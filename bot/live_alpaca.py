"""Paper-trade the strategy on Alpaca (free paper account: https://alpaca.markets).

    export APCA_API_KEY_ID=...  APCA_API_SECRET_KEY=...
    python -m bot.live_alpaca SPY 10      # symbol, shares

Polls 1-minute bars once a minute during market hours and sends market orders to the
*paper* endpoint only. Stops/targets are managed by the strategy on bar closes.
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from .strategy import Strategy, Bar

TRADE = "https://paper-api.alpaca.markets"   # hard-coded paper URL on purpose
DATA = "https://data.alpaca.markets"
HDR = {"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""),
       "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", ""),
       "Content-Type": "application/json"}


def req(method, url, body=None):
    r = urllib.request.Request(url, method=method, headers=HDR,
                               data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(r, timeout=15) as f:
        return json.loads(f.read() or "null")


def order(sym, qty, side):
    o = req("POST", f"{TRADE}/v2/orders", {"symbol": sym, "qty": qty, "side": side,
                                           "type": "market", "time_in_force": "day"})
    print("  order", side, qty, sym, o.get("status"))


def bars_since(sym, start):
    q = f"timeframe=1Min&start={start.isoformat().replace('+00:00','Z')}&feed=iex&limit=1000"
    out = req("GET", f"{DATA}/v2/stocks/{sym}/bars?{q}").get("bars") or []
    return [Bar(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in out]


def main(sym="SPY", qty=10):
    if not HDR["APCA-API-KEY-ID"]:
        sys.exit("set APCA_API_KEY_ID / APCA_API_SECRET_KEY (paper keys)")
    s, seen, side = Strategy(), set(), 0
    while True:
        clock = req("GET", f"{TRADE}/v2/clock")
        if not clock["is_open"]:
            print("market closed; next open", clock["next_open"]); s.new_day(); seen.clear()
            time.sleep(300); continue
        start = datetime.now(ZoneInfo("America/New_York")).replace(hour=9, minute=30, second=0, microsecond=0).astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        for b in bars_since(sym, start):
            # skip the still-forming bar
            if b.t in seen or datetime.fromisoformat(b.t.replace("Z", "+00:00")) > now - timedelta(minutes=1):
                continue
            seen.add(b.t)
            a = s.on_bar(b)
            if not a:
                continue
            print(b.t, a)
            if a["action"] in ("buy", "sell"):
                order(sym, qty, a["action"]); side = 1 if a["action"] == "buy" else -1
            elif a["action"] == "exit" and side:
                order(sym, qty, "sell" if side > 0 else "buy"); side = 0
        # flatten 10 min before close: day trader, no overnight risk
        close = datetime.fromisoformat(clock["next_close"])
        if side and close - datetime.now(close.tzinfo) < timedelta(minutes=10):
            order(sym, qty, "sell" if side > 0 else "buy"); side = 0; s.pos = None
        time.sleep(60 - datetime.now().second + 2)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "SPY", int(sys.argv[2]) if len(sys.argv) > 2 else 10)
