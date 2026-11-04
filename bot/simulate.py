"""Offline paper-test: no keys needed. Runs the strategy on synthetic intraday data
that contains the patterns from the video (stop runs, flushes, shakeouts), or on a CSV
with columns t,o,h,l,c,v (one session per file).

    python -m bot.simulate            # 50 synthetic days
    python -m bot.simulate data.csv   # your own 1-min bars
"""
import csv, random, sys
from .strategy import Strategy, Bar


def synthetic_day(seed, n=390, px=100.0):
    r = random.Random(seed)
    bars, drift, t = [], 0.0, 0
    while t < n:
        ev = r.random()
        if ev < 0.02:        # flush: fast high-volume drop, then V-recovery
            seq = [(-0.25, 4)] * 6 + [(0.18, 3)] * 8
        elif ev < 0.04:      # coil under the highs, then a stop run
            seq = [(0.0, 0.6)] * 8 + [(0.2, 3)] * 5 + [(-0.1, 1.5)] * 4
        else:
            seq = [(drift, 1)]
            drift = 0.9 * drift + r.gauss(0, 0.004)
        for mu, vm in seq:
            o = px
            c = o + mu + r.gauss(0, 0.06)
            h, l = max(o, c) + abs(r.gauss(0, 0.03)), min(o, c) - abs(r.gauss(0, 0.03))
            bars.append(Bar(str(t), o, h, l, c, 1000 * vm * r.uniform(0.6, 1.4)))
            px, t = c, t + 1
    return bars[:n]


def run(days):
    s, trades = Strategy(), []
    for bars in days:
        s.new_day()
        for b in bars:
            a = s.on_bar(b)
            if a:
                print(f"{b.t:>5} {a}")
                if a["action"] == "exit":
                    trades.append(a)
    if not trades:
        return print("no trades")
    wins = [t for t in trades if t["pnl"] > 0]
    total = sum(t["pnl"] for t in trades)
    print(f"\ntrades={len(trades)} win%={100*len(wins)/len(trades):.0f} "
          f"total_pnl/share={total:.2f} avg={total/len(trades):.3f}")
    by = {}
    for t in trades:
        by.setdefault(t["entry_reason"].split(" #")[0], []).append(t["pnl"])
    for k, v in by.items():
        print(f"  {k:<24} n={len(v):<4} pnl={sum(v):.2f}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            rows = [Bar(r["t"], *(float(r[k]) for k in "ohlcv")) for r in csv.DictReader(f)]
        run([rows])
    else:
        run([synthetic_day(i) for i in range(50)])
