"""Quant strategies that compete with the Game Theory strategy. Each reuses the shared
engine in strategy.py (ATR, VWAP, stops, targets, time-stops) and only defines entries.
Every entry carries a plain-English `why`."""
from __future__ import annotations
import statistics
from dataclasses import dataclass, field, replace
from .strategy import Strategy, Params


@dataclass
class MeanReversion(Strategy):
    """Prices stretched far from their average tend to snap back (Bollinger / z-score).
    Buy when price closes 2+ standard deviations below its 20-min average, near VWAP
    (so it's a stretch, not a crash), and the bar turns up. Target: back to the average."""
    name = "Mean Reversion"
    target_label = "target (back to the mean)"
    p: Params = field(default_factory=lambda: replace(Params(), shakeout_bars=15))

    def entries(self, bar, hod, lod, atr):
        if len(self.bars) < 30:
            return None
        closes = [b.c for b in self.bars[-20:]]
        mid, sd = statistics.fmean(closes), statistics.pstdev(closes) or 1e-9
        z = (bar.c - mid) / sd
        vw = self.vwap()
        if z <= -2.0 and bar.c > bar.o and abs(bar.c - vw) / vw < 0.006 and mid - bar.c > atr:
            stop = min(b.l for b in self.bars[-3:]) - 0.5 * atr
            return self._enter(1, bar.c, stop, atr, "stretched below average", target=mid,
                               why=f"Price closed {abs(z):.1f} standard deviations below its 20-min average "
                                   f"({mid:,.2f}) and the bar turned green, while still near VWAP ({vw:,.2f}) - "
                                   "a short-term overreaction, not a collapse. Mean reversion: stretched prices "
                                   "usually snap back toward the average, which is the target.")
        return None


@dataclass
class Momentum(Strategy):
    """Opening-range breakout: once price breaks the first 15 minutes' high on strong
    volume and above VWAP, buyers are in control and moves tend to continue."""
    name = "Momentum"
    target_label = "target (momentum extension)"
    p: Params = field(default_factory=lambda: replace(Params(), target_atr=4.0, shakeout_bars=10))
    traded: bool = False

    def entries(self, bar, hod, lod, atr):
        n = 15
        if self.traded or len(self.bars) <= n + 1:
            return None
        orh = max(b.h for b in self.bars[:n])
        avg_v = statistics.fmean(b.v for b in self.bars[-30:]) or 1
        vw = self.vwap()
        if self.bars[-2].c <= orh < bar.c and bar.v > 1.5 * avg_v and bar.c > vw:
            self.traded = True
            stop = max(orh - 1.0 * atr, bar.c - 2.0 * atr)
            return self._enter(1, bar.c, stop, atr, "opening-range breakout",
                               target=bar.c + 4.0 * atr,
                               why=f"Price broke above the first {n} minutes' high ({orh:,.2f}) on "
                                   f"{bar.v / avg_v:.1f}x average volume and is above VWAP ({vw:,.2f}). "
                                   "Momentum: strong moves with volume behind them tend to keep going; "
                                   "stop goes back inside the range.")
        return None

    def new_day(self):
        super().new_day(); self.traded = False


@dataclass
class TrendPullback(Strategy):
    """Trend following: in an uptrend (fast EMA above slow EMA, price above VWAP), buy the
    dip when price pulls back to the fast EMA and bounces."""
    name = "Trend Pullback"
    target_label = "target (trend continuation)"

    def entries(self, bar, hod, lod, atr):
        if len(self.bars) < 40:
            return None
        e9, e21, vw = self.ema(9), self.ema(21), self.vwap()
        prev = self.bars[-2]
        if e9 > e21 and bar.c > vw and min(prev.l, bar.l) <= e9 < bar.c and bar.c > prev.h and (e9 - e21) > 0.2 * atr:
            stop = min(b.l for b in self.bars[-4:]) - 0.3 * atr
            risk = bar.c - stop
            return self._enter(1, bar.c, stop, atr, "pullback in uptrend", target=bar.c + 2 * risk,
                               why=f"Uptrend: 9-EMA ({e9:,.2f}) above 21-EMA ({e21:,.2f}) and price above VWAP. "
                                   "Price dipped to the 9-EMA and bounced over the prior bar's high - buying the "
                                   "dip in the direction of the trend, targeting 2x the risk.")
        return None


STRATEGIES = [Strategy, MeanReversion, Momentum, TrendPullback]
