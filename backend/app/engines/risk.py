"""Risk score — 0-100 where HIGHER = LOWER risk (safer), kept on the same
"higher is better / green-amber-red" convention as every other sub-score so
the dashboard's color thresholds mean the same thing everywhere. Blends
volatility, leverage, valuation extremity, beta and short-interest exposure."""
from __future__ import annotations

from .scoring_utils import band, weighted_avg


def compute_risk_score(tech: dict, fund: dict, event: dict, beta: float) -> float:
    parts = []
    if not tech.get("insufficient_data"):
        parts.append((band(tech["hist_vol_21d"], 0.15, 0.75, invert=True), 1.2))
        parts.append((band(tech["atr_pct"], 1.0, 7.0, invert=True), 0.8))
    if not fund.get("insufficient_data"):
        parts.append((band(fund["leverage"], 0.15, 0.85, invert=True), 1.0))
        parts.append((band(fund["pe"], 10, 65, invert=True, default=55), 0.6))
    parts.append((band(beta, 0.6, 2.2, invert=True), 0.7))
    dtc = event.get("days_to_cover")
    if dtc is not None:
        parts.append((band(dtc, 2, 12, invert=True), 0.5))
    return weighted_avg(parts) if parts else 50.0
