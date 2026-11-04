"""Sends the bot's trades to your Alpaca PAPER account (fake money, real order handling).
The URL is hard-coded to paper-api, so this can never touch real money."""
from __future__ import annotations
import json, os, urllib.request, urllib.error

URL = "https://paper-api.alpaca.markets"


def _req(method, path, body=None):
    h = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
         "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"], "Content-Type": "application/json"}
    r = urllib.request.Request(URL + path, method=method, headers=h,
                               data=json.dumps(body).encode() if body else None)
    try:
        with urllib.request.urlopen(r, timeout=15) as f:
            return json.loads(f.read() or "null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Alpaca {e.code}: {e.read().decode()[:200]}")


def account():
    return _req("GET", "/v2/account")


def enter(sym, qty, side, stop, target):
    if "/" in sym:   # crypto: Alpaca has no bracket orders, so send market + a separate stop
        o = _req("POST", "/v2/orders", {"symbol": sym, "qty": str(qty), "side": side,
                                        "type": "market", "time_in_force": "gtc"})
        import time; time.sleep(2)
        _req("POST", "/v2/orders", {"symbol": sym, "qty": str(qty), "side": "sell", "type": "stop_limit",
                                    "stop_price": round(stop, 2), "limit_price": round(stop * 0.995, 2),
                                    "time_in_force": "gtc"})
        return o
    """Bracket order: the stop-loss and take-profit live at Alpaca, so you're protected
    even if your computer or the bot dies mid-trade."""
    return _req("POST", "/v2/orders", {
        "symbol": sym, "qty": qty, "side": side, "type": "market", "time_in_force": "day",
        "order_class": "bracket",
        "take_profit": {"limit_price": round(target, 2)},
        "stop_loss": {"stop_price": round(stop, 2)}})


def exit_all(sym):
    import urllib.parse
    for o in _req("GET", f"/v2/orders?status=open&symbols={urllib.parse.quote(sym)}") or []:
        _req("DELETE", f"/v2/orders/{o['id']}")
    try:
        _req("DELETE", f"/v2/positions/{sym.replace('/', '')}")
    except RuntimeError as e:
        if "404" not in str(e):
            raise


def filled_orders(limit=500):
    return _req("GET", f"/v2/orders?status=closed&limit={limit}&direction=asc&nested=true")
