"""Strategy 5 — Undervalued Quality. High quality + strong growth + strong
balance sheet + low valuation. The favourite scanner for longer-term
investors, per the source doc."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    f, s = bundle["fundamental"], bundle["scores"]
    checklist = [
        ("Quality ≥ 70", s["quality"] >= 70),
        ("Growth ≥ 60", s["growth"] >= 60),
        ("Strong balance sheet (leverage < 0.45)", (f.get("leverage") or 1) < 0.45),
        ("Free cash flow score ≥ 60", s["cash_flow"] >= 60),
        ("Valuation ≥ 60 (cheap relative to fundamentals)", s["value"] >= 60),
    ]
    opportunity_score = 0.25 * s["quality"] + 0.20 * s["growth"] + 0.20 * s["cash_flow"] + \
        0.25 * s["value"] + 0.10 * s["momentum"]
    headline = f"Quality {s['quality']:.0f} · Growth {s['growth']:.0f} · Balance Sheet strong · Value {s['value']:.0f}"
    return checklist_result(
        "undervalued_quality", "Undervalued Quality", "⭐ HIGH-CONVICTION WATCHLIST",
        ["investor"], checklist, opportunity_score, qualify_threshold=4, headline=headline,
    )
