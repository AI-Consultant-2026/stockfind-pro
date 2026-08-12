"""Strategy 8 — Short Squeeze / High Short Interest. Kept deliberately
separate from fundamental quality: a highly-shorted stock isn't automatically
a good investment, it's a distinct volatility/positioning setup for traders."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    t, e, company, s = bundle["technical"], bundle["event"], bundle["company"], bundle["scores"]
    if t.get("insufficient_data"):
        return checklist_result("short_squeeze", "Short Squeeze Watch", "🔥 SHORT SQUEEZE WATCH",
                                 ["active"], [], 0, qualify_threshold=99)
    short_pct = e.get("short_interest_pct_float")
    dtc = e.get("days_to_cover")
    float_shares = company.get("float_shares") or 0
    low_float = float_shares > 0 and float_shares < 150_000_000

    checklist = [
        ("High short interest (>15% of float)", (short_pct or 0) > 15),
        ("Rising price", (t.get("mom_21d") or 0) > 3),
        ("Increasing volume", t["volume_ratio"] > 1.3),
        ("Low/medium float", low_float),
        ("Elevated days-to-cover (>4)", (dtc or 0) > 4),
    ]
    opportunity_score = 0.45 * s["momentum"] + 0.35 * min(100, (short_pct or 0) * 3) + 0.20 * (100 - s["risk"])
    headline = (f"Short interest ~{short_pct:.1f}% of float, {dtc:.1f} days to cover"
                if short_pct is not None else "Elevated short-interest setup")
    result = checklist_result(
        "short_squeeze", "Short Squeeze Watch", "🔥 SHORT SQUEEZE WATCH",
        ["active"], checklist, opportunity_score, qualify_threshold=3, headline=headline,
        gate_indices=(0,),  # must actually have elevated short interest — the defining trait
    )
    result["note"] = "High short interest is a positioning/volatility signal, not a fundamental quality signal — kept separate deliberately."
    return result
