"""Full real-time paper bot: live 1-min data, fake money, risk management, trade log.

    python -m bot.run SPY QQQ AAPL                 # Yahoo data, $100k fake cash
    python -m bot.run SPY --feed alpaca            # Alpaca IEX data (set APCA_* keys)
    python -m bot.run SPY --replay                 # replay today's bars instantly (test anytime)

Risk rules: risk 0.5% of equity per trade (size = risk / stop distance), max 25% of
equity in one position, stop trading for the day after -2%, flatten at 15:50 ET.
"""
import argparse, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .strategy import Strategy
from .paper import PaperBroker
from . import feeds

ET = ZoneInfo("America/New_York")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--feed", choices=["yahoo", "alpaca"], default="yahoo")
    ap.add_argument("--cash", type=float, default=100_000)
    ap.add_argument("--risk", type=float, default=0.005)
    ap.add_argument("--max-loss", type=float, default=0.02)
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args()
    get = feeds.yahoo_bars if a.feed == "yahoo" else feeds.alpaca_bars

    broker = PaperBroker(a.cash)
    strat = {s: Strategy() for s in a.symbols}
    seen = {s: set() for s in a.symbols}
    marks, day_start, halted, day = {}, a.cash, False, None

    def act(sym, b, sig):
        nonlocal halted
        q, _ = broker.pos.get(sym, (0, 0))
        if sig["action"] in ("buy", "sell") and not halted and q == 0:
            eq = broker.equity(marks)
            risk_per_share = max(abs(sig["price"] - sig["stop"]), 0.01)
            qty = int(min(eq * a.risk / risk_per_share, eq * 0.25 / sig["price"]))
            if qty > 0:
                broker.fill(sym, qty if sig["action"] == "buy" else -qty, sig["price"], sig["reason"])
                print(f"{b.t[11:16]} {sym:<5} {sig['action'].upper():<4} {qty} @ {sig['price']:.2f}"
                      f"  stop {sig['stop']:.2f} tgt {sig['target']:.2f}  [{sig['reason']}]")
            else:
                strat[sym].pos = None
        elif sig["action"] in ("buy", "sell"):
            strat[sym].pos = None   # halted or already in: ignore the signal
        elif sig["action"] == "exit" and q:
            pnl = broker.fill(sym, -q, sig["price"], sig["reason"])
            print(f"{b.t[11:16]} {sym:<5} EXIT {abs(q)} @ {sig['price']:.2f}  pnl ${pnl:+.2f}  [{sig['reason']}]")
        eq = broker.equity(marks)
        if not halted and eq < day_start * (1 - a.max_loss):
            halted = True
            print(f"!! daily loss limit hit (equity ${eq:,.0f}) - no new trades today")

    def flatten(why):
        for sym, (q, _) in list(broker.pos.items()):
            if q:
                pnl = broker.fill(sym, -q, marks[sym], why)
                print(f"     {sym:<5} FLATTEN {abs(q)} @ {marks[sym]:.2f}  pnl ${pnl:+.2f}")
            strat[sym].pos = None

    print(f"paper bot | {', '.join(a.symbols)} | feed={a.feed} | cash ${a.cash:,.0f} | log trades.csv")
    while True:
        now = datetime.now(ET)
        if not a.replay and not feeds.market_open():
            print(f"{now:%H:%M} market closed - waiting (use --replay to test now)"); time.sleep(300); continue
        if day != now.date():
            day, halted, day_start = now.date(), False, broker.equity(marks)
            for s in strat.values():
                s.new_day()
            for s in seen.values():
                s.clear()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
        for sym in a.symbols:
            try:
                bars = get(sym)
            except Exception as e:
                print(f"feed error {sym}: {e}"); continue
            for b in bars:
                bt = datetime.fromisoformat(b.t.replace("Z", "+00:00"))
                if b.t in seen[sym] or (not a.replay and bt > cutoff):
                    continue           # skip duplicates and the still-forming bar
                seen[sym].add(b.t)
                marks[sym] = b.c
                sig = strat[sym].on_bar(b)
                if sig:
                    act(sym, b, sig)
        if a.replay or now.hour * 60 + now.minute >= 950:
            flatten("end of day flatten")
        eq = broker.equity(marks)
        print(f"--- {now:%H:%M:%S} equity ${eq:,.2f}  day {eq - day_start:+,.2f}  "
              f"total {eq - broker.start_cash:+,.2f}  open {[(s, q) for s, (q, _) in broker.pos.items() if q]}")
        if a.replay:
            return
        time.sleep(60 - datetime.now().second + 3)


if __name__ == "__main__":
    main()
