"""Real-time paper bot with a live browser dashboard.

    python -m bot.run                              # default ETFs + BTC/ETH, local fake money
    python -m bot.run --broker alpaca              # orders go to your Alpaca PAPER account
    python -m bot.run VOO SPY BTC/USD              # pick your own (crypto = XXX/USD)
    python -m bot.run --replay                     # replay today's bars now (any time)
    python -m bot.run --reset                      # start the local fake account over

Risk-averse defaults: long only, 0.25% of equity risked per trade, max 10% of equity per
position, max 6 trades a day, ETFs only 9:50-15:30 ET and flat by 15:50, stop for the day
at -1%. Crypto trades 24/7 with the same limits (its "day" runs midnight to midnight ET).
"""
from __future__ import annotations
import argparse, json, os, time, webbrowser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .strategy import Strategy
from .paper import PaperBroker
from . import feeds, dashboard

ET = ZoneInfo("America/New_York")
ACCOUNT = "account.json"
DEFAULT = ["VOO", "SPY", "QQQ", "IWM", "DIA", "BTC/USD", "ETH/USD"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=DEFAULT)
    ap.add_argument("--feed", choices=["yahoo", "alpaca"], default="yahoo")
    ap.add_argument("--broker", choices=["local", "alpaca"], default="local")
    ap.add_argument("--cash", type=float, default=100_000)
    ap.add_argument("--risk", type=float, default=0.0025)
    ap.add_argument("--max-position", type=float, default=0.10)
    ap.add_argument("--max-trades", type=int, default=6)
    ap.add_argument("--max-loss", type=float, default=0.01)
    ap.add_argument("--allow-shorts", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    a.symbols = [s.upper() for s in a.symbols]
    S, L = dashboard.STATE, dashboard.LOCK

    alp = None
    if a.broker == "alpaca":
        from . import alpaca_broker as alp
        a.cash = float(alp.account()["equity"])
    broker = PaperBroker(a.cash)
    if os.path.exists(ACCOUNT) and not a.reset and not alp:
        acct = json.load(open(ACCOUNT))
        broker.cash, broker.start_cash = acct["cash"], acct["start_cash"]

    def save():
        json.dump({"cash": broker.cash, "start_cash": broker.start_cash}, open(ACCOUNT, "w"))

    strat = {s: Strategy() for s in a.symbols}
    seen = {s: set() for s in a.symbols}
    meta, marks, opens = {}, {}, {}
    st = {"halted": False, "day": None, "day_start": broker.cash, "trades_today": 0}

    def log(msg, kind="info"):
        line = f"{datetime.now(ET):%H:%M:%S}  {msg}"
        print(line)
        with L:
            S["log"] = (S["log"] + [{"m": line, "k": kind}])[-300:]

    def record(sym, t, side, qty, px, pnl, reason):
        with L:
            S["trades"].append({"t": t, "sym": sym, "side": side, "qty": qty, "px": px,
                                "pnl": round(pnl, 2), "reason": reason})
            S["charts"][sym]["marks"].append({"t": t, "px": px, "k": {"BUY": "buy", "SHORT": "sell"}.get(side, "exit")})

    def close(sym, px, reason, t):
        q, _ = broker.pos.get(sym, (0, 0))
        if not q:
            return
        if alp:
            try: alp.exit_all(sym)
            except Exception as e: log(f"{sym} Alpaca exit error: {e}", "bad")
        pnl = broker.fill(sym, -q, px, reason)
        record(sym, t, "EXIT", abs(q), px, pnl, reason)
        meta.pop(sym, None); strat[sym].pos = None
        log(f"{sym} EXIT {abs(q):g} @ {px:,.2f}  P&L ${pnl:+,.2f}  - {reason}", "win" if pnl > 0 else "loss")
        save()

    def act(sym, b, sig, t):
        q, _ = broker.pos.get(sym, (0, 0))
        crypto = feeds.is_crypto(sym)
        if sig["action"] == "exit":
            return close(sym, sig["price"], sig["reason"], t)
        bt = datetime.fromisoformat(b.t.replace("Z", "+00:00")).astimezone(ET)
        mins = bt.hour * 60 + bt.minute
        why = ("daily loss limit" if st["halted"] else "already in a trade" if q else
               "shorts disabled" if sig["action"] == "sell" and (crypto or not a.allow_shorts) else
               f"max {a.max_trades} trades/day" if st["trades_today"] >= a.max_trades else
               "outside 9:50-15:30 window" if not crypto and not (590 <= mins <= 930) else None)
        if why:
            strat[sym].pos = None
            return log(f"{sym} skipped ({why}): {sig['reason']}", "skip")
        eq = broker.equity(marks)
        qty = min(eq * a.risk / max(abs(sig["price"] - sig["stop"]), 1e-9), eq * a.max_position / sig["price"])
        qty = round(qty, 6) if crypto else int(qty)
        if qty * sig["price"] < 10:
            strat[sym].pos = None; return
        if alp:
            try:
                alp.enter(sym, qty, sig["action"], sig["stop"], sig["target"])
            except Exception as e:
                strat[sym].pos = None
                return log(f"{sym} Alpaca rejected order: {e}", "bad")
        side = "BUY" if sig["action"] == "buy" else "SHORT"
        broker.fill(sym, qty if side == "BUY" else -qty, sig["price"], sig["reason"])
        meta[sym] = sig; st["trades_today"] += 1
        record(sym, t, side, qty, sig["price"], 0, sig["reason"])
        log(f"{sym} {side} {qty:g} @ {sig['price']:,.2f}  stop {sig['stop']:,.2f}  target {sig['target']:,.2f}  - {sig['reason']}", "entry")

    def publish(status):
        eq = broker.equity(marks)
        trades = [x for x in S["trades"] if x["side"] == "EXIT"]
        wins = [x for x in trades if x["pnl"] > 0]
        with L:
            S["status"] = status
            S["broker"] = "Alpaca paper" if alp else "Local fake money"
            S["stats"] = {"n": len(trades), "win": round(100 * len(wins) / len(trades)) if trades else None,
                          "trades_today": st["trades_today"], "max_trades": a.max_trades, "halted": st["halted"],
                          "risk": a.risk, "max_loss": a.max_loss}
            S["equity"] = (S["equity"] + [{"t": datetime.now(ET).strftime("%m-%d %H:%M"), "v": round(eq, 2),
                                            "day": round(eq - st["day_start"], 2), "tot": round(eq - broker.start_cash, 2)}])[-2000:]
            S["positions"] = [{"sym": s, "qty": q, "entry": avg, "last": marks.get(s, avg),
                               "pnl": round(q * (marks.get(s, avg) - avg), 2), "stop": meta[s]["stop"],
                               "target": meta[s]["target"], "reason": meta[s]["reason"]}
                              for s, (q, avg) in broker.pos.items() if q and s in meta]
            S["tickers"] = [{"sym": s, "last": marks.get(s), "open": opens.get(s),
                             "crypto": feeds.is_crypto(s), "live": a.replay or feeds.market_open(s)} for s in a.symbols]

    for s in a.symbols:
        S["charts"][s] = {"t": [], "c": [], "hod": [], "lod": [], "marks": []}
    dashboard.serve(a.port)
    url = f"http://localhost:{a.port}"
    log(f"bot started - {', '.join(a.symbols)} - {'Alpaca PAPER' if alp else 'local fake money'} ${broker.cash:,.0f} - dashboard {url}")
    if not a.no_browser:
        webbrowser.open(url)

    while True:
        now = datetime.now(ET)
        if st["day"] != now.date():
            st.update(day=now.date(), halted=False, day_start=broker.equity(marks), trades_today=0)
            for sym in a.symbols:
                strat[sym].new_day(); seen[sym].clear(); opens.pop(sym, None)
                S["charts"][sym] = {"t": [], "c": [], "hod": [], "lod": [], "marks": []}
            log("new trading day - watching for setups")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
        for sym in a.symbols:
            if not (a.replay or feeds.market_open(sym)):
                continue
            try:
                bars = feeds.bars(sym, a.feed)
            except Exception as e:
                log(f"data error {sym}: {e}", "bad"); continue
            for b in bars:
                bt = datetime.fromisoformat(b.t.replace("Z", "+00:00"))
                if b.t in seen[sym] or (not a.replay and bt > cutoff):
                    continue
                seen[sym].add(b.t)
                marks[sym] = b.c; opens.setdefault(sym, b.o)
                t = bt.astimezone(ET).strftime("%H:%M")
                ch = S["charts"][sym]
                with L:
                    ch["t"].append(t); ch["c"].append(b.c)
                    ch["hod"].append(max(b.h, ch["hod"][-1]) if ch["hod"] else b.h)
                    ch["lod"].append(min(b.l, ch["lod"][-1]) if ch["lod"] else b.l)
                    for k in ("t", "c", "hod", "lod"):
                        del ch[k][:-600]
                sig = strat[sym].on_bar(b)
                if sig:
                    act(sym, b, sig, t)
                if not st["halted"] and broker.equity(marks) < st["day_start"] * (1 - a.max_loss):
                    st["halted"] = True
                    log("DAILY LOSS LIMIT HIT - no new trades today", "bad")
        mins = now.hour * 60 + now.minute
        for sym in a.symbols:     # ETFs: never hold overnight
            if not feeds.is_crypto(sym) and sym in marks and (a.replay or mins >= 950):
                close(sym, marks[sym], "end of day flatten", now.strftime("%H:%M"))
        if a.replay:
            for sym in a.symbols:
                if sym in marks: close(sym, marks[sym], "replay finished", now.strftime("%H:%M"))
        open_now = [s for s in a.symbols if feeds.market_open(s)]
        publish("Replay finished" if a.replay else "Halted for the day (loss limit)" if st["halted"] else
                f"Live - watching {len(open_now)} markets" if open_now else "Markets closed - waiting")
        if a.replay:
            while True: time.sleep(3600)
        time.sleep(60 - datetime.now().second + 3)


if __name__ == "__main__":
    main()
