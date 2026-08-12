"""Momentum score — turns technical.py's raw indicators into a single 0-100
Momentum sub-score, matching the doc's Momentum Breakout criteria (trend,
volume confirmation, relative strength, RSI not overextended, MACD)."""
from __future__ import annotations

from .scoring_utils import band, weighted_avg, clip


def rsi_quality(rsi: float) -> float:
    """Best momentum-quality RSI is a healthy uptrend (55-75), not yet
    'excessively extended' (>85) and not weak (<40)."""
    if rsi is None:
        return 50.0
    score = 100 - abs(rsi - 65) * 1.8
    if rsi > 82:
        score -= (rsi - 82) * 2.5  # extra penalty once genuinely extended
    return clip(score)


def compute_momentum_score(tech: dict) -> float:
    if tech.get("insufficient_data"):
        return 50.0

    trend_pts = sum([tech["above_sma20"], tech["above_sma50"], tech["above_sma200"]]) / 3 * 100

    return weighted_avg([
        (trend_pts, 1.3),
        (100 if tech["higher_highs"] else 35, 0.8),
        (rsi_quality(tech["rsi14"]), 1.0),
        (75 if tech["macd_bullish"] else 30, 0.9),
        (band(tech["mom_63d"], -15, 25), 1.2),
        (band(tech["mom_126d"], -20, 35, default=50), 0.8),
        (band(tech["rel_strength_63d"], -15, 15, default=50), 1.1),
        (band(tech["volume_ratio"], 0.6, 2.2), 0.7),
        (band(tech["volume_acceleration"], 0.7, 2.0), 0.6),
        (band(tech["trend_strength"], 20, 90), 0.7),
        (band(tech["pct_from_52w_high"], -25, 0), 0.6),
    ])
