"""Full real-time paper bot with a live browser dashboard. No login needed.

    python -m bot.run SPY QQQ AAPL                 # then open http://localhost:8000
    python -m bot.run SPY --replay                 # replay today's bars (test after hours)
    python -m bot.run SPY --feed alpaca            # Alpaca IEX data (set APCA_* keys)
    python -m bot.run SPY --reset                  # start over at --cash

    python -m bot.run --broker alpaca              # send orders to your Alpaca PAPER account

Risk-averse defaults: trades SPY and QQQ (the most liquid ETFs), long only, risks 0.25% of
equity per trade, max 10% of equity in one position, max 4 trades a day, no new trades
before 9:50 or after 15:30 ET, stops for the day at -1%, flattens at 15:50 ET.
Your fake balance is saved in account.json and survives restarts.
"""
import argparse, json, os, time, webbrowser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .strategy import Strategy
from .paper import PaperBroker
from . import feeds, dashboard

ET = ZoneInfo("America/New_York")
ACCOUNT = "account.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=["SPY", "QQQ"])
    ap.add_argument("--feed", choices=["yahoo", "alpaca"], default="yahoo")
    ap.add_argument("--cash", type=float, default=100_000)
    ap.add_argument("--risk", type=float, default=0.0025)
    ap.add_argument("--max-loss", type=float, default=0.01)
    ap.add_argument("--max-position", type=float, default=0.10)
    ap.add_argument("--max-trades", type=int, default=4)
    ap.add_argument("--allow-shorts", action="store_true")
    ap.add_argument("--broker", choices=["local", "alpaca"], default="local")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    get = feeds.yahoo_bars if a.feed == "yahoo" else feeds.alpaca_bars
    alp = None
    if a.broker == "alpaca":
        from . import alpaca_broker as alp
        acct = alp.account()
        a.cash = float(acct["equity"])
        print(f"connected to Alpaca PAPER account, equity ${a.cash:,.2f}")
    S, L = dashboard.STATE, dashboard.LOCK

    broker = PaperBroker(a.cash)
    if os.path.exists(ACCOUNT) and not a.reset and not alp:
        acct = json.load(open(ACCOUNT))
        broker.cash, broker.start_cash = acct["cash"], acct["start_cash"]
    def save():
        flat = {k: v for k, v in broker.pos.items() if v[0]}
        json.dump({"cash": broker.cash if not flat else broker.cash, "start_cash": broker.start_cash}, open(ACCOUNT, "w"))

    strat = {s: Strategy() for s in a.symbols}
    seen = {s: set() for s in a.symbols}
    meta = {}           # sym -> stop/target/reason of open trade
    marks, day_start, halted, day = {}, broker.cash, False, None
    trades_today = 0

    def log(msg):
        line = f"{datetime.now(ET):%H:%M:%S} {msg}"
        print(line)
        with L:
            S["log"] = (S["log"] + [line])[-300:]

    def record(sym, b, side, qty, px, pnl, reason):
        with L:
            S["trades"].append({"t": b.t[11:16], "sym": sym, "side": side, "qty": qty, "px": px,
                                "pnl": round(pnl, 2), "reason": reason})
            S["charts"][sym]["marks"].append({"t": b.t[11:16], "px": px,
                                              "k": {"BUY": "buy", "SHORT": "sell"}.get(side, "exit")})

    def act(sym, b, sig):
        nonlocal halted, trades_today
        q, _ = broker.pos.get(sym, (0, 0))
        if sig["action"] in ("buy", "sell"):
            mins = datetime.fromisoformat(b.t).hour * 60 + datetime.fromisoformat(b.t).minute
            why = ("daily loss limit" if halted else "already in a trade" if q else
                   "shorts disabled" if sig["action"] == "sell" and not a.allow_shorts else
                   f"max {a.max_trades} trades/day" if trades_today >= a.max_trades else
                   "outside 9:50-15:30 window" if not (590 <= mins <= 930) else None)
            if why:
                strat[sym].pos = None
                return log(f"{sym} skipped signal ({why}): {sig['reason']}")
            eq = broker.equity(marks)
            qty = int(min(eq * a.risk / max(abs(sig["price"] - sig["stop"]), 0.01), eq * a.max_position / sig["price"]))
            if qty <= 0:
                strat[sym].pos = None; return
            side = "BUY" if sig["action"] == "buy" else "SHORT"
            if alp:
                try:
                    alp.enter(sym, qty, sig["action"], sig["stop"], sig["target"])
                except Exception as e:
                    strat[sym].pos = None
                    return log(f"{sym} Alpaca rejected order: {e}")
            trades_today += 1
            broker.fill(sym, qty if side == "BUY" else -qty, sig["price"], sig["reason"])
            meta[sym] = sig
            record(sym, b, side, qty, sig["price"], 0, sig["reason"])
            log(f"{sym} {side} {qty} @ {sig['price']:.2f} stop {sig['stop']:.2f} target {sig['target']:.2f} - {sig['reason']}")
        elif sig["action"] == "exit" and q:
            if alp:
                try: alp.exit_all(sym)
                except Exception as e: log(f"{sym} Alpaca exit error: {e}")
            pnl = broker.fill(sym, -q, sig["price"], sig["reason"])
            record(sym, b, "EXIT", abs(q), sig["price"], pnl, sig["reason"])
            meta.pop(sym, None)
            log(f"{sym} EXIT {abs(q)} @ {sig['price']:.2f} P&L ${pnl:+.2f} - {sig['reason']}")
            save()
        if not halted and broker.equity(marks) < day_start * (1 - a.max_loss):
            halted = True
            log("DAILY LOSS LIMIT HIT - no new trades today")

    def flatten(why):
        for sym, (q, _) in list(broker.pos.items()):
            if q:
                if alp:
                    try: alp.exit_all(sym)
                    except Exception as e: log(f"{sym} Alpaca exit error: {e}")
                pnl = broker.fill(sym, -q, marks[sym], why)
                class B: t = datetime.now(timezone.utc).isoformat()
                record(sym, B, "EXIT", abs(q), marks[sym], pnl, why)
                log(f"{sym} FLATTEN {abs(q)} @ {marks[sym]:.2f} P&L ${pnl:+.2f}")
            strat[sym].pos = None
        meta.clear(); save()

    def publish(status):
        eq = broker.equity(marks)
        with L:
            S["status"] = status
            S["equity"] = (S["equity"] + [{"t": datetime.now(ET).strftime("%m-%d %H:%M"), "v": round(eq, 2),
                                            "day": round(eq - day_start, 2), "tot": round(eq - broker.start_cash, 2)}])[-2000:]
            S["positions"] = [{"sym": s, "qty": q, "entry": avg, "last": marks.get(s, avg),
                               "pnl": round(q * (marks.get(s, avg) - avg), 2), "stop": meta[s]["stop"],
                               "target": meta[s]["target"], "reason": meta[s]["reason"]}
                              for s, (q, avg) in broker.pos.items() if q and s in meta]

    for s in a.symbols:
        S["charts"][s] = {"t": [], "c": [], "hod": [], "lod": [], "marks": []}
    dashboard.serve(a.port)
    url = f"http://localhost:{a.port}"
    log(f"bot started: {', '.join(a.symbols)} | feed={a.feed} | fake cash ${broker.cash:,.0f} | dashboard {url}")
    if not a.no_browser:
        webbrowser.open(url)

    while True:
        now = datetime.now(ET)
        if not a.replay and not feeds.market_open():
            publish(f"market closed - waiting (checked {now:%H:%M} ET)")
            time.sleep(60); continue
        if day != now.date():
            day, halted, day_start, trades_today = now.date(), False, broker.equity(marks), 0
            for sym in a.symbols:
                strat[sym].new_day(); seen[sym].clear()
                S["charts"][sym] = {"t": [], "c": [], "hod": [], "lod": [], "marks": []}
            log("new trading day - watching for setups")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
        for sym in a.symbols:
            try:
                bars = get(sym)
            except Exception as e:
                log(f"data error {sym}: {e}"); continue
            for b in bars:
                bt = datetime.fromisoformat(b.t.replace("Z", "+00:00"))
                if b.t in seen[sym] or (not a.replay and bt > cutoff):
                    continue
                seen[sym].add(b.t)
                marks[sym] = b.c
                ch = S["charts"][sym]
                with L:
                    ch["t"].append(bt.astimezone(ET).strftime("%H:%M")); ch["c"].append(b.c)
                    ch["hod"].append(max(b.h, ch["hod"][-1]) if ch["hod"] else b.h)
                    ch["lod"].append(min(b.l, ch["lod"][-1]) if ch["lod"] else b.l)
                sig = strat[sym].on_bar(b)
                if sig:
                    b.t = bt.astimezone(ET).isoformat()
                    act(sym, b, sig)
        if a.replay or now.hour * 60 + now.minute >= 950:
            flatten("end of day flatten")
        publish("halted for the day (loss limit)" if halted else
                ("replay finished - dashboard stays up, Ctrl+C to quit" if a.replay else "live - checking every minute"))
        if a.replay:
            while True: time.sleep(3600)
        time.sleep(60 - datetime.now().second + 3)


if __name__ == "__main__":
    main()
