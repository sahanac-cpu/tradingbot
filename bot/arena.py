"""Strategy competition + day-by-day history.

- Every strategy trades every symbol in its own simulated $100k account all day.
- Each morning the CHAMPION is picked: best simulated P&L over the last 10 days
  (minimum 5 trades). Only the champion's trades are copied to your real paper account.
- Each day is saved to history/YYYY-MM-DD.json (trades, reviews, results per strategy).
- On first start the last 5 days are back-filled from real market data so the
  leaderboard and history aren't empty.
"""
from __future__ import annotations
import glob, json, os
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .quant import STRATEGIES

ET = ZoneInfo("America/New_York")
HIST = "history"
LOOKBACK = 10


def day_path(d):
    return os.path.join(HIST, f"{d}.json")


def load_day(d):
    p = day_path(d)
    return json.load(open(p)) if os.path.exists(p) else None


def save_day(d, data):
    os.makedirs(HIST, exist_ok=True)
    tmp = day_path(d) + ".tmp"
    json.dump(data, open(tmp, "w"))
    os.replace(tmp, day_path(d))


def all_days():
    return sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(HIST, "*.json")))


def summary():
    out = []
    for d in all_days():
        x = load_day(d) or {}
        ar = x.get("arena", {})
        best = max(ar, key=lambda k: ar[k]["pnl"]) if ar else None
        out.append({"date": d, "champion": x.get("champion"), "source": x.get("source", "live"),
                    "real": x.get("real", {}), "arena": ar, "best": best})
    return out


def score_table(before_date):
    """10-day simulated results per strategy, using days strictly before `before_date`."""
    days = [d for d in all_days() if d < str(before_date)][-LOOKBACK:]
    tot = {C.name: {"pnl": 0.0, "n": 0, "wins": 0, "days": 0} for C in STRATEGIES}
    for d in days:
        for name, r in (load_day(d) or {}).get("arena", {}).items():
            if name in tot:
                t = tot[name]
                t["pnl"] += r["pnl"]; t["n"] += r["n"]; t["wins"] += r["wins"]; t["days"] += 1
    return tot


def pick_champion(today):
    tot = score_table(today)
    ok = {k: v for k, v in tot.items() if v["n"] >= 5}
    if not ok:
        return STRATEGIES[0].name, tot, "not enough history yet - Game Theory trades by default"
    best = max(ok, key=lambda k: ok[k]["pnl"])
    v = ok[best]
    return best, tot, (f"{best} made ${v['pnl']:+,.0f} over the last {v['days']} days "
                       f"({v['n']} simulated trades, {100 * v['wins'] / max(v['n'], 1):.0f}% won) - best of all strategies")


def arena_stats(trades):
    g = defaultdict(lambda: {"pnl": 0.0, "n": 0, "wins": 0})
    for C in STRATEGIES:
        g[C.name]
    for t in trades:
        if t.get("side") == "EXIT" and t.get("account") == "sim":
            r = g[t["strategy"]]
            r["pnl"] = round(r["pnl"] + t["pnl"], 2); r["n"] += 1; r["wins"] += t["pnl"] > 0
    return dict(g)


def backfill(symbols, days=5, log=print):
    """Run every strategy over the last few days of real 1-min data and save them as history."""
    from . import feeds
    from .backtest import simulate, CRYPTO_FEE  # noqa
    today = datetime.now(ET).date()
    data = {}
    for sym in symbols:
        try:
            bars = feeds.crypto_bars(sym, days_back=days) if feeds.is_crypto(sym) else feeds.yahoo_bars(sym, "5d")
        except Exception as e:
            log(f"backfill: no data for {sym} ({e})"); continue
        by = defaultdict(list)
        for b in bars:
            t = datetime.fromisoformat(b.t.replace("Z", "+00:00")).astimezone(ET)
            m = t.hour * 60 + t.minute
            if feeds.is_crypto(sym) or 570 <= m < 960:
                b.t = t.isoformat(); by[t.date()].append(b)
        data[sym] = {d: v for d, v in by.items() if d < today}
    if not data:
        return 0
    per_day = defaultdict(list)
    for C in STRATEGIES:
        for t in simulate(data, cls=C, cap=3):
            per_day[t["date"]].append(t)
    for d in sorted(per_day):
        if os.path.exists(day_path(d)):
            continue
        trades = []
        for t in sorted(per_day[d], key=lambda x: x["time"]):
            common = {"sym": t["sym"], "strategy": t["strategy"], "account": "sim", "qty": t["qty"]}
            trades.append(dict(common, t=t["time"], side="BUY", px=t["entry"], pnl=0, reason=t["reason"], why=t["why"]))
            trades.append(dict(common, t=t["exit_time"][11:16], side="EXIT", px=t["exit"], pnl=round(t["pnl"], 2),
                               reason=t["why_out"], why=""))
        save_day(d, {"date": d, "source": "backfill", "champion": None, "trades": trades, "reviews": [],
                     "arena": arena_stats(trades), "real": {}})
    log(f"backfilled {len(per_day)} past days of simulated trades for all strategies")
    return len(per_day)
