"""
Backtesting engine — source doc §18: "a beautiful-looking strategy can be
useless once tested properly." Runs a monthly-rebalance, equal-weight
simulation of a strategy over a historical window, using only data that was
actually available as of each rebalance date (via DataProvider's `as_of`
contract — see data_providers/base.py), then reports the standard suite of
performance metrics: annualized return, S&P 500 comparison, max drawdown,
Sharpe, Sortino, win rate, average gain/loss, profit factor, number of
trades, and turnover.

Look-ahead-bias & survivorship-bias notes:
  - Every fundamental/estimate/ownership/short-interest value is filtered by
    its `available_on` timestamp <= the rebalance date, never the nominal
    period date — the same discipline the live scanner uses (see
    factor_engine.score_stock, which this engine calls directly).
  - Because the simulated universe is fixed (fictional companies, none of
    which "delist"), this MVP does not yet model true survivorship bias
    (companies that went to zero and dropped out of a real index). A live
    deployment against real data must source a *point-in-time constituent
    list* for whatever universe it screens, not today's list applied
    retroactively — that is the actual survivorship-bias fix, noted here so
    it isn't lost when this engine is pointed at live data.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from ..data_providers.base import DataProvider
from ..engines.factor_engine import score_stock
from ..engines.strategies import STRATEGY_MODULES

STRATEGY_BY_ID = {}
for _mod in STRATEGY_MODULES:
    _dummy_id = _mod.__name__.rsplit(".", 1)[-1]
    STRATEGY_BY_ID[_dummy_id] = _mod


def monthly_rebalance_dates(start: date, end: date, trading_dates: list[str]) -> list[str]:
    """First available trading date on/after the 1st of each calendar month."""
    dates = []
    cursor = date(start.year, start.month, 1)
    td_sorted = trading_dates
    while cursor <= end:
        floor = cursor.isoformat()
        # first trading date >= floor
        import bisect
        idx = bisect.bisect_left(td_sorted, floor)
        if idx < len(td_sorted) and td_sorted[idx] <= end.isoformat():
            dates.append(td_sorted[idx])
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return dates


def passes_custom_rules(bundle: dict, rules: dict) -> bool:
    f, t, s = bundle["fundamental"], bundle["technical"], bundle["scores"]
    if f.get("insufficient_data") or t.get("insufficient_data"):
        return False
    if "min_roic" in rules and (f.get("roic") or -9) < rules["min_roic"]:
        return False
    if "min_eps_growth" in rules and (f.get("eps_growth_yoy") or -9) < rules["min_eps_growth"]:
        return False
    if rules.get("require_above_200ma") and not t["above_sma200"]:
        return False
    if "min_momentum_score" in rules and s["momentum"] < rules["min_momentum_score"]:
        return False
    if "min_volume_ratio" in rules and t["volume_ratio"] < rules["min_volume_ratio"]:
        return False
    if "min_quality_score" in rules and s["quality"] < rules["min_quality_score"]:
        return False
    return True


def select_universe(provider: DataProvider, as_of: date, strategy_id: str | None, rules: dict | None,
                     top_n: int, sector_filter: str | None = None) -> list[dict]:
    companies = provider.get_universe()
    candidates = []
    for c in companies:
        if sector_filter and c["sector"] != sector_filter:
            continue
        bundle = score_stock(c["ticker"], as_of, provider)
        if not bundle:
            continue
        if strategy_id:
            mod = STRATEGY_BY_ID.get(strategy_id)
            if not mod:
                continue
            result = mod.evaluate(bundle)
            if not result["qualifies"]:
                continue
            rank_score = result["opportunity_score"]
        else:
            if not passes_custom_rules(bundle, rules or {}):
                continue
            rank_score = bundle["scores"]["momentum"] * 0.4 + bundle["scores"]["quality"] * 0.6
        candidates.append((rank_score, bundle))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [b for _, b in candidates[:top_n]]


def price_on_or_after(provider: DataProvider, ticker: str, d: date, max_lookahead: int = 10) -> float | None:
    rows = provider.get_prices(ticker, d + timedelta(days=max_lookahead), lookback_days=max_lookahead + 5)
    for r in rows:
        if r["date"] >= d.isoformat():
            return r["close"]
    return rows[-1]["close"] if rows else None


def run_backtest(provider: DataProvider, start_date: date, end_date: date, top_n: int = 12,
                  strategy_id: str | None = None, rules: dict | None = None,
                  sector_filter: str | None = None) -> dict:
    all_dates = sorted({r["date"] for df in provider.prices.values() for r in df.to_dict("records")}) \
        if hasattr(provider, "prices") else None
    # SimulatedProvider stores per-ticker DataFrames; use SPX benchmark dates as the trading calendar.
    bench_rows = provider.get_benchmark_prices("SPX", end_date, lookback_days=100000)
    trading_dates = [r["date"] for r in bench_rows if start_date.isoformat() <= r["date"] <= end_date.isoformat()]
    if not trading_dates:
        return {"error": "No trading data in the requested range."}

    rebalances = monthly_rebalance_dates(start_date, end_date, trading_dates)
    if len(rebalances) < 2:
        return {"error": "Date range too short for a monthly-rebalance backtest (need >= 2 months)."}

    equity = 1.0
    equity_curve = [{"date": rebalances[0], "equity": equity}]
    trade_returns: list[float] = []
    prior_holdings: set[str] = set()
    turnovers: list[float] = []

    bench_by_date = {r["date"]: r["close"] for r in bench_rows}
    bench_start = bench_by_date.get(rebalances[0])
    bench_curve = [{"date": rebalances[0], "close": bench_start}]

    for i in range(len(rebalances) - 1):
        d0 = date.fromisoformat(rebalances[i])
        d1 = date.fromisoformat(rebalances[i + 1])

        selected = select_universe(provider, d0, strategy_id, rules, top_n, sector_filter)
        tickers = [b["ticker"] for b in selected]

        if tickers:
            turnover = len(set(tickers) - prior_holdings) / len(tickers)
        else:
            turnover = 0.0
        turnovers.append(turnover)
        prior_holdings = set(tickers)

        if not tickers:
            equity_curve.append({"date": rebalances[i + 1], "equity": equity})
            bench_curve.append({"date": rebalances[i + 1], "close": bench_by_date.get(rebalances[i + 1])})
            continue

        period_returns = []
        for b in selected:
            p0 = b["price"]
            p1 = price_on_or_after(provider, b["ticker"], d1)
            if p0 and p1:
                r = (p1 - p0) / p0
                period_returns.append(r)
                trade_returns.append(r)

        if period_returns:
            port_return = sum(period_returns) / len(period_returns)
            equity *= (1 + port_return)
        equity_curve.append({"date": rebalances[i + 1], "equity": round(equity, 6)})
        bench_curve.append({"date": rebalances[i + 1], "close": bench_by_date.get(rebalances[i + 1])})

    metrics = compute_metrics(equity_curve, bench_curve, trade_returns, turnovers, start_date, end_date)
    return {
        "strategy_id": strategy_id, "rules": rules, "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(), "top_n": top_n, "sector_filter": sector_filter,
        "equity_curve": equity_curve, "benchmark_curve": bench_curve, "metrics": metrics,
    }


def compute_metrics(equity_curve: list[dict], bench_curve: list[dict], trade_returns: list[float],
                     turnovers: list[float], start_date: date, end_date: date) -> dict:
    equities = [pt["equity"] for pt in equity_curve]
    period_returns = [(equities[i] / equities[i - 1] - 1) for i in range(1, len(equities)) if equities[i - 1]]

    years = max((end_date - start_date).days / 365.25, 0.08)
    total_return = equities[-1] / equities[0] - 1 if equities[0] else 0.0
    annualized_return = (equities[-1] / equities[0]) ** (1 / years) - 1 if equities[0] and equities[-1] > 0 else -1.0

    bench_closes = [pt["close"] for pt in bench_curve if pt["close"] is not None]
    bench_total_return = (bench_closes[-1] / bench_closes[0] - 1) if len(bench_closes) >= 2 and bench_closes[0] else 0.0
    bench_annualized = (bench_closes[-1] / bench_closes[0]) ** (1 / years) - 1 if len(bench_closes) >= 2 and bench_closes[0] else 0.0

    # Max drawdown on the equity curve
    peak = -math.inf
    max_dd = 0.0
    for e in equities:
        peak = max(peak, e)
        if peak > 0:
            max_dd = min(max_dd, (e - peak) / peak)

    n_periods = len(period_returns)
    periods_per_year = 12
    if n_periods >= 2:
        mean_r = sum(period_returns) / n_periods
        var_r = sum((r - mean_r) ** 2 for r in period_returns) / (n_periods - 1)
        std_r = math.sqrt(var_r)
        downside = [r for r in period_returns if r < 0]
        downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside)) if downside else 0.0
        sharpe = (mean_r / std_r * math.sqrt(periods_per_year)) if std_r > 1e-9 else None
        sortino = (mean_r / downside_std * math.sqrt(periods_per_year)) if downside_std > 1e-9 else None
    else:
        sharpe = sortino = None

    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r <= 0]
    win_rate = len(wins) / len(trade_returns) * 100 if trade_returns else None
    avg_gain = (sum(wins) / len(wins) * 100) if wins else None
    avg_loss = (sum(losses) / len(losses) * 100) if losses else None
    gross_gain = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_gain / gross_loss) if gross_loss > 1e-9 else None

    return {
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(annualized_return * 100, 2),
        "benchmark_total_return_pct": round(bench_total_return * 100, 2),
        "benchmark_annualized_return_pct": round(bench_annualized * 100, 2),
        "excess_annualized_pct": round((annualized_return - bench_annualized) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 2) if sortino is not None else None,
        "win_rate_pct": round(win_rate, 1) if win_rate is not None else None,
        "avg_gain_pct": round(avg_gain, 2) if avg_gain is not None else None,
        "avg_loss_pct": round(avg_loss, 2) if avg_loss is not None else None,
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "number_of_trades": len(trade_returns),
        "avg_turnover_pct": round(sum(turnovers) / len(turnovers) * 100, 1) if turnovers else None,
        "rebalances": len(equity_curve) - 1,
    }
