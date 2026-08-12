"""
Stub adapters showing exactly where and how to wire in real live data,
per the source document's recommendation of a primary-source + market-data
architecture:

  - SEC EDGAR (Company Facts / XBRL "companyfacts" API) for US fundamentals
    straight from filings — https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
  - Finnhub for real-time quotes, financial statements, estimates, insider
    transactions, institutional ownership, and news/catalysts —
    https://finnhub.io/docs/api
  - Alpha Vantage for time series, fundamentals, and technical indicators —
    https://www.alphavantage.co/documentation/

None of these are called yet — StockFindPro currently runs entirely on
SimulatedProvider (see simulated.py) so the app works with zero API keys.
To go live:

  1. Implement the DataProvider interface (base.py) for each source, or build
     one BlendedLiveProvider that fans out to whichever source owns each field
     (e.g. EDGAR for fundamentals, Finnhub for quotes/insiders/estimates,
     Alpha Vantage for technicals) and normalizes results into the same
     dict shapes SimulatedProvider returns.
  2. CRITICAL: every live method must still stamp each fact with the date it
     actually became public (filing date, estimate revision date, 13F filing
     date, etc.) — not "today" — and filter out anything with
     available_on > as_of. That point-in-time discipline is what the whole
     backtesting engine (backtest/engine.py) depends on to stay bias-free.
     Finnhub and Alpha Vantage responses generally include the relevant
     report/filed date; EDGAR's companyfacts entries include `filed`.
  3. Cache aggressively (Finnhub/Alpha Vantage free tiers are rate-limited)
     — e.g. persist fetched data into the same SQLite tables SimulatedProvider
     reads, on a schedule, rather than calling the vendor API on every scan.
  4. Set FINNHUB_API_KEY / ALPHA_VANTAGE_API_KEY env vars and flip
     DATA_PROVIDER=live in app/config.py (see get_provider() below).

Below are unimplemented skeletons matching the method signatures so the next
engineer can fill them in without having to rediscover the interface.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

from .base import DataProvider

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"
SEC_EDGAR_BASE = "https://data.sec.gov/api/xbrl/companyfacts"


class LiveProvider(DataProvider):
    """Not implemented — see module docstring. Wire this up when API keys and
    a caching layer are available; every method below should ultimately read
    from a locally cached/normalized store (kept fresh by a scheduled job),
    not call vendor APIs synchronously on the request path."""

    def __init__(self):
        if not FINNHUB_API_KEY and not ALPHA_VANTAGE_API_KEY:
            raise RuntimeError(
                "LiveProvider requires FINNHUB_API_KEY and/or ALPHA_VANTAGE_API_KEY to be set. "
                "Falling back to SimulatedProvider is recommended until a caching layer exists."
            )

    def get_universe(self) -> list[dict]:
        raise NotImplementedError("Fetch symbol list via Finnhub /stock/symbol, cache to `companies` table")

    def get_company(self, ticker: str) -> Optional[dict]:
        raise NotImplementedError("Finnhub /stock/profile2")

    def get_prices(self, ticker: str, as_of: date, lookback_days: int = 400) -> list[dict]:
        raise NotImplementedError("Alpha Vantage TIME_SERIES_DAILY or Finnhub /stock/candle")

    def get_benchmark_prices(self, symbol: str, as_of: date, lookback_days: int = 400) -> list[dict]:
        raise NotImplementedError("Same as get_prices for SPY/QQQ as index proxies")

    def get_latest_fundamentals(self, ticker: str, as_of: date) -> Optional[dict]:
        raise NotImplementedError("SEC EDGAR companyfacts XBRL concepts, stamped with `filed` date")

    def get_fundamentals_history(self, ticker: str, as_of: date, n_quarters: int = 12) -> list[dict]:
        raise NotImplementedError("SEC EDGAR companyfacts, filtered to filed <= as_of")

    def get_latest_estimate(self, ticker: str, as_of: date) -> Optional[dict]:
        raise NotImplementedError("Finnhub /stock/eps-estimate and /stock/revenue-estimate")

    def get_recent_earnings(self, ticker: str, as_of: date, n: int = 4) -> list[dict]:
        raise NotImplementedError("Finnhub /stock/earnings")

    def get_insider_transactions(self, ticker: str, as_of: date, lookback_days: int = 180) -> list[dict]:
        raise NotImplementedError("Finnhub /stock/insider-transactions")

    def get_latest_institutional_ownership(self, ticker: str, as_of: date) -> list[dict]:
        raise NotImplementedError(
            "Finnhub /institutional/ownership or 13F aggregation — remember this is inherently "
            "reported with a 30-45 day lag; keep the UI distinguishing reported vs inferred data"
        )

    def get_latest_short_interest(self, ticker: str, as_of: date) -> Optional[dict]:
        raise NotImplementedError("FINRA/exchange short interest files (bi-monthly, also lagged)")

    def get_catalyst_events(self, ticker: str, as_of: date, lookback_days: int = 180) -> list[dict]:
        raise NotImplementedError("Finnhub /company-news + /press-releases, classified by an NLP tagger")

    def latest_available_date(self) -> date:
        raise NotImplementedError


def get_provider() -> DataProvider:
    """Provider factory — the one place the rest of the app decides which
    backend to use. Swap DATA_PROVIDER=live (with API keys set) once
    LiveProvider is implemented; everything else in the app is unaffected."""
    from .simulated import SimulatedProvider

    mode = os.environ.get("DATA_PROVIDER", "simulated")
    if mode == "live":
        return LiveProvider()
    return SimulatedProvider.instance()
