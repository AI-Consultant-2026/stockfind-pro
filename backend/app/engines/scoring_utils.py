"""Shared normalization helpers used by every scoring engine.

Every sub-score in StockFind Pro is deliberately deterministic: a metric is
mapped into a 0-100 band via a fixed, documented rubric. There is no ML model
and no LLM anywhere in this path — see engines/ai_analyst.py for where
natural-language explanation (not scoring) happens, on top of these numbers.
"""
from __future__ import annotations


def clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def band(value: float | None, lo: float, hi: float, invert: bool = False, default: float = 50.0) -> float:
    """Linearly map value in [lo, hi] -> [0, 100]. If invert, lower raw value = higher score
    (used for valuation multiples and risk-negative metrics where "lower is better")."""
    if value is None:
        return default
    if hi == lo:
        return default
    pct = (value - lo) / (hi - lo)
    pct = max(0.0, min(1.0, pct))
    score = pct * 100
    return clip(100 - score) if invert else clip(score)


def weighted_avg(pairs: list[tuple[float, float]]) -> float:
    """pairs of (score, weight)."""
    total_w = sum(w for _, w in pairs) or 1.0
    return clip(sum(s * w for s, w in pairs) / total_w)
