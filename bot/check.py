"""Tests every connection the bot uses and says exactly what works.

    python3 -m bot.check
"""
import json, os, urllib.request, urllib.error
from .envfile import load


def hit(name, url, auth=True):
    h = {"User-Agent": "Mozilla/5.0"}
    if auth:
        h.update({"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""),
                  "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", "")})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=15) as f:
            body = f.read()[:120].decode(errors="replace")
            print(f"  OK    {name}")
            return True, body
    except urllib.error.HTTPError as e:
        print(f"  FAIL  {name}: HTTP {e.code} {e.read()[:150].decode(errors='replace').strip()}")
    except Exception as e:
        print(f"  FAIL  {name}: {e}")
    return False, ""


def main():
    load()
    k = os.environ.get("APCA_API_KEY_ID", "")
    print(f"key loaded: {k[:4]}...{k[-3:]} (length {len(k)})" if k else "no key found in ~/.tradingbot.env or terminal")
    s = os.environ.get("APCA_API_SECRET_KEY", "")
    print(f"secret length: {len(s)} (should be about 40-44)")
    hit("Alpaca paper account (trading)", "https://paper-api.alpaca.markets/v2/account")
    hit("Alpaca stock data (backtest)", "https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day&limit=2&feed=iex")
    hit("Alpaca crypto data (no key needed)", "https://data.alpaca.markets/v1beta3/crypto/us/bars?symbols=BTC/USD&timeframe=1Day&limit=2", auth=False)
    hit("Yahoo data (live feed + backup)", "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1m&range=1d", auth=False)


if __name__ == "__main__":
    main()
