"""Game-theory day-trading rules, translated to 1-minute bars.

The video's edge comes from reading the depth of market (DOM). Retail data feeds
don't give you a full order book, so each idea is approximated with bars + volume:

  1. Anticipate the breakout, don't chase it   -> enter while coiling just under the
     high of day (HOD); refuse entries more than CHASE_LIMIT past the break.
  2. Exit into resistance                       -> take profit at the next high-volume
     price (volume-profile node) or when momentum stalls after the run.
  3. Catch the 1st/2nd bounce after a flush     -> buy a reversal bar after a sharp,
     high-volume drop; skip the 3rd+ test of the same low ("they'll flush you").
  4. Shakeout time stop                         -> if a trade hasn't moved in
     SHAKEOUT_BARS minutes, scratch it near break-even.
  5. Mirror everything for shorts at the low of day.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Bar:
    t: str
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class Params:
    near_extreme_pct: float = 0.0015  # "close to HOD" = within 0.15%
    coil_bars: int = 6                # bars of tight range under the high
    coil_max_range_atr: float = 1.5   # coil must be tighter than this many ATRs
    chase_limit_atr: float = 0.5      # never enter more than this past the break
    flush_bars: int = 8
    flush_atr: float = 4.0            # drop of >= 4 ATR in flush_bars = a flush
    max_bounces: int = 2              # trade 1st and 2nd bounce, skip 3rd+
    stop_atr: float = 1.5
    target_atr: float = 3.0
    shakeout_bars: int = 6            # his rule: 5-6 min of no progress -> scratch
    atr_len: int = 14
    min_bars: int = 20                # let the opening range form first
    profile_tick: float = 0.0005      # volume-profile bucket = 0.05% of price (works for $50 ETFs and $90k BTC)


@dataclass
class Position:
    side: int          # +1 long, -1 short
    entry: float
    stop: float
    target: float
    bars_held: int = 0
    best: float = 0.0
    reason: str = ""


@dataclass
class Strategy:
    p: Params = field(default_factory=Params)
    bars: list = field(default_factory=list)
    profile: dict = field(default_factory=lambda: defaultdict(float))
    pos: Position | None = None
    bounce_low: float | None = None
    bounce_count: int = 0
    hod: float = float('-inf')
    lod: float = float('inf')

    # ---------- helpers ----------
    def atr(self):
        b = self.bars[-self.p.atr_len - 1:]
        trs = [max(x.h - x.l, abs(x.h - y.c), abs(x.l - y.c)) for y, x in zip(b, b[1:])]
        return sum(trs) / len(trs) if trs else 0.0

    def bucket(self, price):
        tick = self.bars[0].c * self.p.profile_tick
        return round(price / tick) * tick

    def next_volume_node(self, price, side):
        """Nearest price beyond `price` with heavy volume (top 20% of buckets) = resistance."""
        if not self.profile:
            return None
        vols = sorted(self.profile.values())
        heavy = vols[int(len(vols) * 0.8)]
        lvls = [k for k, v in self.profile.items() if v >= heavy and (k - price) * side > 0]
        return min(lvls, key=lambda k: abs(k - price)) if lvls else None

    # ---------- main loop ----------
    def on_bar(self, bar: Bar):
        """Feed one closed bar. Returns an action dict or None."""
        hod, lod = self.hod, self.lod  # HOD/LOD *before* this bar
        self.hod, self.lod = max(self.hod, bar.h), min(self.lod, bar.l)
        self.bars.append(bar)
        self.profile[self.bucket((bar.h + bar.l + bar.c) / 3)] += bar.v
        if len(self.bars) < self.p.min_bars:
            return None
        atr = self.atr() or 1e-9
        if self.pos:
            return self._manage(bar, atr)
        return self._breakout(bar, hod, lod, atr) or self._bounce(bar, atr)

    def _enter(self, side, price, stop, atr, reason):
        node = self.next_volume_node(price, side)
        tgt = price + side * self.p.target_atr * atr
        if node is not None and abs(node - price) > atr:   # exit into the next wall
            tgt = node if side * (node - tgt) < 0 else tgt
        self.pos = Position(side, price, stop, tgt, best=price, reason=reason)
        return {"action": "buy" if side > 0 else "sell", "price": price,
                "stop": round(stop, 4), "target": round(tgt, 4), "reason": reason}

    def _breakout(self, bar, hod, lod, atr):
        coil = self.bars[-self.p.coil_bars:]
        rng = max(b.h for b in coil) - min(b.l for b in coil)
        if rng > self.p.coil_max_range_atr * atr:
            return None
        for side, ext in ((1, hod), (-1, lod)):
            dist = (ext - bar.c) * side          # >0 = still before the break
            if -self.p.chase_limit_atr * atr <= dist <= ext * self.p.near_extreme_pct:
                lows = [b.l for b in coil] if side > 0 else [-b.h for b in coil]
                if lows[-1] >= min(lows[:-1]):   # higher lows (or lower highs) = pressure
                    stop = (min(b.l for b in coil) if side > 0 else max(b.h for b in coil))
                    stop -= side * 0.25 * atr
                    return self._enter(side, bar.c, stop, atr,
                                       "anticipate HOD break" if side > 0 else "anticipate LOD break")
        return None

    def _bounce(self, bar, atr):
        w = self.bars[-self.p.flush_bars - 1:-1]
        top, low = max(b.h for b in w), min(min(b.l for b in w), bar.l)
        avg_v = sum(b.v for b in self.bars[-40:]) / len(self.bars[-40:])
        flushed = top - low >= self.p.flush_atr * atr and max(b.v for b in w) > 1.5 * avg_v
        prev = self.bars[-2]
        reversal = bar.c > prev.h and bar.c > (bar.h + bar.l) / 2
        early = bar.c < low + 0.4 * (top - low)   # still near the low, not chasing the bounce
        if not (flushed and reversal and early):
            return None
        if self.bounce_low is None or abs(low - self.bounce_low) > atr:
            self.bounce_low, self.bounce_count = low, 0      # a new flush low
        self.bounce_count += 1
        if self.bounce_count > self.p.max_bounces:
            return None                                       # 3rd test: the trap
        return self._enter(1, bar.c, low - 0.25 * atr, atr, f"flush bounce #{self.bounce_count}")

    def _manage(self, bar, atr):
        p = self.pos
        p.bars_held += 1
        s = p.side
        p.best = max(p.best, bar.h) if s > 0 else min(p.best, bar.l)
        exit_px, why = None, None
        if (bar.l <= p.stop) if s > 0 else (bar.h >= p.stop):
            exit_px, why = p.stop, "stop"
        elif (bar.h >= p.target) if s > 0 else (bar.l <= p.target):
            exit_px, why = p.target, "target (into resistance)"
        elif (p.best - p.entry) * s > atr and (bar.c - self.bars[-2].c) * s < 0 \
                and (p.best - bar.c) * s > 0.5 * atr:
            exit_px, why = bar.c, "momentum stalled - take the money"
        elif p.bars_held >= self.p.shakeout_bars and (p.best - p.entry) * s < 0.5 * atr:
            exit_px, why = bar.c, "shakeout time-stop"
        if exit_px is None:
            return None
        self.pos = None
        return {"action": "exit", "price": exit_px, "pnl": round((exit_px - p.entry) * s, 4),
                "reason": why, "entry_reason": p.reason}

    def new_day(self):
        self.bars.clear(); self.profile.clear()
        self.pos = None; self.bounce_low = None; self.bounce_count = 0
        self.hod, self.lod = float('-inf'), float('inf')
