"""
Scan service — computes (and memoizes) the full-universe opportunity scan for
a given as_of date. All API routes read from here rather than recomputing
per-request, so switching strategy/mode/sector filters on the dashboard is
instant even though the underlying scoring is a real quant computation.
"""
from __future__ import annotations

from datetime import date

from ..data_providers.live_stubs import get_provider
from ..engines.factor_engine import score_stock
from ..engines.ranking import build_opportunity
from ..engines.sector_rotation import compute_sector_rotation

_scan_cache: dict[str, list[dict]] = {}
_sector_cache: dict[str, list[dict]] = {}

provider = get_provider()


def get_sector_rotation(as_of: date) -> list[dict]:
    key = as_of.isoformat()
    if key not in _sector_cache:
        _sector_cache[key] = compute_sector_rotation(provider, as_of)
    return _sector_cache[key]


def get_full_scan(as_of: date) -> list[dict]:
    key = as_of.isoformat()
    if key in _scan_cache:
        return _scan_cache[key]

    sector_rows = get_sector_rotation(as_of)
    sector_momentum = {r["sector"]: r["momentum_score"] for r in sector_rows}

    results = []
    for company in provider.get_universe():
        bundle = score_stock(company["ticker"], as_of, provider)
        if not bundle:
            continue
        opp = build_opportunity(bundle, sector_momentum.get(company["sector"]))
        results.append(opp)

    results.sort(key=lambda r: r["display_score"], reverse=True)
    _scan_cache[key] = results
    return results


def get_stock_detail(ticker: str, as_of: date) -> dict | None:
    bundle = score_stock(ticker, as_of, provider)
    if not bundle:
        return None
    sector_rows = get_sector_rotation(as_of)
    sector_momentum = {r["sector"]: r["momentum_score"] for r in sector_rows}
    opp = build_opportunity(bundle, sector_momentum.get(bundle["sector"]))
    # The detail view (unlike the list scan) also needs the raw metric
    # breakdown for its "key metrics" table — attach it here rather than in
    # every scan result, which stays lighter for the list/radar views.
    opp["technical"] = bundle["technical"]
    opp["fundamental"] = bundle["fundamental"]
    opp["event"] = bundle["event"]
    opp["company"] = bundle["company"]
    return opp


def default_as_of() -> date:
    return provider.latest_available_date()


def clear_cache():
    _scan_cache.clear()
    _sector_cache.clear()
