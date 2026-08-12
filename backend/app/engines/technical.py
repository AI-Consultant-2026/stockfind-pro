"""
Technical/market-behaviour engine — deterministic indicator calculations
from raw OHLCV. No scoring judgement happens here, only indicator math; the
factor_engine turns these into the 0-100 Momentum score, and the strategy
modules read individual fields directly (e.g. "price > 200-day MA").
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def compute_technicals(price_rows: list[dict], benchmark_rows: list[dict] | None = None) -> dict:
    if len(price_rows) < 5:
        return {"insufficient_data": True}

    df = pd.DataFrame(price_rows)
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    n = len(df)

    sma20 = close.rolling(20, min_periods=1).mean()
    sma50 = close.rolling(50, min_periods=1).mean()
    sma200 = close.rolling(200, min_periods=1).mean()

    last_close = float(close.iloc[-1])

    # RSI-14 (Wilder's smoothing)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=1, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(50)

    # MACD (12,26,9)
    macd_line = _ema(close, 12) - _ema(close, 26)
    macd_signal = _ema(macd_line, 9)
    macd_hist = macd_line - macd_signal

    # ATR-14
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr14 = tr.ewm(alpha=1 / 14, min_periods=1, adjust=False).mean()

    # Bollinger Bands (20, 2 std)
    std20 = close.rolling(20, min_periods=1).std().fillna(0)
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    bb_width = (bb_upper - bb_lower).replace(0, np.nan)
    bb_pct = ((close - bb_lower) / bb_width).fillna(0.5)

    # Volume
    avg_vol20 = volume.rolling(20, min_periods=1).mean()
    volume_ratio = float(volume.iloc[-1] / avg_vol20.iloc[-1]) if avg_vol20.iloc[-1] else 1.0
    # recent volume trend: last 5d avg vs prior 20d avg (volume acceleration)
    recent_vol5 = float(volume.tail(5).mean())
    prior_vol20 = float(volume.tail(40).head(20).mean()) if n >= 40 else float(avg_vol20.iloc[-1])
    volume_acceleration = recent_vol5 / prior_vol20 if prior_vol20 else 1.0

    # 52-week (up to 252 trading days) high/low
    window = min(n, 252)
    high_52w = float(high.tail(window).max())
    low_52w = float(low.tail(window).min())
    pct_from_52w_high = (last_close - high_52w) / high_52w * 100
    pct_from_52w_low = (last_close - low_52w) / low_52w * 100

    # Higher highs: most recent 20-day high exceeds the 20-day high from 20 sessions earlier
    higher_highs = False
    if n >= 45:
        recent_high = high.tail(20).max()
        prior_high = high.tail(40).head(20).max()
        higher_highs = bool(recent_high > prior_high)

    # Gap %: most recent day's open vs prior close
    gap_pct = 0.0
    if n >= 2:
        gap_pct = float((df["open"].iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100)

    # Historical volatility (annualized, 21-day)
    log_ret = np.log(close / close.shift(1))
    hist_vol_21d = float(log_ret.tail(21).std() * np.sqrt(252)) if n >= 5 else 0.0

    # Momentum returns over multiple horizons
    def ret_over(days):
        if n <= days:
            return None
        return float(close.iloc[-1] / close.iloc[-1 - days] - 1) * 100

    mom_21d, mom_63d, mom_126d, mom_252d = ret_over(21), ret_over(63), ret_over(126), ret_over(min(252, n - 1))

    # Relative strength vs benchmark (63-day)
    rel_strength_63d = None
    if benchmark_rows and len(benchmark_rows) >= 64:
        bdf = pd.DataFrame(benchmark_rows).set_index("date")["close"]
        common_dates = df["date"].tail(64).tolist()
        try:
            b0 = bdf.loc[common_dates[0]]
            b1 = bdf.loc[common_dates[-1]]
            bench_ret = (b1 / b0 - 1) * 100
            rel_strength_63d = (mom_63d or 0) - bench_ret
        except KeyError:
            rel_strength_63d = None

    # Trend strength: % of last 50 sessions closing above the 50-day MA (simple, robust proxy for ADX)
    above_sma50_series = (close >= sma50).tail(50)
    trend_strength = float(above_sma50_series.mean() * 100) if len(above_sma50_series) else 50.0

    return {
        "insufficient_data": False,
        "close": last_close,
        "sma20": float(sma20.iloc[-1]), "sma50": float(sma50.iloc[-1]), "sma200": float(sma200.iloc[-1]),
        "above_sma20": last_close > sma20.iloc[-1],
        "above_sma50": last_close > sma50.iloc[-1],
        "above_sma200": last_close > sma200.iloc[-1],
        "rsi14": float(rsi.iloc[-1]),
        "macd": float(macd_line.iloc[-1]), "macd_signal": float(macd_signal.iloc[-1]),
        "macd_hist": float(macd_hist.iloc[-1]),
        "macd_bullish": bool(macd_line.iloc[-1] > macd_signal.iloc[-1]),
        "atr14": float(atr14.iloc[-1]),
        "atr_pct": float(atr14.iloc[-1] / last_close * 100) if last_close else 0.0,
        "bb_upper": float(bb_upper.iloc[-1]), "bb_lower": float(bb_lower.iloc[-1]), "bb_pct": float(bb_pct.iloc[-1]),
        "volume": float(volume.iloc[-1]), "avg_volume20": float(avg_vol20.iloc[-1]),
        "volume_ratio": volume_ratio, "volume_acceleration": volume_acceleration,
        "high_52w": high_52w, "low_52w": low_52w,
        "pct_from_52w_high": pct_from_52w_high, "pct_from_52w_low": pct_from_52w_low,
        "higher_highs": higher_highs, "gap_pct": gap_pct,
        "hist_vol_21d": hist_vol_21d,
        "mom_21d": mom_21d, "mom_63d": mom_63d, "mom_126d": mom_126d, "mom_252d": mom_252d,
        "rel_strength_63d": rel_strength_63d,
        "trend_strength": trend_strength,
    }
