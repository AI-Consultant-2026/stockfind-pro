"""Strategy 6 — Institutional Accumulation. Looks for the *pattern* of
potential institutional buying (rising ownership, rising volume on up days,
uptrend, reduced selling pressure) rather than merely showing raw volume.

Important: institutional ownership data is inherently reported with a lag
(13F-style filings), so every value here is labeled with the period it was
actually reported for — the UI must show that explicitly, not imply it's
live."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    t, e, s = bundle["technical"], bundle["event"], bundle["scores"]
    if t.get("insufficient_data"):
        return checklist_result("institutional_accumulation", "Institutional Accumulation",
                                 "🏦 ACCUMULATION SIGNAL", ["investor", "swing"], [], 0, qualify_threshold=99)
    checklist = [
        ("Institutional ownership rising (reported)", (e.get("institutional_ownership_trend_pct") or 0) > 0.3),
        ("Increasing volume", t["volume_ratio"] > 1.05),
        ("Positive price trend", t["above_sma50"]),
        ("Relative strength positive", (t.get("rel_strength_63d") or 0) > 0),
        ("Breakout / near highs", t["pct_from_52w_high"] >= -12),
        ("Reduced selling pressure (RSI healthy, not oversold)", 40 <= t["rsi14"] <= 75),
    ]
    opportunity_score = 0.35 * s["momentum"] + 0.30 * s["quality"] + 0.20 * s["catalyst"] + 0.15 * s["risk"]
    own_pct = e.get("institutional_ownership_pct")
    as_of = e.get("institutional_ownership_as_of")
    headline = (f"Institutional ownership {own_pct:.1f}% as of {as_of} (reported, not real-time)"
                if own_pct is not None else "Accumulation pattern detected")
    result = checklist_result(
        "institutional_accumulation", "Institutional Accumulation", "🏦 ACCUMULATION SIGNAL",
        ["investor", "swing"], checklist, opportunity_score, qualify_threshold=4, headline=headline,
        gate_indices=(0,),  # reported institutional ownership must actually be rising
    )
    result["data_lag_notice"] = "Institutional ownership reflects the last reported filing period, not real time."
    return result
