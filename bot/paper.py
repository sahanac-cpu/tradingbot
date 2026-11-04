"""Local fake-money broker: cash, positions, fills with slippage, trade log CSV."""
import csv, os
from datetime import datetime


class PaperBroker:
    def __init__(self, cash=100_000.0, slippage=0.0001, commission=0.0, log="trades.csv"):
        self.cash, self.start_cash = cash, cash
        self.slip, self.comm, self.log = slippage, commission, log
        self.pos = {}   # sym -> (qty signed, avg price)
        if not os.path.exists(log):
            with open(log, "w", newline="") as f:
                csv.writer(f).writerow(["time", "symbol", "side", "qty", "price", "pnl", "reason", "equity"])

    def fill(self, sym, qty, price, reason=""):
        """qty>0 buy, qty<0 sell. Returns realized pnl."""
        px = price + self.slip * price * (1 if qty > 0 else -1)
        self.cash -= qty * px + self.comm
        q0, avg = self.pos.get(sym, (0, 0.0))
        pnl = 0.0
        if q0 and (q0 > 0) != (qty > 0):          # closing (part of) a position
            closed = min(abs(qty), abs(q0))
            pnl = closed * (px - avg) * (1 if q0 > 0 else -1) - self.comm
        q1 = q0 + qty
        avg = avg if (q0 and abs(q1) < abs(q0)) else ((q0 * avg + qty * px) / q1 if q1 else 0.0)
        self.pos[sym] = (q1, avg) if q1 else (0, 0.0)
        with open(self.log, "a", newline="") as f:
            csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"), sym,
                                    "BUY" if qty > 0 else "SELL", abs(qty), round(px, 4),
                                    round(pnl, 2), reason, round(self.cash, 2)])
        return pnl

    def equity(self, marks):
        return self.cash + sum(q * marks.get(s, a) for s, (q, a) in self.pos.items())
