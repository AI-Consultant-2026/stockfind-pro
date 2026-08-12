"""
Simulated market data generator for StockFind Pro.

This produces a fully self-consistent, point-in-time-correct synthetic dataset:
daily OHLCV, quarterly fundamentals, analyst estimates, insider transactions,
institutional ownership, short interest, earnings events and catalyst events,
for the fictional universe in seed_universe.py, over START_DATE..END_DATE.

It is deliberately built with a realistic market-regime backbone (2018 selloff,
2020 COVID crash + recovery, 2022 bear market, otherwise a ~9-11%/yr uptrend)
so that momentum/mean-reversion signals and the backtesting engine behave the
way they would against real market history, and every ticker is assigned an
"archetype" (see seed_universe.py) that shapes its return path and fundamentals
so each opportunity strategy has genuine examples to find.

Nothing here is a claim about any real company — tickers and names are fictional.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .seed_universe import UNIVERSE, SECTORS

START_DATE = date(2016, 1, 1)
END_DATE = date(2026, 8, 11)

RNG_SEED = 20260811


def trading_days(start: date, end: date) -> pd.DatetimeIndex:
    return pd.bdate_range(start, end)


# ---------------------------------------------------------------------------
# Market regime: annualized drift & vol multiplier by date, shared by everyone.
# ---------------------------------------------------------------------------
REGIME_WINDOWS = [
    # (start, end, annualized_drift, vol_multiplier)
    (date(2016, 1, 1), date(2018, 9, 30), 0.11, 1.0),
    (date(2018, 10, 1), date(2018, 12, 24), -0.45, 1.8),   # Q4 2018 selloff
    (date(2018, 12, 25), date(2020, 2, 18), 0.17, 0.9),
    (date(2020, 2, 19), date(2020, 3, 23), -2.10, 3.2),    # COVID crash
    (date(2020, 3, 24), date(2020, 8, 31), 0.85, 2.0),     # sharp recovery
    (date(2020, 9, 1), date(2021, 12, 31), 0.18, 1.0),
    (date(2022, 1, 1), date(2022, 10, 12), -0.38, 1.6),    # 2022 bear market
    (date(2022, 10, 13), date(2024, 12, 31), 0.15, 1.0),
    (date(2025, 1, 1), date(2026, 8, 11), 0.10, 1.05),
]


def regime_for(d: date) -> tuple[float, float]:
    for start, end, drift, vol in REGIME_WINDOWS:
        if start <= d <= end:
            return drift, vol
    return 0.10, 1.0


def build_regime_series(days: pd.DatetimeIndex) -> pd.DataFrame:
    drifts, vols = [], []
    for ts in days:
        drift, vol = regime_for(ts.date())
        drifts.append(drift / 252.0)
        vols.append(vol)
    return pd.DataFrame({"date": days, "daily_drift": drifts, "vol_mult": vols})


# ---------------------------------------------------------------------------
# Sector strength: a slowly-varying random walk per sector in [-1, 1] used to
# tilt each sector's stocks up or down relative to the broad market, which is
# what the Sector Rotation strategy reads (via realized relative strength).
# ---------------------------------------------------------------------------
def build_sector_tilts(days: pd.DatetimeIndex, rng: np.random.Generator) -> dict[str, pd.Series]:
    """Mean-reverting (OU-process) sector strength in roughly [-1, 1], with a
    ~150-trading-day half-life — long enough to produce genuine multi-quarter
    sector leadership/rotation, but bounded so it can't drift to an extreme
    and stay there for the full simulation (which would silently compound
    into unrealistic decade-long price multiples for an entire sector)."""
    from scipy.signal import lfilter
    tilts = {}
    k = 0.0046  # ~150-session half-life
    for sector in SECTORS:
        steps = rng.normal(0, 0.055, size=len(days))
        walk = lfilter([1.0], [1.0, -(1 - k)], steps)
        tilts[sector] = pd.Series(np.tanh(walk), index=days)
    return tilts


ARCHETYPE_PARAMS = {
    # base_alpha: extra annualized drift on top of regime+sector
    # vol: annualized idiosyncratic volatility
    "compounder":                dict(base_alpha=0.045, vol=0.24),
    "momentum_breakout":         dict(base_alpha=0.025, vol=0.34),
    "earnings_momentum":         dict(base_alpha=0.035, vol=0.30),
    "fallen_angel_good":         dict(base_alpha=-0.010, vol=0.36),
    "fallen_angel_bad":          dict(base_alpha=-0.070, vol=0.40),
    "undervalued_quality":       dict(base_alpha=0.030, vol=0.22),
    "institutional_accumulation":dict(base_alpha=0.040, vol=0.24),
    "insider_accumulation":      dict(base_alpha=0.020, vol=0.28),
    "short_squeeze":             dict(base_alpha=0.010, vol=0.55),
    "mean_reversion_healthy":    dict(base_alpha=0.025, vol=0.32),
    "mean_reversion_unhealthy":  dict(base_alpha=-0.045, vol=0.38),
    "deteriorating":             dict(base_alpha=-0.090, vol=0.30),
    "generic_neutral":           dict(base_alpha=0.015, vol=0.26),
}


def archetype_event_overlay(archetype: str, days: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """Return an array of extra log-return bumps on top of the base random walk,
    used to sculpt the *recent* window (last ~9 months) into a shape the relevant
    strategy will actually detect — e.g. a real consolidation-then-breakout for
    momentum_breakout, a real sharp recent drawdown for fallen_angel/mean_reversion.
    Recent = last 190 trading days, so "as of today" scans find live setups.
    """
    n = len(days)
    overlay = np.zeros(n)
    recent_start = max(0, n - 190)

    if archetype == "momentum_breakout":
        # flat consolidation then a strong breakout in the final ~25 sessions
        overlay[recent_start:n - 25] = -0.0003
        overlay[n - 25:] = 0.014
    elif archetype == "earnings_momentum":
        # a couple of positive earnings jumps in the last two quarters
        for offset in (40, 110):
            idx = n - offset
            if 0 <= idx < n:
                overlay[idx:idx + 3] += 0.045
        overlay[n - 60:] += 0.0015
    elif archetype in ("fallen_angel_good", "fallen_angel_bad"):
        # a sharp decline roughly 4-9 months ago, since flattening/basing
        overlay[n - 160:n - 60] = -0.006
        overlay[n - 60:] = 0.0005 if archetype == "fallen_angel_good" else -0.0015
    elif archetype == "institutional_accumulation":
        overlay[recent_start:] = 0.0012
    elif archetype == "insider_accumulation":
        overlay[n - 45:] = 0.0009
    elif archetype == "short_squeeze":
        overlay[n - 15:] = 0.02
        overlay[n - 90:n - 15] = 0.001
    elif archetype in ("mean_reversion_healthy", "mean_reversion_unhealthy"):
        overlay[n - 20:] = -0.011
    elif archetype == "deteriorating":
        overlay[recent_start:] = -0.0018

    return overlay


def gen_prices_for_ticker(ticker: str, sector: str, archetype: str, days: pd.DatetimeIndex,
                           regime_df: pd.DataFrame, sector_tilt: pd.Series,
                           rng: np.random.Generator) -> pd.DataFrame:
    n = len(days)
    params = ARCHETYPE_PARAMS[archetype]
    daily_alpha = params["base_alpha"] / 252.0
    daily_vol = params["vol"] / math.sqrt(252.0)

    base_drift = regime_df["daily_drift"].values
    vol_mult = regime_df["vol_mult"].values
    sector_component = (sector_tilt.values * 0.15) / 252.0

    # Smooth long-term trend: regime + sector + archetype alpha, no idiosyncratic
    # noise. This is what compounds over the full 10+ year horizon.
    trend_log_returns = base_drift + sector_component + daily_alpha
    trend_log_returns[0] = 0.0
    trend_log_price = np.cumsum(trend_log_returns)

    # Idiosyncratic deviation from trend follows a mean-reverting (OU) process
    # rather than a pure random walk, so cumulative variance stays bounded
    # over a decade of daily noise instead of compounding into absurd prices
    # (a well-known artifact of naive GBM over long horizons). Archetype
    # "overlay" events (breakouts, earnings jumps, drawdowns) ride on top of
    # this deviation, so recent setups are still fully visible in the last
    # ~6-9 months even though older noise has reverted.
    overlay = archetype_event_overlay(archetype, days, rng)
    noise = rng.normal(0, 1, size=n) * daily_vol * vol_mult
    k = 0.006  # reversion speed (~115-session half-life)
    from scipy.signal import lfilter
    deviation = lfilter([1.0], [1.0, -(1 - k)], noise + overlay)

    start_price = rng.uniform(10, 140)
    prices = start_price * np.exp(trend_log_price + deviation)

    # build OHLC around the close-to-close path with plausible intraday range
    closes = prices
    opens = np.empty(n)
    opens[0] = start_price
    opens[1:] = closes[:-1] * (1 + rng.normal(0, 0.002, size=n - 1))
    intraday_range = np.abs(rng.normal(0, 1, size=n)) * daily_vol * closes * 0.6 + closes * 0.0025
    highs = np.maximum(opens, closes) + intraday_range * rng.uniform(0.2, 0.6, size=n)
    lows = np.minimum(opens, closes) - intraday_range * rng.uniform(0.2, 0.6, size=n)
    lows = np.clip(lows, 0.5, None)

    base_volume = rng.uniform(400_000, 6_000_000)
    vol_noise = np.abs(rng.normal(1, 0.35, size=n))
    ret_shock = np.abs(np.diff(np.concatenate([[0], np.log(closes)]))) * 18
    volumes = base_volume * vol_noise * (1 + ret_shock)
    # extra volume during breakout/squeeze/earnings windows
    if archetype == "momentum_breakout":
        volumes[n - 25:] *= 2.3
    elif archetype == "short_squeeze":
        volumes[n - 15:] *= 4.0
    elif archetype == "earnings_momentum":
        for offset in (40, 110):
            idx = n - offset
            if 0 <= idx < n:
                volumes[idx:idx + 3] *= 3.5

    return pd.DataFrame({
        "ticker": ticker,
        "date": [d.date().isoformat() for d in days],
        "open": opens.round(2),
        "high": highs.round(2),
        "low": lows.round(2),
        "close": closes.round(2),
        "volume": volumes.round(0),
    })


def gen_benchmark(days: pd.DatetimeIndex, regime_df: pd.DataFrame, rng: np.random.Generator,
                   symbol: str, tech_tilt: float = 0.0) -> pd.DataFrame:
    """Same trend + bounded-deviation construction as individual stocks (see
    gen_prices_for_ticker) so a single random draw can't make an index quietly
    underperform its intended long-run drift over a 10+ year simulation —
    the trend component is deterministic given the regime schedule, only the
    bounded noise around it is random."""
    from scipy.signal import lfilter
    n = len(days)
    daily_vol = (0.16 if symbol == "SPX" else 0.20) / math.sqrt(252.0)

    trend_log_returns = regime_df["daily_drift"].values * (1 + tech_tilt)
    trend_log_returns = trend_log_returns.copy()
    trend_log_returns[0] = 0.0
    trend_log_price = np.cumsum(trend_log_returns)

    noise = rng.normal(0, 1, size=n) * daily_vol * regime_df["vol_mult"].values
    deviation = lfilter([1.0], [1.0, -(1 - 0.006)], noise)

    start = 2000.0 if symbol == "SPX" else 5000.0
    closes = start * np.exp(trend_log_price + deviation)
    return pd.DataFrame({"symbol": symbol, "date": [d.date().isoformat() for d in days], "close": closes.round(2)})


# ---------------------------------------------------------------------------
# Fundamentals, estimates, ownership, short interest, earnings & catalysts
# ---------------------------------------------------------------------------
FUND_ARCHETYPE = {
    # rev_g/eps_g/fcf_g are calibrated to roughly track each archetype's total
    # expected price CAGR (see ARCHETYPE_PARAMS base_alpha + market regime,
    # ~11-13%/yr blended) so trailing valuation multiples stay in a realistic
    # band over a full decade-long simulation instead of drifting to extremes
    # (a P/E that silently compresses toward zero or explodes over 10 years
    # because EPS and price were compounding at very different rates).
    "compounder":                 dict(rev_g=0.13, eps_g=0.16, fcf_g=0.15, gm=0.55, om=0.24, roic=0.19, roe=0.21, debt_trend=-0.01, cash_trend=0.06),
    "momentum_breakout":          dict(rev_g=0.09, eps_g=0.11, fcf_g=0.10, gm=0.42, om=0.15, roic=0.12, roe=0.14, debt_trend=0.01, cash_trend=0.03),
    "earnings_momentum":          dict(rev_g=0.12, eps_g=0.18, fcf_g=0.14, gm=0.48, om=0.19, roic=0.16, roe=0.18, debt_trend=-0.01, cash_trend=0.05),
    "fallen_angel_good":          dict(rev_g=0.08, eps_g=0.10, fcf_g=0.11, gm=0.45, om=0.17, roic=0.14, roe=0.15, debt_trend=0.00, cash_trend=0.04),
    "fallen_angel_bad":           dict(rev_g=-0.04, eps_g=-0.10, fcf_g=-0.08, gm=0.30, om=0.05, roic=0.03, roe=0.02, debt_trend=0.05, cash_trend=-0.06),
    "undervalued_quality":        dict(rev_g=0.08, eps_g=0.10, fcf_g=0.10, gm=0.50, om=0.22, roic=0.18, roe=0.19, debt_trend=-0.01, cash_trend=0.05),
    "institutional_accumulation": dict(rev_g=0.09, eps_g=0.12, fcf_g=0.11, gm=0.46, om=0.18, roic=0.15, roe=0.16, debt_trend=-0.01, cash_trend=0.04),
    "insider_accumulation":       dict(rev_g=0.07, eps_g=0.09, fcf_g=0.08, gm=0.40, om=0.14, roic=0.11, roe=0.12, debt_trend=0.00, cash_trend=0.02),
    "short_squeeze":              dict(rev_g=0.06, eps_g=0.02, fcf_g=-0.02, gm=0.32, om=0.04, roic=0.02, roe=0.01, debt_trend=0.03, cash_trend=-0.02),
    "mean_reversion_healthy":     dict(rev_g=0.08, eps_g=0.09, fcf_g=0.09, gm=0.44, om=0.16, roic=0.13, roe=0.14, debt_trend=-0.01, cash_trend=0.03),
    "mean_reversion_unhealthy":   dict(rev_g=-0.02, eps_g=-0.03, fcf_g=-0.04, gm=0.33, om=0.07, roic=0.05, roe=0.04, debt_trend=0.03, cash_trend=-0.03),
    "deteriorating":              dict(rev_g=-0.06, eps_g=-0.12, fcf_g=-0.11, gm=0.28, om=0.02, roic=0.01, roe=-0.02, debt_trend=0.06, cash_trend=-0.07),
    "generic_neutral":            dict(rev_g=0.07, eps_g=0.08, fcf_g=0.07, gm=0.38, om=0.12, roic=0.10, roe=0.11, debt_trend=0.00, cash_trend=0.01),
}


def quarter_ends(start: date, end: date):
    qs = []
    y, m = start.year, ((start.month - 1) // 3) * 3 + 3
    d = date(y, m, 1)
    while d <= end:
        next_month = d.month + 3
        y2, m2 = (d.year + 1, next_month - 12) if next_month > 12 else (d.year, next_month)
        last_day = date(y2, m2, 1) - timedelta(days=1)
        if last_day <= end:
            qs.append(last_day)
        d = date(y2, m2, 1)
    return qs


def gen_fundamentals(ticker: str, archetype: str, rng: np.random.Generator, start_price: float):
    """`start_price` must be the FIRST close in the ticker's price series (day
    one of the simulation), not the latest — initial EPS is anchored to it via
    a plausible entry P/E so valuation ratios stay realistic from day one,
    rather than an independently-random EPS colliding with an unrelated price
    level after a decade of compounding (which produced absurd "fair value"
    multiples before this anchoring was added)."""
    params = FUND_ARCHETYPE[archetype]
    qends = quarter_ends(START_DATE, END_DATE)
    rows = []
    shares = rng.uniform(80, 900)             # millions
    entry_pe = rng.uniform(14, 27)
    annual_eps = start_price / entry_pe
    eps = annual_eps / 4  # `eps` tracks *quarterly* EPS throughout (TTM = sum of 4 quarters below)
    revenue = max(300.0, annual_eps * shares * rng.uniform(6, 14))  # $M, starting base — plausible P/S entry too
    fcf = revenue * rng.uniform(0.05, 0.15)
    debt = revenue * rng.uniform(0.2, 0.9)
    cash = revenue * rng.uniform(0.15, 0.6)

    # Each ticker gets ONE realized growth rate per line item (archetype
    # nominal +/- a per-company random offset), applied consistently every
    # quarter with only small seasonal noise on top. Earlier this drew fresh
    # multiplicative noise every quarter, which is a random walk in the
    # growth *rate* itself — compounded over 41 quarters that produces wildly
    # dispersed realized decade-long growth (and therefore wildly unrealistic
    # trailing valuation multiples) even when the nominal rate is modest.
    realized_rev_g = params["rev_g"] + rng.normal(0, 0.015)
    realized_eps_g = params["eps_g"] + rng.normal(0, 0.02)
    realized_fcf_g = params["fcf_g"] + rng.normal(0, 0.02)

    for i, qend in enumerate(qends):
        revenue *= (1 + realized_rev_g / 4) * rng.normal(1.0, 0.02)
        eps *= (1 + realized_eps_g / 4) * rng.normal(1.0, 0.025)
        fcf *= (1 + realized_fcf_g / 4) * rng.normal(1.0, 0.03)
        debt *= (1 + params["debt_trend"] / 4)
        cash *= (1 + params["cash_trend"] / 4) * rng.normal(1.0, 0.03)
        gm = np.clip(params["gm"] + rng.normal(0, 0.01), 0.05, 0.85)
        om = np.clip(params["om"] + rng.normal(0, 0.01), -0.10, 0.45)
        roic = np.clip(params["roic"] + rng.normal(0, 0.01), -0.10, 0.55)
        roe = np.clip(params["roe"] + rng.normal(0, 0.015), -0.20, 0.60)

        available_on = qend + timedelta(days=int(rng.integers(28, 45)))
        rows.append(dict(
            ticker=ticker, fiscal_period=f"{qend.year}Q{(qend.month - 1)//3 + 1}",
            period_end=qend.isoformat(), available_on=available_on.isoformat(),
            revenue=round(revenue, 2), eps=round(eps, 3), fcf=round(fcf, 2),
            gross_margin=round(gm, 4), operating_margin=round(om, 4),
            roic=round(roic, 4), roe=round(roe, 4),
            debt=round(debt, 2), cash=round(cash, 2), shares_outstanding=round(shares, 2),
        ))
    return rows


def gen_estimates_and_earnings(ticker: str, archetype: str, fundamentals: list[dict],
                                prices_df: pd.DataFrame, rng: np.random.Generator):
    """Derive analyst estimates (slightly noisy vs actual eps/revenue) and an
    earnings_event per quarter with a plausible next-session price reaction
    pulled from the actual generated price series around the report date."""
    estimates, earnings = [], []
    prices_df = prices_df.set_index("date")
    dates_sorted = prices_df.index.tolist()

    beat_bias = {
        "earnings_momentum": 0.06, "compounder": 0.02, "undervalued_quality": 0.015,
        "institutional_accumulation": 0.02, "fallen_angel_good": 0.01,
        "mean_reversion_healthy": 0.01, "insider_accumulation": 0.01,
        "fallen_angel_bad": -0.05, "deteriorating": -0.06,
        "mean_reversion_unhealthy": -0.03, "short_squeeze": -0.02,
        "momentum_breakout": 0.02, "generic_neutral": 0.0,
    }[archetype]

    for i, fq in enumerate(fundamentals):
        report_date = date.fromisoformat(fq["available_on"])
        est_date = date.fromisoformat(fq["period_end"]) - timedelta(days=20)
        eps_actual = fq["eps"]
        eps_est = eps_actual / (1 + beat_bias + rng.normal(0, 0.03))
        rev_actual = fq["revenue"]
        rev_est = rev_actual / (1 + beat_bias * 0.6 + rng.normal(0, 0.02))
        revision = "up" if beat_bias + rng.normal(0, 0.02) > 0.015 else ("down" if beat_bias < -0.02 else "flat")

        estimates.append(dict(
            ticker=ticker, as_of_date=est_date.isoformat(),
            available_on=est_date.isoformat(),
            eps_estimate=round(eps_est, 3), revenue_estimate=round(rev_est, 2),
            analyst_count=int(rng.integers(4, 28)), revision_direction=revision,
        ))

        # find the trading date on/after report_date to read the price reaction
        idx = next((d for d in dates_sorted if d >= report_date.isoformat()), None)
        reaction = 0.0
        if idx is not None:
            pos = dates_sorted.index(idx)
            if pos + 1 < len(dates_sorted):
                p0 = prices_df.loc[dates_sorted[pos], "close"]
                p1 = prices_df.loc[dates_sorted[pos + 1], "close"]
                reaction = (p1 - p0) / p0

        guidance = "raised" if beat_bias > 0.02 else ("lowered" if beat_bias < -0.02 else "maintained")
        earnings.append(dict(
            ticker=ticker, report_date=report_date.isoformat(), available_on=report_date.isoformat(),
            eps_actual=round(eps_actual, 3), eps_estimate=round(eps_est, 3),
            revenue_actual=round(rev_actual, 2), revenue_estimate=round(rev_est, 2),
            guidance_change=guidance, price_reaction_pct=round(reaction * 100, 2),
        ))
    return estimates, earnings


INSIDER_NAMES = ["A. Whitfield (CEO)", "R. Chen (CFO)", "M. Alvarez (COO)", "S. Ito (Director)",
                  "T. Novak (VP Eng)", "L. Osei (Director)", "K. Fournier (CTO)", "D. Marsh (VP Sales)"]


def gen_insider_transactions(ticker: str, archetype: str, days: pd.DatetimeIndex, rng: np.random.Generator, last_price: float):
    rows = []
    n_random = int(rng.integers(6, 14))
    for _ in range(n_random):
        d = days[int(rng.integers(0, len(days)))]
        ttype = "sell" if rng.random() < 0.7 else "buy"
        shares = rng.uniform(1000, 40000)
        price = last_price * rng.uniform(0.6, 1.05)
        rows.append(dict(ticker=ticker, transaction_date=d.date().isoformat(),
                          available_on=(d + timedelta(days=2)).date().isoformat(),
                          insider_name=random.choice(INSIDER_NAMES),
                          insider_role="Officer", transaction_type=ttype,
                          shares=round(shares, 0), price=round(price, 2), value=round(shares * price, 2)))

    if archetype == "insider_accumulation":
        cluster_day = days[-int(rng.integers(15, 40))]
        for name in random.sample(INSIDER_NAMES, k=4):
            d = cluster_day + timedelta(days=int(rng.integers(-5, 5)))
            shares = rng.uniform(8000, 60000)
            price = last_price * rng.uniform(0.95, 1.02)
            rows.append(dict(ticker=ticker, transaction_date=d.date().isoformat(),
                              available_on=(d + timedelta(days=2)).date().isoformat(),
                              insider_name=name, insider_role="Officer/Director",
                              transaction_type="buy", shares=round(shares, 0),
                              price=round(price, 2), value=round(shares * price, 2)))
    return rows


def gen_institutional_ownership(ticker: str, archetype: str, rng: np.random.Generator):
    qends = quarter_ends(START_DATE, END_DATE)
    rows = []
    pct = rng.uniform(35, 65)
    trend = {"institutional_accumulation": 0.9, "compounder": 0.25, "earnings_momentum": 0.3,
              "undervalued_quality": 0.2, "deteriorating": -0.6, "fallen_angel_bad": -0.4,
              "mean_reversion_unhealthy": -0.3}.get(archetype, 0.05)
    for qend in qends:
        change = rng.normal(trend, 1.2)
        pct = float(np.clip(pct + change, 5, 92))
        available_on = qend + timedelta(days=int(rng.integers(30, 48)))
        rows.append(dict(ticker=ticker, period_end=qend.isoformat(),
                          available_on=available_on.isoformat(),
                          pct_ownership=round(pct, 2), change_pct=round(change, 2)))
    return rows


def gen_short_interest(ticker: str, archetype: str, days: pd.DatetimeIndex, rng: np.random.Generator, float_shares: float):
    rows = []
    settlement_dates = days[::10]  # roughly bi-monthly
    base_pct = {"short_squeeze": 0.28, "fallen_angel_bad": 0.14, "deteriorating": 0.12,
                "mean_reversion_unhealthy": 0.11}.get(archetype, 0.045)
    pct = base_pct
    for i, d in enumerate(settlement_dates):
        drift = rng.normal(0, 0.01)
        if archetype == "short_squeeze" and i > len(settlement_dates) - 4:
            drift += 0.03
        pct = float(np.clip(pct + drift, 0.005, 0.45))
        shares = pct * float_shares
        dtc = float(np.clip(rng.normal(3.5 if archetype != "short_squeeze" else 8.5, 1.5), 0.3, 20))
        rows.append(dict(ticker=ticker, settlement_date=d.date().isoformat(),
                          available_on=(d + timedelta(days=14)).date().isoformat(),
                          short_shares=round(shares, 0), days_to_cover=round(dtc, 2)))
    return rows


CATALYST_TYPES = {
    "earnings_momentum": [("guidance", "positive"), ("contract", "positive")],
    "momentum_breakout": [("product_launch", "positive")],
    "fallen_angel_bad": [("regulatory", "negative"), ("guidance", "negative")],
    "deteriorating": [("guidance", "negative")],
    "compounder": [("buyback", "positive")],
    "undervalued_quality": [("buyback", "positive")],
    "institutional_accumulation": [("contract", "positive")],
    "short_squeeze": [("product_launch", "neutral")],
}

CATALYST_DESC = {
    "contract": "Announced a major new supply/services contract",
    "product_launch": "Launched a new flagship product line",
    "regulatory": "Facing a regulatory inquiry into disclosed practices",
    "ma": "Announced a strategic acquisition",
    "buyback": "Board authorized an expanded share buyback program",
    "guidance": "Updated forward guidance",
}


def gen_catalyst_events(ticker: str, archetype: str, days: pd.DatetimeIndex, rng: np.random.Generator):
    rows = []
    for etype, sentiment in CATALYST_TYPES.get(archetype, []):
        d = days[-int(rng.integers(10, 120))]
        rows.append(dict(ticker=ticker, event_date=d.date().isoformat(),
                          available_on=d.date().isoformat(), event_type=etype,
                          description=CATALYST_DESC[etype], sentiment=sentiment))
    return rows
