"""Post-trade review: after every exit the bot keeps watching that symbol for 15 more
minutes, then explains what happened in terms of the game-theory rules from the
"Trading is poker" transcript the strategy is built on."""
from __future__ import annotations

WATCH_BARS = 15

# Lines from the transcript each lesson is based on.
QUOTES = {
    "chase": "Anticipate the breakout before it happens. Don't chase too far after it happens.",
    "trap": "The market maker is working sell orders above the high ... it is essentially a pump and dump.",
    "flush": "They hit your bid and shove right through it ... flush those people out ... "
             "the market will turn, come back up.",
    "shakeout": "Within 30 seconds of you exiting the trade after holding it for 15 minutes, "
                "the market makes new highs and you miss the trade. This is by design.",
    "scratch": "If I sit in that trade for more than five or 6 minutes and it's still not going, "
               "I'll just chalk it up as a break even.",
    "third": "Try to anticipate the first, try to anticipate the second, probably avoid the third or "
             "fourth. It becomes less reliable the farther out it goes.",
    "knife": "Except on those very rare days when it's just a complete one-way street ... "
             "you have to anticipate the shorts taking their money off the table.",
    "early": "I'm exiting that trade and taking my money where I see it run into more resistance.",
    "good": "As soon as it shows signs of stopping, I exit and I take my money.",
    "close": "Day traders flatten before the close - no overnight risk.",
}


QUANT_QUOTES = {
    "Mean Reversion": "Prices stretched far from their average tend to snap back - unless a real trend has started.",
    "Momentum": "Strong moves with volume behind them tend to keep going - until the volume dries up.",
    "Trend Pullback": "The trend is your friend: buy dips in an uptrend, cut it fast if the trend breaks.",
}


def judge_quant(r, after):
    n = r.get("strategy", "")
    entry, exitp, stop, target = r["entry"], r["exit"], r["stop"], r["target"]
    risk = max(entry - stop, 1e-9)
    hi = max(after) if after else exitp
    lo = min(after) if after else exitp
    won, why = r["pnl"] > 0, r["why_out"]
    if "end of day" in why or "rollover" in why or "finished" in why:
        return ("ok" if won else "loss", "Closed at the end of the day as planned.")
    if why == "stop" and hi >= target:
        return ("mistake", f"Stopped out, then price reached the target within {WATCH_BARS} min - stop too tight for this market's noise.")
    if why == "stop":
        lessons = {"Mean Reversion": "Price kept falling instead of snapping back - this was a trend day, and mean reversion loses on trend days.",
                   "Momentum": "False breakout: price broke the opening range but buyers didn't follow through.",
                   "Trend Pullback": "The dip kept going - the uptrend broke rather than continued."}
        return ("loss", lessons.get(n, "Normal loss - the stop kept it small."))
    if "time-stop" in why:
        return (("mistake", "Gave up too early - the move came after the time-stop.") if hi >= target
                else ("ok", "Good scratch - nothing happened, got out near break-even."))
    if won and hi > target + risk:
        return ("ok", f"Won, but price kept going {(hi - exitp) / risk:.1f}R past the exit - a trailing stop would have caught more.")
    if won:
        return ("good", "Worked as designed: entry signal, then the target was hit.")
    return ("loss", "Small loss after momentum faded.")


def judge(r, after):
    """r = closed trade info, after = closes of the next bars. Returns (verdict, lesson, quote_key)."""
    entry, exitp, stop, target = r["entry"], r["exit"], r["stop"], r["target"]
    risk = max(entry - stop, 1e-9)
    hi = max(after) if after else exitp
    lo = min(after) if after else exitp
    won = r["pnl"] > 0
    setup, why = r["setup"], r["why_out"]
    hit_target_after = hi >= target
    if "end of day" in why or "flatten" in why or "finished" in why:
        return ("ok" if won else "loss", "Closed at the end of the day as planned.", "close")
    if "break" in setup and r.get("above_high", 0) > 0.25 and not won:
        return ("mistake", f"Bought {r['above_high']:.1f}x the average bar range ABOVE the day's high - "
                "that's chasing, the move was already spent.", "chase")
    if why == "stop":
        if hit_target_after:
            return ("mistake", "Stopped out, then price ran back up to the target within "
                    f"{WATCH_BARS} min. The stop sat where everyone's stop sits and got flushed - "
                    "stop was too tight for this move.", "flush")
        if "break" in setup:
            return ("loss", "Fake breakout: price pushed to the high and got sold into, then fell. "
                    "Classic stop-run trap - market makers exiting into breakout buyers.", "trap")
        if "#2" in setup or "#3" in setup:
            return ("loss", "The later bounce failed - each test of the same low is less reliable.", "third")
        if lo < stop - risk:
            return ("loss", "Caught a falling knife: selling hadn't run out of steam, price kept "
                    "dropping after the stop (a one-way day).", "knife")
        return ("loss", "Normal loss - the setup was valid and the stop did its job (small, controlled).", "good")
    if "shakeout" in why:
        if hit_target_after:
            return ("mistake", "Shaken out: the bot gave up and the move came right after. "
                    "This is the shakeout he describes - they wait you out.", "shakeout")
        return ("ok", "Good scratch - the trade went nowhere and the time-stop got out near break-even.", "scratch")
    if won and hi > target + risk:
        return ("ok", f"Won, but price kept running {(hi - exitp) / risk:.1f}R past the exit. "
                "Fine by his rule (take money at resistance), but a trailing stop would have caught more.", "early")
    if won:
        return ("good", "Played by the book: entered early, sold into resistance.", "good")
    return ("loss", "Small loss after momentum stalled.", "good")


class Reviewer:
    def __init__(self):
        self.pending = {}   # sym -> review dict waiting for after-bars

    def start(self, sym, info):
        info["after"] = []
        self.pending[sym] = info

    def on_bar(self, sym, bar):
        """Feed every new bar; returns a finished review or None."""
        r = self.pending.get(sym)
        if not r:
            return None
        r["after"].append(bar.h); r["after"].append(bar.l)
        if len(r["after"]) >= 2 * WATCH_BARS:
            return self.finish(sym)
        return None

    def finish(self, sym):
        r = self.pending.pop(sym, None)
        if not r:
            return None
        after = r.pop("after")
        if r.get("strategy", "Game Theory") != "Game Theory":
            v, lesson = judge_quant(r, after)
            r.update(verdict=v, lesson=lesson, quote=QUANT_QUOTES.get(r["strategy"], ""))
        else:
            v, lesson, q = judge(r, after)
            r.update(verdict=v, lesson=lesson, quote=QUOTES[q])
        return r

    def finish_all(self):
        return [self.finish(s) for s in list(self.pending)]
