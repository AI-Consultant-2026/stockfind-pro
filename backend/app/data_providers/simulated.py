"""
SimulatedProvider — reads the local SQLite database produced by app.seed.

Everything is loaded into memory once (the whole universe is ~175k price rows
and a few thousand fundamentals/events rows — a few tens of MB), then served
from plain Python/pandas structures. This matters because the backtesting
engine calls these methods once per ticker per rebalance date across a
multi-year simulation, and repeated SQLite round-trips would make that slow.
"""
from __future__ import annotations

import bisect
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from .base import DataProvider
from ..db.database import get_connection


def _d(s: str) -> date:
    return date.fromisoformat(s)


class SimulatedProvider(DataProvider):
    _instance: "SimulatedProvider | None" = None

    def __init__(self):
        conn = get_connection()
        self.companies = {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM companies")}

        self.prices: dict[str, pd.DataFrame] = {}
        for ticker in self.companies:
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume FROM prices WHERE ticker=? ORDER BY date",
                conn, params=(ticker,),
            )
            df["date"] = df["date"]  # keep as ISO string; comparisons are lexicographic-safe
            self.prices[ticker] = df

        self.benchmarks: dict[str, pd.DataFrame] = {}
        for sym in ("SPX", "NDX"):
            self.benchmarks[sym] = pd.read_sql_query(
                "SELECT date, close FROM benchmark_prices WHERE symbol=? ORDER BY date", conn, params=(sym,)
            )

        self.fundamentals: dict[str, list[dict]] = {}
        for ticker in self.companies:
            rows = conn.execute(
                "SELECT * FROM fundamentals_quarterly WHERE ticker=? ORDER BY available_on", (ticker,)
            ).fetchall()
            self.fundamentals[ticker] = [dict(r) for r in rows]

        self.estimates: dict[str, list[dict]] = {}
        for ticker in self.companies:
            rows = conn.execute(
                "SELECT * FROM estimates WHERE ticker=? ORDER BY available_on", (ticker,)
            ).fetchall()
            self.estimates[ticker] = [dict(r) for r in rows]

        self.earnings: dict[str, list[dict]] = {}
        for ticker in self.companies:
            rows = conn.execute(
                "SELECT * FROM earnings_events WHERE ticker=? ORDER BY available_on", (ticker,)
            ).fetchall()
            self.earnings[ticker] = [dict(r) for r in rows]

        self.insiders: dict[str, list[dict]] = {}
        for ticker in self.companies:
            rows = conn.execute(
                "SELECT * FROM insider_transactions WHERE ticker=? ORDER BY available_on", (ticker,)
            ).fetchall()
            self.insiders[ticker] = [dict(r) for r in rows]

        self.inst_ownership: dict[str, list[dict]] = {}
        for ticker in self.companies:
            rows = conn.execute(
                "SELECT * FROM institutional_ownership WHERE ticker=? ORDER BY available_on", (ticker,)
            ).fetchall()
            self.inst_ownership[ticker] = [dict(r) for r in rows]

        self.short_interest: dict[str, list[dict]] = {}
        for ticker in self.companies:
            rows = conn.execute(
                "SELECT * FROM short_interest WHERE ticker=? ORDER BY available_on", (ticker,)
            ).fetchall()
            self.short_interest[ticker] = [dict(r) for r in rows]

        self.catalysts: dict[str, list[dict]] = {}
        for ticker in self.companies:
            rows = conn.execute(
                "SELECT * FROM catalyst_events WHERE ticker=? ORDER BY available_on", (ticker,)
            ).fetchall()
            self.catalysts[ticker] = [dict(r) for r in rows]

        self._max_date = max(df["date"].iloc[-1] for df in self.prices.values() if len(df))
        conn.close()

    @classmethod
    def instance(cls) -> "SimulatedProvider":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _filter_available(rows: list[dict], as_of: date) -> list[dict]:
        cutoff = as_of.isoformat()
        return [r for r in rows if r["available_on"] <= cutoff]

    # -- interface -----------------------------------------------------------
    def get_universe(self) -> list[dict]:
        return list(self.companies.values())

    def get_company(self, ticker: str) -> Optional[dict]:
        return self.companies.get(ticker)

    def get_prices(self, ticker: str, as_of: date, lookback_days: int = 400) -> list[dict]:
        df = self.prices.get(ticker)
        if df is None or df.empty:
            return []
        cutoff = as_of.isoformat()
        idx = bisect.bisect_right(df["date"].values, cutoff)
        sub = df.iloc[max(0, idx - lookback_days):idx]
        return sub.to_dict("records")

    def get_benchmark_prices(self, symbol: str, as_of: date, lookback_days: int = 400) -> list[dict]:
        df = self.benchmarks.get(symbol)
        if df is None or df.empty:
            return []
        cutoff = as_of.isoformat()
        idx = bisect.bisect_right(df["date"].values, cutoff)
        sub = df.iloc[max(0, idx - lookback_days):idx]
        return sub.to_dict("records")

    def get_latest_fundamentals(self, ticker: str, as_of: date) -> Optional[dict]:
        rows = self._filter_available(self.fundamentals.get(ticker, []), as_of)
        return rows[-1] if rows else None

    def get_fundamentals_history(self, ticker: str, as_of: date, n_quarters: int = 12) -> list[dict]:
        rows = self._filter_available(self.fundamentals.get(ticker, []), as_of)
        return rows[-n_quarters:]

    def get_latest_estimate(self, ticker: str, as_of: date) -> Optional[dict]:
        rows = self._filter_available(self.estimates.get(ticker, []), as_of)
        return rows[-1] if rows else None

    def get_recent_earnings(self, ticker: str, as_of: date, n: int = 4) -> list[dict]:
        rows = self._filter_available(self.earnings.get(ticker, []), as_of)
        return list(reversed(rows[-n:]))

    def get_insider_transactions(self, ticker: str, as_of: date, lookback_days: int = 180) -> list[dict]:
        rows = self._filter_available(self.insiders.get(ticker, []), as_of)
        floor = (as_of - timedelta(days=lookback_days)).isoformat()
        return [r for r in rows if r["transaction_date"] >= floor]

    def get_latest_institutional_ownership(self, ticker: str, as_of: date) -> list[dict]:
        rows = self._filter_available(self.inst_ownership.get(ticker, []), as_of)
        return rows[-2:]

    def get_latest_short_interest(self, ticker: str, as_of: date) -> Optional[dict]:
        rows = self._filter_available(self.short_interest.get(ticker, []), as_of)
        return rows[-1] if rows else None

    def get_catalyst_events(self, ticker: str, as_of: date, lookback_days: int = 180) -> list[dict]:
        rows = self._filter_available(self.catalysts.get(ticker, []), as_of)
        floor = (as_of - timedelta(days=lookback_days)).isoformat()
        return [r for r in rows if r["event_date"] >= floor]

    def latest_available_date(self) -> date:
        return _d(self._max_date)
