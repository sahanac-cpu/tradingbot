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


def _rsi(closes, n):
    gains = losses = 0.0
    for a_, b_ in zip(closes[-n - 1:], closes[-n:]):
        d = b_ - a_
        gains += max(d, 0); losses += max(-d, 0)
    return 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)


@dataclass
class RSIDip(Strategy):
    """Connors-style RSI(2): in an uptrend (above VWAP and rising 30-min average), a very
    short-term oversold reading (RSI-2 under 10) usually bounces. Exit on the bounce."""
    name = "RSI Dip"
    target_label = "target (RSI bounce)"
    p: Params = field(default_factory=lambda: replace(Params(), shakeout_bars=10))

    def entries(self, bar, hod, lod, atr):
        if len(self.bars) < 40:
            return None
        closes = [b.c for b in self.bars]
        rsi = _rsi(closes, 2)
        sma30, sma30_prev = statistics.fmean(closes[-30:]), statistics.fmean(closes[-35:-5])
        vw = self.vwap()
        if rsi < 10 and bar.c > vw and sma30 > sma30_prev and bar.c > bar.o:
            stop = bar.l - 1.0 * atr
            return self._enter(1, bar.c, stop, atr, "RSI-2 oversold in uptrend", target=bar.c + 1.5 * atr,
                               why=f"RSI(2) hit {rsi:.0f} (deeply oversold for a 2-bar window) while price stays above "
                                   f"VWAP ({vw:,.2f}) and the 30-min average is rising. Short, sharp dips inside an "
                                   "uptrend tend to get bought - a classic quant mean-reversion edge.")
        return None


@dataclass
class VWAPReclaim(Strategy):
    """Microstructure: VWAP is the price big institutions benchmark against. When price
    has been below it and reclaims it on rising volume, buyers have taken control."""
    name = "VWAP Reclaim"
    target_label = "target (back to day high)"

    def entries(self, bar, hod, lod, atr):
        if len(self.bars) < 45:
            return None
        vw = self.vwap()
        below = sum(1 for b in self.bars[-16:-1] if b.c < vw)
        avg_v = statistics.fmean(b.v for b in self.bars[-30:]) or 1
        if below >= 12 and self.bars[-2].c < vw < bar.c and bar.v > 1.3 * avg_v and hod - bar.c > 1.5 * atr:
            stop = min(b.l for b in self.bars[-5:]) - 0.3 * atr
            return self._enter(1, bar.c, stop, atr, "VWAP reclaim", target=hod,
                               why=f"Price spent {below} of the last 15 minutes below VWAP ({vw:,.2f}), then closed back "
                                   f"above it on {bar.v / avg_v:.1f}x volume. Institutions benchmark to VWAP, so a "
                                   "reclaim often means buyers took control; target is the day's high.")
        return None


@dataclass
class SqueezeBreakout(Strategy):
    """Volatility: when the Bollinger Bands contract inside the Keltner Channel the market
    is coiling ('squeeze'). Quiet periods tend to end in big moves - buy the upside release."""
    name = "Squeeze Breakout"
    target_label = "target (volatility expansion)"
    p: Params = field(default_factory=lambda: replace(Params(), shakeout_bars=12))
    was_squeezed: int = 0

    def entries(self, bar, hod, lod, atr):
        if len(self.bars) < 40:
            return None
        closes = [b.c for b in self.bars[-20:]]
        mid, sd = statistics.fmean(closes), statistics.pstdev(closes)
        squeezed = 2 * sd < 1.5 * atr            # Bollinger(2sd) inside Keltner(1.5 ATR)
        if squeezed:
            self.was_squeezed += 1
            return None
        streak, self.was_squeezed = self.was_squeezed, 0
        if streak >= 8 and bar.c > mid + 2 * sd and bar.c > self.vwap():
            stop = mid - 0.5 * atr
            return self._enter(1, bar.c, stop, atr, "squeeze release", target=bar.c + 3 * atr,
                               why=f"Volatility was compressed for {streak} minutes (Bollinger Bands inside the Keltner "
                                   "Channel), and price just broke out above the upper band and VWAP. Quiet markets "
                                   "tend to end in big moves; riding the release.")
        return None

    def new_day(self):
        super().new_day(); self.was_squeezed = 0


STRATEGIES = [Strategy, MeanReversion, Momentum, TrendPullback, RSIDip, VWAPReclaim, SqueezeBreakout]
