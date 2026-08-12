"""Strategy 9 — Mean Reversion. The critical distinction per the source doc:
"oversold + fundamentally healthy" is the opportunity, plain "oversold" is
not — a stock down 40% because the business is collapsing isn't automatically
a buy just because it's statistically stretched."""
from __future__ import annotations

from .common import checklist_result


def evaluate(bundle: dict) -> dict:
    t, f, s = bundle["technical"], bundle["fundamental"], bundle["scores"]
    if t.get("insufficient_data") or f.get("insufficient_data"):
        return checklist_result("mean_reversion", "Mean Reversion", "🟠 OVERSOLD + HEALTHY",
                                 ["swing"], [], 0, qualify_threshold=99)

    oversold = t["rsi14"] < 35 or t["bb_pct"] < 0.1 or (t.get("mom_21d") or 0) < -12
    fundamentally_healthy = (
        (f.get("revenue_growth_yoy") or -1) > 0
        and (f.get("eps_growth_yoy") or -1) > -0.05
        and (f.get("roic") or 0) > 0.06
    )
    checklist = [
        ("Oversold by at least one measure (RSI/Bollinger/21d move)", oversold),
        ("RSI oversold (<35)", t["rsi14"] < 35),
        ("Below lower Bollinger Band", t["bb_pct"] < 0.1),
        ("Sharp recent pullback (21d < -12%)", (t.get("mom_21d") or 0) < -12),
        ("Deviation from moving average is unusual (ATR-scaled)", t["atr_pct"] > 2.5),
        ("Fundamentals still healthy (growth + ROIC intact)", fundamentally_healthy),
    ]
    opportunity_score = 0.45 * s["quality"] + 0.25 * (100 - t["rsi14"]) + 0.15 * s["value"] + 0.15 * s["cash_flow"]
    if not fundamentally_healthy:
        opportunity_score *= 0.45  # this is "just oversold", the doc's explicit non-opportunity case

    verdict = "Oversold + fundamentally healthy" if (oversold and fundamentally_healthy) else \
              ("Oversold, but fundamentals are weak — not the same thing" if oversold else "Not currently oversold")
    headline = verdict
    result = checklist_result(
        "mean_reversion", "Mean Reversion", "🟠 OVERSOLD + HEALTHY" if fundamentally_healthy else "🔴 OVERSOLD ONLY",
        ["swing"], checklist, opportunity_score, qualify_threshold=3, headline=headline,
        gate_indices=(0, 5),  # must actually be oversold AND fundamentals must actually be healthy
    )
    result["fundamentally_healthy"] = fundamentally_healthy
    return result
