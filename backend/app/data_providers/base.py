"""
DataProvider interface.

Every engine in StockFind Pro (fundamental, technical, event, strategies,
backtester) talks to data exclusively through this interface — never to SQL
or a specific vendor SDK directly. That is what makes the "live market-data
integration" step in the architecture a matter of writing one new adapter
class, not touching the scoring logic at all.

The single most important contract here is `as_of`: every method accepts an
`as_of` date and must return only information that was *actually available*
on or before that date (using each record's `available_on` timestamp, not
its nominal period/report date). This is what lets the exact same code path
power both "scan the market right now" and "replay the market as it looked
on 2019-03-14" for backtesting — there is no separate backtest data path to
accidentally leak future information through.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional


class DataProvider(ABC):
    @abstractmethod
    def get_universe(self) -> list[dict]:
        """Return static company metadata for every ticker in the coverage universe."""

    @abstractmethod
    def get_company(self, ticker: str) -> Optional[dict]:
        ...

    @abstractmethod
    def get_prices(self, ticker: str, as_of: date, lookback_days: int = 400) -> list[dict]:
        """Daily OHLCV bars with date <= as_of, most recent `lookback_days` sessions,
        oldest first. Price data has no reporting lag (it's the market itself)."""

    @abstractmethod
    def get_benchmark_prices(self, symbol: str, as_of: date, lookback_days: int = 400) -> list[dict]:
        ...

    @abstractmethod
    def get_latest_fundamentals(self, ticker: str, as_of: date) -> Optional[dict]:
        """Most recent fundamentals_quarterly row with available_on <= as_of."""

    @abstractmethod
    def get_fundamentals_history(self, ticker: str, as_of: date, n_quarters: int = 12) -> list[dict]:
        """Up to n_quarters of fundamentals with available_on <= as_of, oldest first."""

    @abstractmethod
    def get_latest_estimate(self, ticker: str, as_of: date) -> Optional[dict]:
        ...

    @abstractmethod
    def get_recent_earnings(self, ticker: str, as_of: date, n: int = 4) -> list[dict]:
        """Most recent n earnings events with available_on <= as_of, newest first."""

    @abstractmethod
    def get_insider_transactions(self, ticker: str, as_of: date, lookback_days: int = 180) -> list[dict]:
        ...

    @abstractmethod
    def get_latest_institutional_ownership(self, ticker: str, as_of: date) -> list[dict]:
        """Returns the two most recent available snapshots (current + prior) so callers
        can compute a change; each snapshot itself carries change_pct too."""

    @abstractmethod
    def get_latest_short_interest(self, ticker: str, as_of: date) -> Optional[dict]:
        ...

    @abstractmethod
    def get_catalyst_events(self, ticker: str, as_of: date, lookback_days: int = 180) -> list[dict]:
        ...

    @abstractmethod
    def latest_available_date(self) -> date:
        """The most recent date this provider has price data for (i.e. 'today' for live use)."""
