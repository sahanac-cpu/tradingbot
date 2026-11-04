"""Real-time 1-minute bar feeds. Yahoo needs no account; Alpaca needs free paper keys."""
import json, os, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .strategy import Bar


def _get(url, headers=None):
    r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    with urllib.request.urlopen(r, timeout=15) as f:
        return json.loads(f.read())


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
    start = datetime.now(ZoneInfo("America/New_York")).replace(hour=9, minute=30, second=0, microsecond=0)
    s = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = _get(f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min&start={s}&feed=iex&limit=1000",
             {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]})
    return [Bar(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in d.get("bars") or []]


def market_open():
    now = datetime.now(ZoneInfo("America/New_York"))
    m = now.hour * 60 + now.minute
    return now.weekday() < 5 and 570 <= m < 960   # 9:30-16:00 ET (ignores holidays)
