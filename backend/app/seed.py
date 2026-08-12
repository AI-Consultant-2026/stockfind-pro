"""
Orchestrates generation of the full simulated dataset and loads it into SQLite.
Run with: python -m app.seed
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

from .db.database import init_db, session
from .seed_universe import UNIVERSE
from . import data_gen as G


def run(reset: bool = True):
    t0 = time.time()
    print(f"Initializing DB (reset={reset})...")
    init_db(reset=reset)

    days = G.trading_days(G.START_DATE, G.END_DATE)
    print(f"Trading days: {len(days)} ({days[0].date()} -> {days[-1].date()})")

    master_rng = np.random.default_rng(G.RNG_SEED)
    regime_df = G.build_regime_series(days)
    sector_tilts = G.build_sector_tilts(days, master_rng)

    spx = G.gen_benchmark(days, regime_df, np.random.default_rng(G.RNG_SEED + 1), "SPX", tech_tilt=0.0)
    ndx = G.gen_benchmark(days, regime_df, np.random.default_rng(G.RNG_SEED + 2), "NDX", tech_tilt=0.35)

    with session() as conn:
        conn.executemany(
            "INSERT INTO benchmark_prices (symbol, date, close) VALUES (?, ?, ?)",
            spx[["symbol", "date", "close"]].itertuples(index=False, name=None),
        )
        conn.executemany(
            "INSERT INTO benchmark_prices (symbol, date, close) VALUES (?, ?, ?)",
            ndx[["symbol", "date", "close"]].itertuples(index=False, name=None),
        )
        print("Benchmarks loaded.")

        for n, (ticker, name, sector, industry, archetype) in enumerate(UNIVERSE):
            rng = np.random.default_rng(G.RNG_SEED + 1000 + n)
            beta = float(np.clip(rng.normal(1.05 if sector == "Technology" else 0.9, 0.25), 0.4, 2.2))

            prices_df = G.gen_prices_for_ticker(ticker, sector, archetype, days, regime_df, sector_tilts[sector], rng)
            shares_out_m = float(rng.uniform(80, 900))
            float_pct = float(rng.uniform(0.6, 0.97))
            float_shares_m = shares_out_m * float_pct

            conn.execute(
                "INSERT INTO companies (ticker, name, sector, industry, exchange, ipo_date, shares_outstanding, float_shares, beta) "
                "VALUES (?, ?, ?, ?, 'NASDAQ', ?, ?, ?, ?)",
                (ticker, name, sector, industry, G.START_DATE.isoformat(),
                 shares_out_m * 1_000_000, float_shares_m * 1_000_000, round(beta, 2)),
            )

            conn.executemany(
                "INSERT INTO prices (ticker, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                prices_df[["ticker", "date", "open", "high", "low", "close", "volume"]].itertuples(index=False, name=None),
            )

            last_price = float(prices_df.iloc[-1]["close"])
            first_price = float(prices_df.iloc[0]["close"])
            fundamentals = G.gen_fundamentals(ticker, archetype, rng, first_price)
            conn.executemany(
                "INSERT INTO fundamentals_quarterly (ticker, fiscal_period, period_end, available_on, revenue, eps, fcf, "
                "gross_margin, operating_margin, roic, roe, debt, cash, shares_outstanding) "
                "VALUES (:ticker, :fiscal_period, :period_end, :available_on, :revenue, :eps, :fcf, "
                ":gross_margin, :operating_margin, :roic, :roe, :debt, :cash, :shares_outstanding)",
                fundamentals,
            )

            estimates, earnings = G.gen_estimates_and_earnings(ticker, archetype, fundamentals, prices_df, rng)
            conn.executemany(
                "INSERT INTO estimates (ticker, as_of_date, available_on, eps_estimate, revenue_estimate, analyst_count, revision_direction) "
                "VALUES (:ticker, :as_of_date, :available_on, :eps_estimate, :revenue_estimate, :analyst_count, :revision_direction)",
                estimates,
            )
            conn.executemany(
                "INSERT INTO earnings_events (ticker, report_date, available_on, eps_actual, eps_estimate, revenue_actual, "
                "revenue_estimate, guidance_change, price_reaction_pct) "
                "VALUES (:ticker, :report_date, :available_on, :eps_actual, :eps_estimate, :revenue_actual, "
                ":revenue_estimate, :guidance_change, :price_reaction_pct)",
                earnings,
            )

            insiders = G.gen_insider_transactions(ticker, archetype, days, rng, last_price)
            if insiders:
                conn.executemany(
                    "INSERT INTO insider_transactions (ticker, transaction_date, available_on, insider_name, insider_role, "
                    "transaction_type, shares, price, value) VALUES (:ticker, :transaction_date, :available_on, :insider_name, "
                    ":insider_role, :transaction_type, :shares, :price, :value)",
                    insiders,
                )

            inst = G.gen_institutional_ownership(ticker, archetype, rng)
            conn.executemany(
                "INSERT INTO institutional_ownership (ticker, period_end, available_on, pct_ownership, change_pct) "
                "VALUES (:ticker, :period_end, :available_on, :pct_ownership, :change_pct)",
                inst,
            )

            shorts = G.gen_short_interest(ticker, archetype, days, rng, float_shares_m * 1_000_000)
            conn.executemany(
                "INSERT INTO short_interest (ticker, settlement_date, available_on, short_shares, days_to_cover) "
                "VALUES (:ticker, :settlement_date, :available_on, :short_shares, :days_to_cover)",
                shorts,
            )

            catalysts = G.gen_catalyst_events(ticker, archetype, days, rng)
            if catalysts:
                conn.executemany(
                    "INSERT INTO catalyst_events (ticker, event_date, available_on, event_type, description, sentiment) "
                    "VALUES (:ticker, :event_date, :available_on, :event_type, :description, :sentiment)",
                    catalysts,
                )

            print(f"  [{n+1}/{len(UNIVERSE)}] {ticker:6s} {archetype:28s} seeded ({len(prices_df)} bars, "
                  f"{len(fundamentals)} quarters)")

    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    run(reset="--no-reset" not in sys.argv)
