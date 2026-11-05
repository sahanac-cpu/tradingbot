"""Backtest on ~a year of real 1-minute history with a train/test split.

    python3 -m bot.backtest                      # 360 days, default symbols (needs APCA_* keys)
    python3 -m bot.backtest VOO SPY --days 180
    python3 -m bot.backtest --synthetic          # fake data, just to check it runs

How it works
  1. Downloads 1-min bars from Alpaca (free) into data/ (cached, so later runs are instant).
  2. Splits the days in time order: first 70% = TRAIN, last 30% = TEST. The test period is
     never used to choose anything, so it shows how the bot would do on "unseen" days.
  3. Runs the current settings on both halves (baseline).
  4. Tries a grid of settings on TRAIN only, picks the best, then checks it on TEST.
  5. Trains the self-learning filter on TRAIN trades and checks whether it helps on TEST.
  6. Writes everything to backtest_report.txt and backtest_trades.csv.

Costs are included: 0.01% slippage per side, plus 0.25% per side fee on crypto
(Alpaca's crypto taker fee tier for small accounts). ETFs have no commission.
"""
from __future__ import annotations
import argparse, csv, itertools, json, os, sys, time, urllib.parse, urllib.request
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool
from zoneinfo import ZoneInfo
from .strategy import Strategy, Params, Bar
from .learner import Learner, features
from .feeds import is_crypto

ET = ZoneInfo("America/New_York")
DEFAULT = ["VOO", "SPY", "QQQ", "IWM", "DIA", "BTC/USD", "ETH/USD"]
RISK_DOLLARS, MAX_NOTIONAL = 250.0, 10_000.0      # 0.25% and 10% of a $100k account
SLIP, CRYPTO_FEE = 0.0001, 0.0025
MAX_TRADES_PER_SYMBOL = 2

# ------------------------------------------------------------------ data
def _get(url):
    h = {"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""),
         "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", ""), "User-Agent": "tradingbot"}
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as f:
                return json.loads(f.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3 * (attempt + 1)); continue
            raise SystemExit(f"Alpaca error {e.code}: {e.read().decode()[:200]}\n"
                             "Did you set APCA_API_KEY_ID / APCA_API_SECRET_KEY in this terminal?")
    raise SystemExit("Alpaca kept rate-limiting; wait a minute and rerun (downloads are cached).")


def download(sym, days):
    os.makedirs("data", exist_ok=True)
    path = f"data/{sym.replace('/', '-')}_{days}d.csv"
    if os.path.exists(path):
        return path
    end = datetime.now(timezone.utc) - timedelta(minutes=20)          # free data is 15-min delayed
    start = end - timedelta(days=days)
    q = {"timeframe": "1Min", "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 10000}
    if is_crypto(sym):
        base, q["symbols"] = "https://data.alpaca.markets/v1beta3/crypto/us/bars?", sym
    else:
        base, q["feed"] = f"https://data.alpaca.markets/v2/stocks/{sym}/bars?", "iex"
    rows, n = [], 0
    with open(path + ".tmp", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["t", "o", "h", "l", "c", "v"])
        while True:
            d = _get(base + urllib.parse.urlencode(q))
            bars = d["bars"].get(sym, []) if is_crypto(sym) else (d.get("bars") or [])
            for b in bars:
                w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]])
            n += len(bars)
            print(f"\r  downloading {sym}: {n:,} bars", end="", flush=True)
            if not d.get("next_page_token"):
                break
            q["page_token"] = d["next_page_token"]
    os.replace(path + ".tmp", path)
    print()
    return path


def load_days(path, sym):
    """Group bars into trading days (ET). ETFs: regular hours only."""
    days = defaultdict(list)
    for r in csv.DictReader(open(path)):
        t = datetime.fromisoformat(r["t"].replace("Z", "+00:00")).astimezone(ET)
        m = t.hour * 60 + t.minute
        if not is_crypto(sym) and not (570 <= m < 960):
            continue
        days[t.date()].append(Bar(t.isoformat(), float(r["o"]), float(r["h"]), float(r["l"]), float(r["c"]), float(r["v"])))
    return dict(sorted(days.items()))


def synthetic(sym, n_days):
    from .simulate import synthetic_day
    scale = {"BTC/USD": 950, "ETH/USD": 34}.get(sym, 5)
    out, d = {}, datetime(2025, 11, 3, tzinfo=ET)
    for i in range(n_days):
        day = d + timedelta(days=i)
        if not is_crypto(sym) and day.weekday() >= 5:
            continue
        bars = synthetic_day(hash((sym, i)) % 10**6)
        for j, b in enumerate(bars):
            b.t = (day.replace(hour=9, minute=30) + timedelta(minutes=j)).isoformat()
            b.o *= scale; b.h *= scale; b.l *= scale; b.c *= scale
        out[day.date()] = bars
    return out

