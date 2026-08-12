"""
Fundamental engine — growth, quality, valuation and cash-flow calculations
from point-in-time quarterly fundamentals. Deterministic rubric-based scoring
(see scoring_utils.band): every metric is mapped through a fixed, documented
band rather than a percentile-vs-live-universe rank, so scores are stable and
explainable even though our simulated universe is small.
"""
from __future__ import annotations

from .scoring_utils import band, weighted_avg, clip


def _yoy(history: list[dict], field: str) -> float | None:
    """Year-over-year growth using the quarter 4 periods back (avoids seasonality)."""
    if len(history) < 5:
        return None
    latest = history[-1][field]
    prior = history[-5][field]
    if prior in (None, 0):
        return None
    return (latest - prior) / abs(prior)


def compute_fundamental_metrics(history: list[dict], latest_price: float | None,
                                 latest_estimate: dict | None) -> dict:
    """Returns raw fundamental metrics + Quality/Growth/Value/CashFlow sub-scores (0-100)."""
    if not history:
        return {"insufficient_data": True}

    latest = history[-1]
    rev_growth = _yoy(history, "revenue")
    eps_growth = _yoy(history, "eps")
    fcf_growth = _yoy(history, "fcf")

    gross_margin = latest["gross_margin"]
    operating_margin = latest["operating_margin"]
    roic = latest["roic"]
    roe = latest["roe"]
    debt = latest["debt"] or 0.0
    cash = latest["cash"] or 0.0
    revenue = latest["revenue"] or 0.0
    fcf = latest["fcf"] or 0.0
    shares_out = latest["shares_outstanding"] or 1.0

    leverage = debt / (debt + cash) if (debt + cash) else 0.0
    fcf_margin = fcf / revenue if revenue else 0.0

    # trailing-4-quarter EPS / revenue / FCF for valuation multiples
    last4 = history[-4:] if len(history) >= 4 else history
    ttm_eps = sum(q["eps"] for q in last4)
    ttm_revenue = sum(q["revenue"] for q in last4)
    ttm_fcf = sum(q["fcf"] for q in last4)

    market_cap = (latest_price or 0) * shares_out
    pe = (latest_price / ttm_eps) if (latest_price and ttm_eps and ttm_eps > 0) else None
    forward_eps = latest_estimate["eps_estimate"] * 4 if latest_estimate and latest_estimate.get("eps_estimate") else None
    forward_pe = (latest_price / forward_eps) if (latest_price and forward_eps and forward_eps > 0) else None
    peg = (pe / (eps_growth * 100)) if (pe and eps_growth and eps_growth > 0) else None
    # EBITDA proxy: operating income * 1.15 (adds back a typical D&A load) — a proxy since
    # granular D&A isn't part of this simulated dataset; documented approximation.
    ebitda_ttm = operating_margin * ttm_revenue * 1.15 if operating_margin else None
    ev = market_cap + debt - cash
    ev_ebitda = (ev / ebitda_ttm) if (ebitda_ttm and ebitda_ttm > 0 and market_cap) else None
    price_fcf = (market_cap / ttm_fcf) if (ttm_fcf and ttm_fcf > 0 and market_cap) else None
    fcf_yield = (ttm_fcf / market_cap * 100) if (market_cap and ttm_fcf) else None
    price_sales = (market_cap / ttm_revenue) if (ttm_revenue and market_cap) else None

    # ---- sub-scores -------------------------------------------------------
    quality_score = weighted_avg([
        (band(gross_margin, 0.10, 0.70), 1.0),
        (band(operating_margin, -0.05, 0.35), 1.2),
        (band(roic, -0.05, 0.30), 1.4),
        (band(roe, -0.10, 0.35), 1.0),
        (band(leverage, 0.15, 0.85, invert=True), 1.0),
    ])

    growth_score = weighted_avg([
        (band(rev_growth, -0.10, 0.30), 1.2),
        (band(eps_growth, -0.20, 0.40), 1.3),
        (band(fcf_growth, -0.20, 0.35), 1.0),
    ])
    if latest_estimate:
        revision = latest_estimate.get("revision_direction")
        if revision == "up":
            growth_score = clip(growth_score + 4)
        elif revision == "down":
            growth_score = clip(growth_score - 6)

    value_score = weighted_avg([
        (band(pe, 8, 45, invert=True, default=50), 1.0),
        (band(peg, 0.5, 3.0, invert=True, default=50), 1.0),
        (band(ev_ebitda, 5, 30, invert=True, default=50), 1.0),
        (band(price_fcf, 8, 40, invert=True, default=50), 1.0),
        (band(price_sales, 0.5, 12, invert=True, default=50), 0.7),
    ])

    cash_flow_score = weighted_avg([
        (band(fcf_margin, 0.0, 0.28), 1.3),
        (band(fcf_growth, -0.20, 0.35), 1.0),
        (band(fcf_yield, 0.0, 9.0, default=50), 0.9),
        (band(cash / debt if debt else 5.0, 0.2, 3.0), 0.6),
    ])

    # ---- deterministic "fair value" heuristic ------------------------------
    # A justified-multiple estimate: a stock earns a higher fair P/E the more
    # growth and quality it has (bounded 8x-45x), applied to trailing EPS.
    # This is a simple, transparent quant heuristic for the "Margin of Safety"
    # calculation the source doc calls for — explicitly NOT a DCF or ML model,
    # just a documented formula so the number is always explainable.
    fair_value = None
    upside_pct = None
    if ttm_eps and ttm_eps > 0:
        justified_pe = clip(8 + growth_score / 100 * 28 + quality_score / 100 * 14, 8, 45)
        fair_value = round(ttm_eps * justified_pe, 2)
        if latest_price:
            upside_pct = round((fair_value / latest_price - 1) * 100, 1)

    return {
        "insufficient_data": False,
        "revenue": revenue, "eps_ttm": round(ttm_eps, 3), "fcf": fcf,
        "fair_value": fair_value, "upside_pct": upside_pct,
        "revenue_growth_yoy": rev_growth, "eps_growth_yoy": eps_growth, "fcf_growth_yoy": fcf_growth,
        "gross_margin": gross_margin, "operating_margin": operating_margin,
        "roic": roic, "roe": roe, "debt": debt, "cash": cash, "leverage": leverage,
        "fcf_margin": fcf_margin, "market_cap": market_cap,
        "pe": pe, "forward_pe": forward_pe, "peg": peg, "ev_ebitda": ev_ebitda,
        "price_fcf": price_fcf, "fcf_yield": fcf_yield, "price_sales": price_sales,
        "quality_score": quality_score, "growth_score": growth_score,
        "value_score": value_score, "cash_flow_score": cash_flow_score,
        "analyst_revision": latest_estimate.get("revision_direction") if latest_estimate else None,
        "analyst_count": latest_estimate.get("analyst_count") if latest_estimate else None,
    }
