"""
Strategy 10 — Sector Rotation. Not a per-stock strategy like the other nine;
this continuously ranks sectors by relative strength so the scanner can
express the doc's hierarchy: Market → Sector → Industry → Stock, and drill
into the strongest sectors rather than searching stocks randomly.
"""
from __future__ import annotations

from datetime import date

from .scoring_utils import band, clip
from .technical import compute_technicals
from ..data_providers.base import DataProvider
from ..seed_universe import SECTORS


def compute_sector_rotation(provider: DataProvider, as_of: date) -> list[dict]:
    benchmark_rows = provider.get_benchmark_prices("SPX", as_of, lookback_days=300)
    companies = provider.get_universe()
    by_sector: dict[str, list[str]] = {sec: [] for sec in SECTORS}
    for c in companies:
        by_sector.setdefault(c["sector"], []).append(c["ticker"])

    results = []
    for sector, tickers in by_sector.items():
        rel_strengths, mom63s = [], []
        for ticker in tickers:
            rows = provider.get_prices(ticker, as_of, lookback_days=300)
            if len(rows) < 65:
                continue
            tech = compute_technicals(rows, benchmark_rows)
            if tech.get("insufficient_data"):
                continue
            if tech.get("rel_strength_63d") is not None:
                rel_strengths.append(tech["rel_strength_63d"])
            if tech.get("mom_63d") is not None:
                mom63s.append(tech["mom_63d"])
        if not rel_strengths:
            continue
        avg_rel = sum(rel_strengths) / len(rel_strengths)
        avg_mom = sum(mom63s) / len(mom63s) if mom63s else 0.0
        momentum_score = band(avg_rel, -12, 12)
        results.append({
            "sector": sector,
            "momentum_score": round(momentum_score, 1),
            "avg_relative_strength_63d": round(avg_rel, 2),
            "avg_return_63d": round(avg_mom, 2),
            "stock_count": len(rel_strengths),
        })

    results.sort(key=lambda r: r["momentum_score"], reverse=True)
    return results


def sector_momentum_lookup(provider: DataProvider, as_of: date) -> dict[str, float]:
    return {r["sector"]: r["momentum_score"] for r in compute_sector_rotation(provider, as_of)}