# ------------------------------------------------------------------ simulation
def simulate(data, params=None, learner=None, use_filter=False, learn=False, cls=None, cap=None):
    """data = {sym: {date: [bars]}}. Returns list of trade dicts. Mirrors bot.run's rules."""
    trades = []
    for sym, days in data.items():
        crypto = is_crypto(sym)
        fee = CRYPTO_FEE if crypto else 0.0
        for date, bars in days.items():
            C = cls or Strategy
            s = C() if params is None else C(p=params)
            n_today, open_t = 0, None
            for b in bars:
                t = datetime.fromisoformat(b.t)
                mins = t.hour * 60 + t.minute
                if open_t and not crypto and mins >= 950:                 # flatten 15:50
                    sig = {"action": "exit", "price": b.o, "reason": "end of day"}
                else:
                    sig = s.on_bar(b)
                if not sig:
                    continue
                if sig["action"] == "exit":
                    if not open_t:
                        continue
                    px = sig["price"] * (1 - SLIP)
                    gross = (px - open_t["entry"]) * open_t["qty"]
                    costs = fee * (px + open_t["entry"]) * open_t["qty"]
                    open_t.update(exit=px, exit_time=b.t, why_out=sig["reason"], pnl=gross - costs)
                    if learner and learn:
                        learner.learn(open_t.pop("_x"), open_t["pnl"] > 0)
                    open_t.pop("_x", None)
                    trades.append(open_t); open_t, s.pos = None, None
                    continue
                # entry signal - same filters as the live bot
                skip = (sig["action"] == "sell" or n_today >= (cap or MAX_TRADES_PER_SYMBOL) or
                        (not crypto and not (590 <= mins <= 930)))
                x = None
                if not skip and learner:
                    x = features(s, sig, sym, mins - 570 if not crypto else mins)
                    ok, _, _ = learner.decide(x)
                    skip = use_filter and not ok
                if skip:
                    s.pos = None; continue
                entry = sig["price"] * (1 + SLIP)
                qty = min(RISK_DOLLARS / max(entry - sig["stop"], entry * 1e-4), MAX_NOTIONAL / entry)
                if not crypto:
                    qty = int(qty)
                if qty * entry < 10:
                    s.pos = None; continue
                n_today += 1
                open_t = {"sym": sym, "date": str(date), "time": b.t[11:16], "setup": sig["reason"].split(" #")[0],
                          "strategy": s.name, "why": sig.get("why", ""), "reason": sig["reason"],
                          "entry": entry, "qty": qty, "stop": sig["stop"], "target": sig["target"], "_x": x}
            if open_t:                                                    # close at last bar
                px = bars[-1].c * (1 - SLIP)
                open_t.update(exit=px, exit_time=bars[-1].t, why_out="day end",
                              pnl=(px - open_t["entry"]) * open_t["qty"] - fee * (px + open_t["entry"]) * open_t["qty"])
                if learner and learn:
                    learner.learn(open_t["_x"], open_t["pnl"] > 0)
                open_t.pop("_x", None); trades.append(open_t)
    return trades


def stats(trades):
    if not trades:
        return {"n": 0, "pnl": 0, "pf": 0, "win": 0, "dd": 0, "avg": 0}
    trades = sorted(trades, key=lambda t: (t["date"], t["time"]))
    w = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    l = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    eq = peak = dd = 0
    for t in trades:
        eq += t["pnl"]; peak = max(peak, eq); dd = max(dd, peak - eq)
    return {"n": len(trades), "pnl": eq, "pf": w / l if l else float("inf"),
            "win": 100 * sum(t["pnl"] > 0 for t in trades) / len(trades), "dd": dd, "avg": eq / len(trades)}


def fmt(s):
    return (f"{s['n']:>5} trades  win {s['win']:>4.0f}%  P&L ${s['pnl']:>+10,.0f}  "
            f"profit factor {s['pf']:>5.2f}  avg ${s['avg']:>+7.2f}  worst drawdown ${s['dd']:>8,.0f}")


def split(data, frac=0.7):
    all_days = sorted({d for days in data.values() for d in days})
    cut = all_days[int(len(all_days) * frac)]
    tr = {s: {d: b for d, b in days.items() if d < cut} for s, days in data.items()}
    te = {s: {d: b for d, b in days.items() if d >= cut} for s, days in data.items()}
    return tr, te, all_days[0], cut, all_days[-1]


