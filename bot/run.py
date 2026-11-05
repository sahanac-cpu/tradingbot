"""Real-time paper bot: 4 competing strategies, a daily champion, live dashboard, history.

    python -m bot.run --broker alpaca              # trade your Alpaca PAPER account
    python -m bot.run                              # local fake money only
    python -m bot.run --replay                     # replay today's bars now (any time)

How it works
  - Strategies: Game Theory (the transcript), Mean Reversion, Momentum, Trend Pullback.
  - Every strategy trades every symbol (ETFs + crypto) in its own SIMULATED $100k account.
  - Each morning the strategy with the best simulated P&L over the last 10 days becomes
    CHAMPION; only the champion's ETF trades are copied to your real paper account.
  - Every day is saved in history/ and shown on the dashboard, with a "why" for each trade.

Risk-averse real-account rules: long only, 0.25% of equity risked per trade, max 10% per
position, max 10 real trades a day, ETFs only 9:50-15:30 ET and flat by 15:50, no new
trades after -1% on the day. Crypto is simulation-only (fees are larger than 1-min moves).
"""
from __future__ import annotations
import argparse, json, os, re, time, webbrowser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .paper import PaperBroker
from . import feeds, dashboard, arena
from .quant import STRATEGIES
from .learner import Learner, features
from .review import Reviewer

