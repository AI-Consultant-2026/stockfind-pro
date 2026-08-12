"""Strategy 3 — Earnings Momentum. Fundamental information and market
behaviour agreeing: beat + guidance + positive reaction + volume + revisions."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    e, t, s = bundle["event"], bundle["technical"], bundle["scores"]
    fund = bundle["fundamental"]
    checklist = [
        ("EPS beat expectations", (e.get("eps_beat_pct") or -99) > 0),
        ("Revenue beat expectations", (e.get("revenue_beat_pct") or -99) > 0),
        ("Guidance raised or maintained", e.get("guidance_change") in ("raised", "maintained")),
        ("Stock reacted positively to earnings", (e.get("earnings_price_reaction_pct") or -99) > 0),
        ("Volume increased on the move", (not t.get("insufficient_data")) and t["volume_ratio"] > 1.2),
        ("Analyst estimates revised upward", fund.get("analyst_revision") == "up"),
    ]
    opportunity_score = 0.35 * s["catalyst"] + 0.30 * s["momentum"] + 0.25 * s["growth"] + 0.10 * s["quality"]
    headline = (f"EPS beat {e['eps_beat_pct']:+.1f}%, guidance {e.get('guidance_change') or 'n/a'}"
                if e.get("eps_beat_pct") is not None else "Recent earnings reaction")
    return checklist_result(
        "earnings_momentum", "Earnings Momentum", "🚀 EARNINGS MOMENTUM",
        ["swing"], checklist, opportunity_score, qualify_threshold=5, headline=headline,
        gate_indices=(0,),  # must have actually beaten on EPS
    )