GRID = {"flush_atr": [3.0, 4.0, 5.0], "target_atr": [2.0, 3.0, 4.0],
        "shakeout_bars": [6, 10], "coil_max_range_atr": [1.0, 1.5]}
_DATA = None


def _init(d):
    global _DATA
    _DATA = d


def _score(combo):
    p = replace(Params(), **combo)
    return combo, stats(simulate(_DATA, p))


def breakdown(trades, key):
    g = defaultdict(list)
    for t in trades:
        g[key(t)].append(t)
    return {k: stats(v) for k, v in sorted(g.items())}

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=DEFAULT)
    ap.add_argument("--days", type=int, default=360)
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    syms = [s.upper() for s in a.symbols]

    print(f"loading {a.days} days of 1-minute bars for {', '.join(syms)}")
    data = {s: synthetic(s, a.days) if a.synthetic else load_days(download(s, a.days), s) for s in syms}
    train, test, d0, cut, d1 = split(data)
    out = []
    say = lambda x="": (print(x), out.append(x))
    say(f"\nBACKTEST {'(SYNTHETIC DATA - not meaningful)' if a.synthetic else ''}")
    say(f"symbols {', '.join(syms)} | TRAIN {d0} -> {cut} | TEST {cut} -> {d1}")
    say(f"costs: slippage {SLIP:.2%}/side, crypto fee {CRYPTO_FEE:.2%}/side | risk ${RISK_DOLLARS:.0f}/trade, long only")

    base = Params()
    b_tr, b_te = simulate(train, base), simulate(test, base)
    say("\n1) CURRENT SETTINGS")
    say("   train " + fmt(stats(b_tr)))
    say("   test  " + fmt(stats(b_te)))

    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    say(f"\n2) TUNING {len(combos)} setting combinations on TRAIN only...")
    with Pool(initializer=_init, initargs=(train,)) as pool:
        res = pool.map(_score, combos)
    ok = [r for r in res if r[1]["n"] >= 50] or res
    best, bs = max(ok, key=lambda r: (r[1]["pf"] if r[1]["pf"] != float("inf") else 0, r[1]["pnl"]))
    say("   top 5 on train:")
    for c, s in sorted(ok, key=lambda r: -r[1]["pf"])[:5]:
        say(f"     {c}  PF {s['pf']:.2f}  n {s['n']}  P&L ${s['pnl']:+,.0f}")
    tuned = replace(Params(), **best)
    t_te = simulate(test, tuned)
    say(f"   best: {best}")
    say("   test  " + fmt(stats(t_te)) + "   <- the honest number")

    say("\n3) SELF-LEARNING FILTER (trained on TRAIN, keeps learning through TEST)")
    brain = Learner(path=os.devnull if False else "backtest_model.json")
    brain.w = {k: 0.0 for k in brain.w}; brain.n = brain.wins = 0
    simulate(train, tuned, learner=brain, learn=True)
    a_te = simulate(test, tuned, learner=brain, use_filter=True, learn=True)
    say("   test  " + fmt(stats(a_te)))
    say("   what it learned: " + ", ".join(f"{f} {w:+.2f}" for f, w in brain.top_factors(6)))

    final = t_te
    say("\n4) TEST BREAKDOWN (tuned settings)")
    say("   by setup:")
    for k, s in breakdown(final, lambda t: t["setup"]).items():
        say(f"     {k:<24}" + fmt(s))
    say("   by symbol:")
    for k, s in breakdown(final, lambda t: t["sym"]).items():
        say(f"     {k:<24}" + fmt(s))
    say("   by exit reason:")
    for k, s in breakdown(final, lambda t: t["why_out"]).items():
        say(f"     {k:<24}" + fmt(s))
    say("   by hour (ET):")
    for k, s in breakdown(final, lambda t: t["time"][:2]).items():
        say(f"     {k + ':00':<24}" + fmt(s))

    from .quant import STRATEGIES
    say("\n5) STRATEGY COMPARISON (default settings, same costs)")
    for C in STRATEGIES:
        say(f"   {C.name:<16} train " + fmt(stats(simulate(train, cls=C, cap=3))))
        say(f"   {'':<16} test  " + fmt(stats(simulate(test, cls=C, cap=3))))

    with open("backtest_trades.csv", "w", newline="") as f:
        cols = ["sym", "date", "time", "setup", "entry", "stop", "target", "exit", "exit_time", "why_out", "qty", "pnl"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for t in final:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items()})
    open("backtest_report.txt", "w").write("\n".join(out) + "\n")
    print("\nsaved backtest_report.txt and backtest_trades.csv - paste the report to Claude for code changes")


if __name__ == "__main__":
    main()
