"""Real-time 1-minute bars. Stocks/ETFs: Yahoo (no account) or Alpaca. Crypto: Alpaca's
free crypto feed (no keys needed). Crypto symbols look like BTC/USD."""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .strategy import Bar

ET = ZoneInfo("America/New_York")


def is_crypto(sym):
    return "/" in sym


def _get(url, headers=None):
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    with urllib.request.urlopen(r, timeout=15) as f:
        return json.loads(f.read())


def _keys():
    return {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}


def _start(h=9, m=30):
    t = datetime.now(ET).replace(hour=h, minute=m, second=0, microsecond=0)
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def yahoo_bars(sym):
    d = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1m&range=1d")["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(d.get("timestamp") or []):
        if None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]):
            continue
        out.append(Bar(datetime.fromtimestamp(ts, timezone.utc).isoformat(), q["open"][i], q["high"][i],
                       q["low"][i], q["close"][i], q["volume"][i] or 0))
    return out


def alpaca_bars(sym):
    d = _get(f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min&start={_start()}&feed=iex&limit=1000", _keys())
    return [Bar(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in d.get("bars") or []]


def crypto_bars(sym):
    """Bars since midnight ET (crypto never closes, so the 'day' runs midnight to midnight)."""
    out, token = [], None
    while True:
        q = {"symbols": sym, "timeframe": "1Min", "start": _start(0, 0), "limit": 1000}
        if token:
            q["page_token"] = token
        d = _get("https://data.alpaca.markets/v1beta3/crypto/us/bars?" + urllib.parse.urlencode(q))
        out += [Bar(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in d["bars"].get(sym, [])]
        token = d.get("next_page_token")
        if not token:
            return out


def bars(sym, feed):
    if is_crypto(sym):
        return crypto_bars(sym)
    return yahoo_bars(sym) if feed == "yahoo" else alpaca_bars(sym)


def market_open(sym=None):
    if sym and is_crypto(sym):
        return True
    now = datetime.now(ET)
    m = now.hour * 60 + now.minute
    return now.weekday() < 5 and 570 <= m < 960   # 9:30-16:00 ET (ignores holidays)
