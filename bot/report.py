"""Every trade the bot made + a plain verdict.

    python -m bot.report            # from trades.csv
    python -m bot.report --alpaca   # straight from your Alpaca paper account
"""
from __future__ import annotations
import csv, sys


def rows_from_csv(path="trades.csv"):
    out, open_ = [], {}
    for r in csv.DictReader(open(path)):
        if r["reason"] and float(r["pnl"]) == 0 and r["symbol"] not in open_:
            open_[r["symbol"]] = r
        else:
            e = open_.pop(r["symbol"], None)
            out.append({"time": (e or r)["time"][:16].replace("T", " "), "sym": r["symbol"],
                        "side": "LONG" if e and e["side"] == "BUY" else "SHORT", "qty": int(float(r["qty"])),
                        "entry": float(e["price"]) if e else 0, "exit": float(r["price"]),
                        "pnl": float(r["pnl"]), "why_in": e["reason"] if e else "", "why_out": r["reason"]})
    return out


def rows_from_alpaca():
    from .alpaca_broker import filled_orders
    out, pos = [], {}
    for o in filled_orders():
        legs = [o] + (o.get("legs") or [])
        for x in legs:
            if x["status"] != "filled":
                continue
            s, q, px = x["symbol"], float(x["filled_qty"]), float(x["filled_avg_price"])
            q = q if x["side"] == "buy" else -q
            if s not in pos:
                pos[s] = (q, px, x["filled_at"])
            else:
                q0, p0, t0 = pos.pop(s)
                out.append({"time": t0[:16].replace("T", " "), "sym": s, "side": "LONG" if q0 > 0 else "SHORT",
                            "qty": abs(q0), "entry": p0, "exit": px, "pnl": (px - p0) * q0,
                            "why_in": "", "why_out": x.get("type", "")})
    return out


def main():
    from .envfile import load; load()
    t = rows_from_alpaca() if "--alpaca" in sys.argv else rows_from_csv()
    if not t:
        return print("no completed trades yet")
    print(f"{'time':<17}{'sym':<6}{'side':<6}{'qty':>6}{'entry':>10}{'exit':>10}{'P&L':>11}  why")
    eq = peak = dd = 0
    for x in t:
        print(f"{x['time']:<17}{x['sym']:<6}{x['side']:<6}{x['qty']:>6}{x['entry']:>10.2f}{x['exit']:>10.2f}"
              f"{x['pnl']:>+11.2f}  {x['why_in']} -> {x['why_out']}")
        eq += x["pnl"]; peak = max(peak, eq); dd = max(dd, peak - eq)
    w = [x["pnl"] for x in t if x["pnl"] > 0]; l = [x["pnl"] for x in t if x["pnl"] <= 0]
    pf = sum(w) / abs(sum(l)) if l and sum(l) else float("inf")
    days = len({x["time"][:10] for x in t})
    print(f"\ntrades {len(t)} over {days} day(s) | win rate {100*len(w)/len(t):.0f}% | total ${eq:+,.2f}"
          f" | avg win ${sum(w)/max(len(w),1):.2f} avg loss ${sum(l)/max(len(l),1):.2f}"
          f" | profit factor {pf:.2f} | worst drawdown ${dd:,.2f}")
    ok = days >= 40 and len(t) >= 100 and pf >= 1.3 and eq > 0
    print("verdict:", "meets the bar for considering a SMALL real-money test" if ok else
          f"NOT ready for real money - need >=40 trading days, >=100 trades, profit factor >=1.3 and a profit "
          f"(have {days} days, {len(t)} trades, PF {pf:.2f})")


if __name__ == "__main__":
    main()
