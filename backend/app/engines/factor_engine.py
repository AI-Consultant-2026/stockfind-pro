"""
Factor engine — the orchestration layer that pulls point-in-time data for one
ticker as of one date from a DataProvider and produces the full ScoreBundle:
Quality, Growth, Momentum, Value, Cash Flow, Catalyst and Risk sub-scores,
plus every raw metric needed downstream by strategies, the Why/Why-Not
generator, and the dashboard. This is the single function both the live
scanner and the backtester call — see architecture note in data_providers/base.py.
"""
from __future__ import annotations

from datetime import date

from ..data_providers.base import DataProvider
from .technical import compute_technicals
from .fundamental import compute_fundamental_metrics
from .event import compute_event_signals
from .momentum import compute_momentum_score
from .risk import compute_risk_score


def score_stock(ticker: str, as_of: date, provider: DataProvider, lookback_days: int = 300) -> dict | None:
    company = provider.get_company(ticker)
    if not company:
        return None

    price_rows = provider.get_prices(ticker, as_of, lookback_days=max(lookback_days, 260))
    if len(price_rows) < 30:
        return None
    benchmark_rows = provider.get_benchmark_prices("SPX", as_of, lookback_days=max(lookback_days, 260))

    tech = compute_technicals(price_rows, benchmark_rows)

    fund_history = provider.get_fundamentals_history(ticker, as_of, n_quarters=8)
    latest_estimate = provider.get_latest_estimate(ticker, as_of)
    fund = compute_fundamental_metrics(fund_history, tech.get("close"), latest_estimate)

    earnings = provider.get_recent_earnings(ticker, as_of, n=4)
    insiders = provider.get_insider_transactions(ticker, as_of, lookback_days=180)
    inst_ownership = provider.get_latest_institutional_ownership(ticker, as_of)
    short_interest = provider.get_latest_short_interest(ticker, as_of)
    if short_interest:
        short_interest = dict(short_interest)
        short_interest["_float_shares"] = company.get("float_shares")
    catalysts = provider.get_catalyst_events(ticker, as_of, lookback_days=180)
    event = compute_event_signals(earnings, insiders, inst_ownership, short_interest, catalysts)

    momentum_score = compute_momentum_score(tech)
    risk_score = compute_risk_score(tech, fund, event, company.get("beta", 1.0))

    quality = fund.get("quality_score", 50.0)
    growth = fund.get("growth_score", 50.0)
    value = fund.get("value_score", 50.0)
    cash_flow = fund.get("cash_flow_score", 50.0)
    catalyst = event.get("catalyst_score", 50.0)

    return {
        "ticker": ticker,
        "name": company["name"],
        "sector": company["sector"],
        "industry": company["industry"],
        "as_of": as_of.isoformat(),
        "price": tech.get("close"),
        "market_cap": fund.get("market_cap"),
        "scores": {
            "quality": round(quality, 1),
            "growth": round(growth, 1),
            "momentum": round(momentum_score, 1),
            "value": round(value, 1),
            "cash_flow": round(cash_flow, 1),
            "catalyst": round(catalyst, 1),
            "risk": round(risk_score, 1),
        },
        "technical": tech,
        "fundamental": fund,
        "event": event,
        "company": company,
    }
