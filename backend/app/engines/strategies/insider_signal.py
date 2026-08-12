"""Strategy 7 — Insider Signal. Multiple insiders buying around the same
period is treated as the strongest version of this signal. Insider selling is
NOT automatically treated as bearish (executives sell for many reasons)."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    e, s = bundle["event"], bundle["scores"]
    buyers = e.get("insider_distinct_buyers_180d", 0)
    checklist = [
        ("Insider purchases present (180d)", e.get("insider_buy_value_180d", 0) > 0),
        ("Multiple insiders buying (cluster)", e.get("insider_cluster_buying", False)),
        ("Net insider activity positive", e.get("insider_buy_value_180d", 0) > e.get("insider_sell_value_180d", 0)),
        ("3+ distinct insider buyers", buyers >= 3),
    ]
    opportunity_score = 0.40 * s["catalyst"] + 0.30 * s["quality"] + 0.30 * s["momentum"]
    if not e.get("insider_cluster_buying"):
        opportunity_score *= 0.6
    headline = (f"{buyers} distinct insiders bought in the last 180 days"
                if buyers > 0 else "No notable recent insider buying")
    result = checklist_result(
        "insider_signal", "Insider Signal", "🟢 INSIDER ACCUMULATION",
        ["investor"], checklist, opportunity_score, qualify_threshold=3, headline=headline,
        gate_indices=(0,),  # some insider buying must actually be present
    )
    result["note"] = "Insider selling is not treated as bearish on its own — executives sell for many routine reasons."
    return result
