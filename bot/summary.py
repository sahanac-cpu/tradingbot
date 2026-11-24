"""One-screen summary of how the bot is doing. Run from the bot's folder:

    cd ~/tradingbot-service && python3 -m bot.summary               # normal mode
    cd ~/tradingbot-service && python3 -m bot.summary --aggressive  # aggressive mode
"""
from __future__ import annotations
import os
from collections import defaultdict
from . import arena
from .quant import STRATEGIES


def main():
    import sys
    if "--aggressive" in sys.argv and os.path.isdir("aggressive"):
        os.chdir("aggressive")
    days = arena.summary()
    if not days:
        return print("no history yet - is the bot running? (bash scripts/status.sh)")
    names = [C.name for C in STRATEGIES]
    tot = defaultdict(lambda: {"pnl": 0.0, "n": 0, "wins": 0})
    real = {"pnl": 0.0, "n": 0, "wins": 0}
    print(f"{'date':<11}{'champion':<16}{'real P&L':>10}  " + "  ".join(f"{n.split()[0][:9]:>14}" for n in names))
    for d in days:
        r = d.get("real") or {}
        for k in real:
            real[k] += r.get(k, 0)
        cells = []
        for n in names:
            a = d["arena"].get(n, {"pnl": 0, "n": 0, "wins": 0})   # ETF trades only
            for k in tot[n]:
                tot[n][k] += a.get(k, 0)
            cells.append(f"{a['pnl']:>+9.0f} ({a['n']:>2})")
        champ = "backfill" if d["source"] == "backfill" else (d.get("champion") or "sat out")
        print(f"{d['date']:<11}{champ:<16}{r.get('pnl', 0):>+10.2f}  " + "  ".join(f"{c:>14}" for c in cells))
    print("\nTOTALS (simulated ETF trades, all days - crypto excluded, its fees made every trade a loss)")
    for n in sorted(names, key=lambda n: -tot[n]["pnl"]):
        t = tot[n]
        print(f"  {n:<16} P&L ${t['pnl']:>+9,.2f}   trades {t['n']:>4}   win {100 * t['wins'] / max(t['n'], 1):>3.0f}%")
    print(f"\nREAL ACCOUNT: P&L ${real['pnl']:+,.2f} over {real['n']} trades "
          f"({100 * real['wins'] / max(real['n'], 1):.0f}% won) on {len(days)} days of history")
    champ, _, note = arena.pick_champion("9999-12-31")
    print(f"next champion if picked now: {champ or 'none - sitting out'} ({note})")
    log = "logs/bot.log" if os.path.exists("logs/bot.log") else "../logs/bot.log"
    if os.path.exists(log):
        print("\nlast log lines:")
        print("".join(open(log).readlines()[-6:]).rstrip())


if __name__ == "__main__":
    main()
