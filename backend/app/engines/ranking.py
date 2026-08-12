"""
Ranking engine — combines every strategy match, signal convergence and the
factor scores into the final per-stock opportunity record: a Fundamental
Opportunity score, a Trading Opportunity score, and an Overall Signal —
worded as "meets your selected criteria and deserves further investigation",
never as a buy call (source doc §23).
"""
from __future__ import annotations

from datetime import date

from .strategies import evaluate_all
from .convergence import compute_convergence
from .ai_analyst import generate_explanation
from .scoring_utils import clip


def fundamental_opportunity_score(s: dict) -> float:
    return clip(0.30 * s["quality"] + 0.25 * s["growth"] + 0.25 * s["value"] + 0.20 * s["cash_flow"])


def trading_opportunity_score(s: dict) -> float:
    return clip(0.50 * s["momentum"] + 0.30 * s["catalyst"] + 0.20 * s["risk"])


def overall_signal(fundamental_opp: float, trading_opp: float, convergence_pct: float) -> dict:
    """Three tiers, calibrated against the simulated universe's actual score
    distribution (roughly top ~quartile / middle ~half / bottom ~quartile),
    matching the doc's "N high-conviction / N watch / N risk warnings" framing."""
    blended = 0.5 * fundamental_opp + 0.5 * trading_opp
    if blended >= 61 and convergence_pct >= 45:
        label, tier = "HIGH-CONVICTION WATCH", "green"
    elif blended < 43:
        label, tier = "RISK WARNING", "red"
    else:
        label, tier = "WATCH SETUP", "amber"
    return {"label": label, "tier": tier, "blended_score": round(blended, 1)}


def build_opportunity(bundle: dict, sector_momentum: float | None = None) -> dict:
    strategy_results = evaluate_all(bundle)
    qualifying = [r for r in strategy_results if r["qualifies"]]
    best = max(strategy_results, key=lambda r: r["opportunity_score"]) if strategy_results else None

    convergence = compute_convergence(bundle, sector_momentum)
    explanation = generate_explanation(bundle, convergence)

    fund_opp = fundamental_opportunity_score(bundle["scores"])
    trade_opp = trading_opportunity_score(bundle["scores"])
    signal = overall_signal(fund_opp, trade_opp, convergence["convergence_pct"])

    # top-level ranking score: prefer the strongest *qualifying* strategy so
    # genuine multi-signal setups float to the top; fall back to the blended
    # score for stocks that don't cleanly match any single strategy yet.
    if qualifying:
        top_strategy = max(qualifying, key=lambda r: r["opportunity_score"])
        display_score = top_strategy["opportunity_score"]
    else:
        top_strategy = best
        display_score = signal["blended_score"]

    return {
        "ticker": bundle["ticker"],
        "name": bundle["name"],
        "sector": bundle["sector"],
        "industry": bundle["industry"],
        "price": bundle["price"],
        "as_of": bundle["as_of"],
        "scores": bundle["scores"],
        "display_score": round(display_score, 1),
        "top_strategy": top_strategy,
        "qualifying_strategies": qualifying,
        "all_strategies": strategy_results,
        "fundamental_opportunity": round(fund_opp, 1),
        "trading_opportunity": round(trade_opp, 1),
        "overall_signal": signal,
        "convergence": convergence,
        "explanation": explanation,
        "sector_momentum": sector_momentum,
    }
