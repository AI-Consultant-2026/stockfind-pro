"""Strategy 4 — "Fallen Angel". A stock that has fallen substantially but may
still have attractive fundamentals. Crucially, this does NOT auto-label it a
buy — it asks *why* the stock fell, distinguishing temporary setbacks
(earnings miss, sector sell-off, macro shock, guidance cut) from permanent
deterioration (competitive decline, accounting concerns, debt crisis,
regulatory threat) using the fundamentals trend and any negative catalysts."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    t, f, e, s = bundle["technical"], bundle["fundamental"], bundle["event"], bundle["scores"]
    if t.get("insufficient_data") or f.get("insufficient_data"):
        return checklist_result("fallen_angel", "Fallen Angel", "🟠 POTENTIAL RECOVERY",
                                 ["investor"], [], 0, qualify_threshold=99)

    drawdown = t["pct_from_52w_high"]  # negative number
    fell_substantially = drawdown <= -25

    fundamentals_healthy = (
        (f.get("revenue_growth_yoy") or -1) > 0.03
        and (f.get("eps_growth_yoy") or -1) > 0
        and (f.get("fcf_growth_yoy") or -1) > 0
    )
    debt_stable = (f.get("leverage") or 1) < 0.65

    permanent_concern_flags = [
        c for c in e.get("negative_catalysts", [])
    ]
    has_permanent_concern = len(permanent_concern_flags) > 0 or (f.get("roic") or 1) < 0.02

    checklist = [
        ("Fallen ≥25% from 52-week high", fell_substantially),
        ("Revenue still growing", (f.get("revenue_growth_yoy") or -1) > 0.03),
        ("EPS still growing", (f.get("eps_growth_yoy") or -1) > 0),
        ("FCF still growing", (f.get("fcf_growth_yoy") or -1) > 0),
        ("Debt stable/manageable", debt_stable),
        ("Estimated fair value above current price", (f.get("upside_pct") or -99) > 10),
        ("No permanent-deterioration red flags found", not has_permanent_concern),
    ]

    is_good_recovery = fell_substantially and fundamentals_healthy and debt_stable and not has_permanent_concern
    opportunity_score = 0.30 * s["quality"] + 0.30 * s["value"] + 0.25 * s["cash_flow"] + 0.15 * (100 - abs(drawdown))
    if has_permanent_concern:
        opportunity_score *= 0.55  # this looks like a value trap, not a recovery

    reason = "Likely temporary setback — fundamentals still healthy" if is_good_recovery else \
             ("⚠️ Possible permanent deterioration — treat with caution" if has_permanent_concern else "Mixed signals")
    headline = f"Down {drawdown:.0f}% from 52-week high. {reason}"

    result = checklist_result(
        "fallen_angel", "Fallen Angel", "🟠 POTENTIAL RECOVERY" if is_good_recovery else "🔴 VALUE TRAP RISK",
        ["investor"], checklist, opportunity_score, qualify_threshold=4, headline=headline,
        gate_indices=(0,),  # must actually have fallen ≥25% — this is a Fallen Angel, not just "cheap"
    )
    result["is_good_recovery"] = is_good_recovery
    result["has_permanent_concern"] = has_permanent_concern
    return result
