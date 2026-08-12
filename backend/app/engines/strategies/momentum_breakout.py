"""Strategy 2 — Momentum Breakout Finder. Asks "is there evidence of
institutional-quality demand behind the move?", not just "price went up"."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    t, s = bundle["technical"], bundle["scores"]
    if t.get("insufficient_data"):
        return checklist_result("momentum_breakout", "Momentum Breakout", "🔥 BREAKOUT WATCH",
                                 ["swing"], [], 0, qualify_threshold=99)
    checklist = [
        ("Price above 20-day MA", t["above_sma20"]),
        ("Price above 50-day MA", t["above_sma50"]),
        ("Price above 200-day MA", t["above_sma200"]),
        ("Making higher highs", t["higher_highs"]),
        ("Near/above 52-week high (within 8%)", t["pct_from_52w_high"] >= -8),
        ("Volume > 20-day average", t["volume_ratio"] > 1.0),
        ("Volume expansion (accelerating)", t["volume_acceleration"] > 1.2),
        ("RSI not excessively extended (<82)", t["rsi14"] < 82),
        ("MACD trend confirmation", t["macd_bullish"]),
        ("Outperforming the market (63d rel. strength > 0)", (t.get("rel_strength_63d") or 0) > 0),
    ]
    opportunity_score = 0.55 * s["momentum"] + 0.20 * s["catalyst"] + 0.15 * s["quality"] + 0.10 * s["risk"]
    headline = f"{t['volume_ratio']:.1f}x average volume, {t.get('mom_63d') or 0:+.0f}% over 63 sessions"
    return checklist_result(
        "momentum_breakout", "Momentum Breakout Finder", "🔥 BREAKOUT WATCH",
        ["swing"], checklist, opportunity_score, qualify_threshold=7, headline=headline,
        gate_indices=(1, 4),  # must actually be above the 50-day MA and near its 52-week high
    )