ET = ZoneInfo("America/New_York")
ACCOUNT = "account.json"
DEFAULT = ["VOO", "SPY", "QQQ", "IWM", "DIA"]
CRYPTO_FEE = 0.0025
SIM_CAP = 3            # simulated trades per strategy per symbol per day
slug = lambda n: re.sub(r"\W+", "_", n.lower()).strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=DEFAULT)
    ap.add_argument("--watch", nargs="*", default=["BTC/USD", "ETH/USD"], help="simulation-only symbols")
    ap.add_argument("--feed", choices=["yahoo", "alpaca"], default="yahoo")
    ap.add_argument("--broker", choices=["local", "alpaca"], default="local")
    ap.add_argument("--cash", type=float, default=100_000)
    ap.add_argument("--risk", type=float, default=0.0025)
    ap.add_argument("--max-position", type=float, default=0.10)
    ap.add_argument("--max-trades", type=int, default=10)
    ap.add_argument("--max-loss", type=float, default=0.01)
    ap.add_argument("--champion", help="force a strategy to trade the real account (default: picked daily)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-learn", action="store_true")
    ap.add_argument("--no-backfill", action="store_true")
    a = ap.parse_args()
    from .envfile import load; load()
    a.symbols = [s.upper() for s in a.symbols]
    a.watch = [s.upper() for s in a.watch if s.upper() not in a.symbols]
    watch, allsyms = set(a.watch), a.symbols + a.watch
    names = [C.name for C in STRATEGIES]
    S, L = dashboard.STATE, dashboard.LOCK

    alp = None
    if a.broker == "alpaca":
        from . import alpaca_broker as alp
        a.cash = float(alp.account()["equity"])
    real = PaperBroker(a.cash)
    if os.path.exists(ACCOUNT) and not a.reset and not alp:
        acct = json.load(open(ACCOUNT))
        real.cash, real.start_cash = acct["cash"], acct["start_cash"]
    sims = {n: PaperBroker(100_000, log=f"arena_{slug(n)}.csv") for n in names}
    brains = {n: Learner(path="model.json" if n == names[0] else f"model_{slug(n)}.json") for n in names}
    reviewers = {n: Reviewer() for n in names}
    strat = {(n, s): C() for C in STRATEGIES for n in [C.name] for s in allsyms}
    meta, feats, n_today = {}, {}, {}
    owner, real_meta = {}, {}          # sym -> strategy holding the REAL position
    seen = {s: set() for s in allsyms}
    shown, marks, opens = {}, {}, {}
    st = {"halted": False, "day": None, "day_start": real.cash, "trades_today": 0,
          "champion": names[0], "note": ""}
    fee = lambda sym: CRYPTO_FEE if feeds.is_crypto(sym) else 0.0

    def log(msg, kind="info"):
        line = f"{datetime.now(ET):%H:%M:%S}  {msg}"
        print(line, flush=True)
        with L:
            S["log"] = (S["log"] + [{"m": line, "k": kind}])[-400:]

    def save_account():
        json.dump({"cash": real.cash, "start_cash": real.start_cash}, open(ACCOUNT, "w"))

    def save_day():
        if a.replay:
            return
        with L:
            trades, reviews = list(S["trades"]), list(S["reviews"])
        ex = [t for t in trades if t["side"] == "EXIT" and t["account"] == "real"]
        arena.save_day(str(st["day"]), {
            "date": str(st["day"]), "source": "live", "champion": st["champion"], "champion_note": st["note"],
            "trades": trades, "reviews": reviews, "arena": arena.arena_stats(trades),
            "real": {"pnl": round(sum(t["pnl"] for t in ex), 2), "n": len(ex), "wins": sum(t["pnl"] > 0 for t in ex)}})

    def record(n, sym, t, side, qty, px, pnl, reason, why, account):
        with L:
            S["trades"].append({"t": t, "sym": sym, "strategy": n, "account": account, "side": side, "qty": qty,
                                "px": px, "pnl": round(pnl, 2), "reason": reason, "why": why})
            S["charts"][sym]["marks"].append({"t": t, "px": px, "strategy": n, "account": account,
                                              "k": "buy" if side == "BUY" else "exit"})
        save_day()

    def add_review(r):
        if r:
            with L:
                S["reviews"].append(r)
            if r.get("real"):
                log(f"{r['sym']} REVIEW [{r['verdict'].upper()}] {r['lesson']}",
                    "win" if r["verdict"] in ("good", "ok") else "loss")
            save_day()

    # ---------------------------------------------------------------- trading
    def close(n, sym, px, reason, t):
        k = (n, sym)
        q, _ = sims[n].pos.get(sym, (0, 0))
        if q:
            pnl = sims[n].fill(sym, -q, px, reason, fee(sym))
            if k in feats:
                x = feats.pop(k)
                if not a.replay:
                    brains[n].learn(x, pnl > 0)
            record(n, sym, t, "EXIT", abs(q), px, pnl, reason, "", "sim")
            m = meta.pop(k, {})
            reviewers[n].start(sym, {"sym": sym, "strategy": n, "t_in": m.get("t", ""), "t_out": t,
                                     "setup": m.get("reason", ""), "entry": m.get("price", px), "exit": px,
                                     "stop": m.get("stop", px), "target": m.get("target", px), "pnl": round(pnl, 2),
                                     "why_out": reason, "above_high": m.get("above_high", 0),
                                     "real": owner.get(sym) == n, "sim": owner.get(sym) != n})
        if owner.get(sym) == n:
            rq, _ = real.pos.get(sym, (0, 0))
            if rq:
                if alp:
                    try: alp.exit_all(sym)
                    except Exception as e: log(f"{sym} Alpaca exit error: {e}", "bad")
                pnl = real.fill(sym, -rq, px, reason, fee(sym))
                record(n, sym, t, "EXIT", abs(rq), px, pnl, reason, "", "real")
                log(f"REAL {sym} EXIT {abs(rq):g} @ {px:,.2f}  P&L ${pnl:+,.2f}  [{n}] {reason}",
                    "win" if pnl > 0 else "loss")
                save_account()
            owner.pop(sym, None); real_meta.pop(sym, None)
        strat[k].pos = None

    def act(n, sym, b, sig, t):
        k, s = (n, sym), strat[(n, sym)]
        if sig["action"] == "exit":
            return close(n, sym, sig["price"], sig["reason"], t)
        crypto = feeds.is_crypto(sym)
        bt = datetime.fromisoformat(b.t.replace("Z", "+00:00")).astimezone(ET)
        mins = bt.hour * 60 + bt.minute
        if (sims[n].pos.get(sym, (0, 0))[0] or sig["action"] == "sell" or n_today.get(k, 0) >= SIM_CAP
                or (not crypto and not 590 <= mins <= 930)):
            s.pos = None; return
        x = features(s, sig, sym, mins - 570 if not crypto else mins)
        ok, prob, note = brains[n].decide(x)
        if not ok and not a.no_learn:
            s.pos = None
            if n == st["champion"] and sym not in watch:
                log(f"{sym} skipped by {n}'s learning filter ({note}): {sig['reason']}", "skip")
            return
        reason = f"{sig['reason']} · AI {prob:.0%}"
        eq = sims[n].equity(marks)
        risk_ps = max(abs(sig["price"] - sig["stop"]), 1e-9)
        qty = min(eq * a.risk / risk_ps, eq * a.max_position / sig["price"])
        qty = round(qty, 6) if crypto else int(qty)
        if qty * sig["price"] < 10:
            s.pos = None; return
        sims[n].fill(sym, qty, sig["price"], reason, fee(sym))
        meta[k] = dict(sig, t=t, reason=reason, above_high=-x["dist_extreme_atr"])
        feats[k] = x; n_today[k] = n_today.get(k, 0) + 1
        record(n, sym, t, "BUY", qty, sig["price"], 0, reason, sig.get("why", ""), "sim")
        # ---- copy the champion's trade to the real account
        if n != st["champion"] or sym in watch or owner.get(sym):
            return
        why_not = ("daily loss limit" if st["halted"] else
                   f"max {a.max_trades} real trades/day" if st["trades_today"] >= a.max_trades else None)
        if why_not:
            return log(f"{sym} champion signal not copied to real account ({why_not})", "skip")
        req = real.equity(marks)
        rq = int(min(req * a.risk / risk_ps, req * a.max_position / sig["price"]))
        if rq <= 0:
            return
        if alp:
            try:
                o = alp.enter(sym, rq, "buy", sig["stop"], sig["target"])
                rq = o.get("held_qty", rq)
            except Exception as e:
                return log(f"{sym} Alpaca rejected order: {e}", "bad")
        real.fill(sym, rq, sig["price"], reason)
        owner[sym], real_meta[sym] = n, meta[k]
        st["trades_today"] += 1
        record(n, sym, t, "BUY", rq, sig["price"], 0, reason, sig.get("why", ""), "real")
        log(f"REAL {sym} BUY {rq} @ {sig['price']:,.2f} stop {sig['stop']:,.2f} target {sig['target']:,.2f} "
            f"[{n}] - {sig.get('why', '')}", "entry")

    # ---------------------------------------------------------------- dashboard
    def publish(status):
        eq = real.equity(marks)
        with L:
            trades = list(S["trades"])
        ex = [x for x in trades if x["side"] == "EXIT" and x["account"] == "real"]
        today_ar = arena.arena_stats(trades)
        tot = arena.score_table(st["day"])
        board = []
        for n in names:
            t, d = today_ar[n], tot[n]
            board.append({"name": n, "today": t["pnl"], "n": t["n"], "win": round(100 * t["wins"] / t["n"]) if t["n"] else None,
                          "ten": round(d["pnl"] + t["pnl"], 2), "ten_n": d["n"] + t["n"], "days": d["days"] + 1,
                          "champion": n == st["champion"], "learned": brains[n].n,
                          "open": sum(1 for s_ in allsyms if sims[n].pos.get(s_, (0, 0))[0])})
        with L:
            S["status"], S["updated"] = status, datetime.now(ET).strftime("%H:%M:%S")
            S["broker"] = "Alpaca paper" if alp else "Local fake money"
            S["champion"] = {"name": st["champion"], "note": st["note"]}
            S["board"] = board
            S["strategies"] = names
            S["stats"] = {"n": len(ex), "win": round(100 * sum(x["pnl"] > 0 for x in ex) / len(ex)) if ex else None,
                          "trades_today": st["trades_today"], "max_trades": a.max_trades, "halted": st["halted"],
                          "risk": a.risk, "max_loss": a.max_loss}
            bn = st["champion"] or names[0]
            g = brains[bn]
            S["brain"] = {"n": g.n, "wins": g.wins, "min": g.min_samples, "off": a.no_learn, "name": bn,
                          "factors": [[f, round(w, 3)] for f, w in g.top_factors()]}
            S["equity"] = (S["equity"] + [{"t": datetime.now(ET).strftime("%m-%d %H:%M"), "v": round(eq, 2),
                                            "day": round(eq - st["day_start"], 2),
                                            "tot": round(eq - real.start_cash, 2)}])[-2000:]
            pos = []
            for sym, (q, avg) in real.pos.items():
                if q and sym in real_meta:
                    m = real_meta[sym]
                    pos.append({"sym": sym, "qty": q, "entry": avg, "last": marks.get(sym, avg), "account": "real",
                                "pnl": round(q * (marks.get(sym, avg) - avg), 2), "stop": m["stop"],
                                "target": m["target"], "reason": m["reason"], "strategy": owner.get(sym, "")})
            for n in names:
                for sym, (q, avg) in sims[n].pos.items():
                    if q and (n, sym) in meta:
                        m = meta[(n, sym)]
                        pos.append({"sym": sym, "qty": q, "entry": avg, "last": marks.get(sym, avg), "account": "sim",
                                    "pnl": round(q * (marks.get(sym, avg) - avg), 2), "stop": m["stop"],
                                    "target": m["target"], "reason": m["reason"], "strategy": n})
            S["positions"] = pos
            S["tickers"] = [{"sym": s_, "last": marks.get(s_), "open": opens.get(s_), "crypto": feeds.is_crypto(s_),
                             "live": a.replay or feeds.market_open(s_), "sim": s_ in watch} for s_ in allsyms]
            S["history"] = arena.summary()

    def new_day(now):
        if st["day"]:
            for n in names:                                    # close anything still open from yesterday
                for sym, (q, _) in list(sims[n].pos.items()):
                    if q and sym in marks:
                        close(n, sym, marks[sym], "day rollover", now.strftime("%H:%M"))
        for n in names:
            for r in reviewers[n].finish_all():
                add_review(r)
        st.update(day=now.date(), halted=False, day_start=real.equity(marks), trades_today=0)
        champ, _, note = arena.pick_champion(now.date())
        if a.champion:
            champ, note = a.champion, "chosen by you with --champion"
        st["champion"], st["note"] = champ, note
        n_today.clear()
        with L:
            S["trades"], S["reviews"] = [], []
        old = arena.load_day(str(now.date())) if not a.replay else None
        if old and old.get("source") == "live":                # restarted mid-day
            with L:
                S["trades"], S["reviews"] = old["trades"], old["reviews"]
            st["trades_today"] = sum(1 for x in old["trades"] if x["side"] == "BUY" and x["account"] == "real")
            log(f"restored {len(old['trades'])} trade records from earlier today")
        for k in strat:
            strat[k].new_day()
        for s_ in allsyms:
            seen[s_].clear(); opens.pop(s_, None); shown.pop(s_, None)
            S["charts"][s_] = {"t": [], "c": [], "hod": [], "lod": [], "marks": []}
        for x in S["trades"]:
            if x["sym"] in S["charts"]:
                S["charts"][x["sym"]]["marks"].append({"t": x["t"], "px": x["px"], "strategy": x["strategy"],
                                                       "account": x["account"], "k": "buy" if x["side"] == "BUY" else "exit"})
        log(f"new day - CHAMPION: {st['champion'] or 'none (sitting out)'} ({st['note']})")

    # ---------------------------------------------------------------- start
    for s_ in allsyms:
        S["charts"][s_] = {"t": [], "c": [], "hod": [], "lod": [], "marks": []}
    dashboard.serve(a.port)
    url = f"http://localhost:{a.port}"
    log(f"bot started - real: {', '.join(a.symbols)} | sim-only: {', '.join(a.watch) or '-'} | "
        f"{'Alpaca PAPER' if alp else 'local fake money'} ${real.cash:,.0f} | dashboard {url}")
    if not a.no_browser:
        webbrowser.open(url)
    if not a.replay and not a.no_backfill and len(arena.all_days()) < 3:
        log("back-filling the last 5 days so the leaderboard has history (one-time, ~1 min)...")
        try:
            arena.backfill(allsyms, 5, log)
        except Exception as e:
            log(f"backfill failed: {e}", "bad")

    started = datetime.now(timezone.utc)
    while True:
        now = datetime.now(ET)
        if st["day"] != now.date():
            new_day(now)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
        for sym in allsyms:
            if not (a.replay or feeds.market_open(sym)):
                if time.time() - shown.get(sym, 0) > 600:      # closed: show last session (display only)
                    shown[sym] = time.time()
                    try:
                        last = feeds.yahoo_bars(sym)
                    except Exception:
                        last = []
                    if last:
                        hod, lod = [], []
                        for b in last:
                            hod.append(max(b.h, hod[-1]) if hod else b.h); lod.append(min(b.l, lod[-1]) if lod else b.l)
                        with L:
                            S["charts"][sym].update(t=[datetime.fromisoformat(b.t).astimezone(ET).strftime("%H:%M") for b in last],
                                                    c=[b.c for b in last], hod=hod, lod=lod)
                        marks[sym], opens[sym] = last[-1].c, last[0].o
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
                    for key in ("t", "c", "hod", "lod"):
                        del ch[key][:-1500]
                warm = not a.replay and bt < started - timedelta(minutes=2)
                for n in names:
                    sig = strat[(n, sym)].on_bar(b)
                    add_review(reviewers[n].on_bar(sym, b))
                    if sig and warm:
                        strat[(n, sym)].pos = None   # warm-up on old bars: learn the day, don't trade it
                    elif sig:
                        act(n, sym, b, sig, t)
                if not st["halted"] and real.equity(marks) < st["day_start"] * (1 - a.max_loss):
                    st["halted"] = True
                    log("DAILY LOSS LIMIT HIT - no new real trades today", "bad")
        mins = now.hour * 60 + now.minute
        for sym in allsyms:
            if sym in marks and ((not feeds.is_crypto(sym) and mins >= 950) or a.replay):
                for n in names:
                    close(n, sym, marks[sym], "end of day flatten", now.strftime("%H:%M"))
        if a.replay:
            for n in names:
                for r in reviewers[n].finish_all():
                    add_review(r)
        etf_open = any(feeds.market_open(s_) for s_ in a.symbols if not feeds.is_crypto(s_))
        if a.replay:
            status = "Replay finished"
        elif st["halted"]:
            status = "Halted for the day (loss limit)"
        elif etf_open:
            status = f"Live - {len(names)} strategies on {len(allsyms)} symbols"
        else:
            nxt = now.replace(hour=9, minute=30, second=0, microsecond=0)
            while nxt <= now or nxt.weekday() >= 5:
                nxt = (nxt + timedelta(days=1)).replace(hour=9, minute=30)
            h, m = divmod(int((nxt - now).total_seconds() // 60), 60)
            status = f"Live - stock market opens in {h}h {m}m" + (f" · crypto simulating 24/7" if a.watch else "")
        publish(status)
        if a.replay:
            while True:
                time.sleep(3600)
        time.sleep(60 - datetime.now().second + 3)


if __name__ == "__main__":
    main()
