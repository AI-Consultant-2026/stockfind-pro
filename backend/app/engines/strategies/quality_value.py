"""Strategy 1 — "Great Company at a Good Price" (long-term investor scanner)."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    f, s = bundle["fundamental"], bundle["scores"]
    checklist = [
        ("Revenue growth positive", (f.get("revenue_growth_yoy") or 0) > 0),
        ("EPS growth positive", (f.get("eps_growth_yoy") or 0) > 0),
        ("FCF growth positive", (f.get("fcf_growth_yoy") or 0) > 0),
        ("High ROIC (>12%)", (f.get("roic") or 0) > 0.12),
        ("Strong margins (op margin >15%)", (f.get("operating_margin") or 0) > 0.15),
        ("Low/manageable debt", (f.get("leverage") or 1) < 0.55),
        ("Attractive valuation (Value score ≥55)", s["value"] >= 55),
    ]
    opportunity_score = 0.30 * s["quality"] + 0.25 * s["growth"] + 0.25 * s["value"] + 0.20 * s["cash_flow"]
    upside = f.get("upside_pct")
    headline = f"Fair value ~${f['fair_value']:.0f} vs price ${bundle['price']:.2f} ({upside:+.0f}% est. upside)" \
        if f.get("fair_value") and upside is not None else "Quality + valuation setup"
    return checklist_result(
        "quality_value", "Great Company at a Good Price", "🟢 VALUE + QUALITY ALERT",
        ["investor"], checklist, opportunity_score, qualify_threshold=5, headline=headline,
        gate_indices=(6,),  # must actually be attractively valued, not just high quality
    )
