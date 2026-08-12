"""
AI Analyst — explains, it does not score. Per the source doc §19: "The AI
should NOT determine the score." All numbers here come from the deterministic
quant engines above; this module only turns those already-computed numbers
into plain-language WHY / WHY NOT bullets, a one-line narrative, a headline
"main concern", and a 0-10 setup-quality rating — a template over real data,
not a model inventing a signal.

To upgrade this to a real LLM-backed writer later: keep every quantitative
score exactly as computed here, and replace `generate_explanation`'s bullet
templating with a call that passes this same structured dict to a language
model purely to phrase it more fluently — never to change or infer any of
the underlying numbers.
"""
from __future__ import annotations

from .scoring_utils import clip

SIGNAL_WHY = {
    "Strong fundamentals": "Fundamentals are strong",
    "Strong valuation": "Valuation is attractive relative to growth and quality",
    "Strong momentum": "Price momentum and trend are strong",
    "Positive earnings surprise": "Recent earnings beat expectations",
    "Increasing volume": "Trading volume is expanding, suggesting real demand",
    "Strong sector": "The sector is currently outperforming the broad market",
    "Cash flow strength": "Free cash flow generation is strong",
    "Active catalyst": "There is an active, well-evidenced catalyst",
    "Insider activity positive": "Insider buying activity is net positive",
    "Risk contained": "Volatility and leverage are within a comfortable range",
}
SIGNAL_WHY_NOT = {
    "Strong fundamentals": "Fundamentals are middling, not clearly strong",
    "Strong valuation": "Valuation looks stretched relative to fundamentals",
    "Strong momentum": "Momentum is weak or fading",
    "Positive earnings surprise": "No recent positive earnings surprise",
    "Increasing volume": "Volume isn't confirming the move",
    "Strong sector": "The sector itself isn't currently a leader",
    "Cash flow strength": "Free cash flow generation is weak",
    "Active catalyst": "No strong near-term catalyst identified",
    "Insider activity positive": "No notable positive insider activity",
    "Risk contained": "Elevated volatility/leverage raises the risk profile",
}

MAIN_CONCERN_ORDER = [
    ("value", "Valuation is demanding."),
    ("risk", "Risk profile (volatility/leverage) is elevated."),
    ("momentum", "Momentum has not yet confirmed."),
    ("catalyst", "No strong near-term catalyst is currently active."),
    ("cash_flow", "Free cash flow generation is thin."),
    ("quality", "Underlying business quality is unproven."),
    ("growth", "Growth has slowed."),
]


def generate_explanation(bundle: dict, convergence: dict) -> dict:
    s = bundle["scores"]
    t = bundle["technical"]

    why = [SIGNAL_WHY[sig["label"]] for sig in convergence["signals"] if sig["positive"]]
    why_not = [SIGNAL_WHY_NOT[sig["label"]] for sig in convergence["signals"] if not sig["positive"]]

    if not t.get("insufficient_data"):
        if t["rsi14"] > 78:
            why_not.append(f"RSI is elevated ({t['rsi14']:.0f}) — may be short-term overbought")
        if t["hist_vol_21d"] > 0.45:
            why_not.append("Volatility is elevated versus historical norms")

    # main concern = the lowest-scoring dimension that isn't risk-inverted oddly
    score_map = {"value": s["value"], "risk": s["risk"], "momentum": s["momentum"],
                 "catalyst": s["catalyst"], "cash_flow": s["cash_flow"], "quality": s["quality"],
                 "growth": s["growth"]}
    weakest_key = min(score_map, key=lambda k: score_map[k])
    main_concern = dict(MAIN_CONCERN_ORDER)[weakest_key]

    top_reasons = [r[0].lower() + r[1:] for r in why[:3]]
    if len(top_reasons) > 1:
        reason_text = ", ".join(top_reasons[:-1]) + " and " + top_reasons[-1]
    elif top_reasons:
        reason_text = top_reasons[0]
    else:
        reason_text = None

    if reason_text:
        narrative = f"The score is high because {reason_text}. Main concern: {main_concern}"
    else:
        narrative = f"No strong independent signals currently line up for this stock. Main concern: {main_concern}"

    setup_quality = clip(convergence["convergence_pct"] / 100 * 7 + s["risk"] / 100 * 3, 0, 10)

    return {
        "why": why,
        "why_not": why_not,
        "narrative": narrative,
        "main_concern": main_concern,
        "setup_quality_10": round(setup_quality, 1),
    }
