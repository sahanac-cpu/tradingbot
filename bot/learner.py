"""The bot's own brain: a small machine-learning model that runs entirely on your computer.

Every time the strategy finds a setup, the learner describes the market in numbers
(features), and when the trade closes it learns whether that kind of setup won or lost.
After enough trades it starts skipping setups it predicts will lose.

It's online logistic regression written in plain Python: no Claude, no internet, no
extra libraries. Its memory is saved in model.json, so it keeps learning across days.
"""
from __future__ import annotations
import json, math, os

FEATURES = ["bias", "breakout", "bounce", "short", "crypto", "dist_extreme_atr", "range_pos",
            "trend_30", "vol_ratio", "atr_pct", "minutes_open", "bounce_n", "reward_risk"]


def features(strategy, sig, sym, minutes_open):
    b = strategy.bars
    atr = strategy.atr() or 1e-9
    c = b[-1].c
    hod, lod = max(x.h for x in b), min(x.l for x in b)
    r = sig["reason"]
    v_now = sum(x.v for x in b[-5:]) / 5
    v_avg = sum(x.v for x in b[-60:]) / len(b[-60:]) or 1
    risk = abs(sig["price"] - sig["stop"]) or 1e-9
    return {
        "bias": 1.0,
        "breakout": 1.0 if "break" in r else 0.0,
        "bounce": 1.0 if "bounce" in r else 0.0,
        "short": 1.0 if sig["action"] == "sell" else 0.0,
        "crypto": 1.0 if "/" in sym else 0.0,
        "dist_extreme_atr": max(-5, min(5, (hod - c) / atr)),          # how far below the high
        "range_pos": (c - lod) / ((hod - lod) or 1e-9),                # 0 = at low, 1 = at high
        "trend_30": max(-5, min(5, (c - b[-min(30, len(b))].c) / atr)),  # recent direction
        "vol_ratio": min(5, v_now / v_avg),                            # is volume picking up?
        "atr_pct": min(5, 100 * atr / c),                              # how wild is the market
        "minutes_open": min(1, minutes_open / 390),                    # time of day
        "bounce_n": float(r.split("#")[-1]) if "#" in r else 0.0,
        "reward_risk": min(5, abs(sig["target"] - sig["price"]) / risk),
    }


class Learner:
    def __init__(self, path="model.json", lr=0.05, min_samples=30, threshold=0.45):
        self.path, self.lr, self.min_samples, self.threshold = path, lr, min_samples, threshold
        self.w = {f: 0.0 for f in FEATURES}
        self.n = self.wins = 0
        if os.path.exists(path):
            d = json.load(open(path))
            self.w.update(d["w"]); self.n, self.wins = d["n"], d["wins"]

    def predict(self, x):
        z = sum(self.w[f] * x.get(f, 0.0) for f in FEATURES)
        return 1 / (1 + math.exp(-max(-30, min(30, z))))

    def decide(self, x):
        """Returns (take_trade, win_probability, explanation)."""
        p = self.predict(x)
        if self.n < self.min_samples:
            return True, p, f"learning ({self.n}/{self.min_samples} trades seen)"
        return p >= self.threshold, p, f"model says {p:.0%} chance to win"

    def learn(self, x, won):
        p = self.predict(x)
        err = (1.0 if won else 0.0) - p
        for f in FEATURES:
            self.w[f] += self.lr * err * x.get(f, 0.0) - self.lr * 0.001 * self.w[f]  # small L2
        self.n += 1; self.wins += bool(won)
        json.dump({"w": self.w, "n": self.n, "wins": self.wins}, open(self.path, "w"), indent=1)

    def top_factors(self, k=4):
        return sorted(((f, w) for f, w in self.w.items() if f != "bias"), key=lambda t: -abs(t[1]))[:k]
