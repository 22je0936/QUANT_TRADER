from __future__ import annotations

import pandas as pd

from src.indicators.technical import atr, bollinger_bands, ema, macd, rsi, sma, vwap


def _close_series() -> pd.Series:
    return pd.Series([10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18, 17, 19, 20], dtype=float)


def test_sma_matches_manual_average():
    close = pd.Series([1, 2, 3, 4, 5], dtype=float)
    result = sma(close, period=3)
    assert result.iloc[2] == 2.0
    assert result.iloc[4] == 4.0
    assert pd.isna(result.iloc[1])


def test_ema_is_defined_after_period_and_reacts_to_trend():
    close = _close_series()
    result = ema(close, period=5)
    assert pd.isna(result.iloc[3])
    assert result.iloc[-1] > result.iloc[4]  # uptrend pulls EMA up


def test_rsi_is_bounded_between_0_and_100():
    close = _close_series()
    result = rsi(close, period=5).dropna()
    assert (result >= 0).all()
    assert (result <= 100).all()


def test_macd_returns_expected_columns():
    close = _close_series()
    result = macd(close, fast=3, slow=6, signal=3)
    assert list(result.columns) == ["macd", "signal", "histogram"]
    assert (result["histogram"].dropna() == (result["macd"] - result["signal"]).dropna()).all()


def test_atr_is_non_negative():
    high = pd.Series([10, 11, 12, 13, 14], dtype=float)
    low = pd.Series([8, 9, 10, 11, 12], dtype=float)
    close = pd.Series([9, 10, 11, 12, 13], dtype=float)
    result = atr(high, low, close, period=3).dropna()
    assert (result >= 0).all()


def test_vwap_is_between_min_and_max_price():
    high = pd.Series([10, 11, 12], dtype=float)
    low = pd.Series([8, 9, 10], dtype=float)
    close = pd.Series([9, 10, 11], dtype=float)
    volume = pd.Series([100, 200, 300], dtype=float)
    result = vwap(high, low, close, volume)
    assert (result >= low.min()).all()
    assert (result <= high.max()).all()


def test_bollinger_bands_upper_above_lower():
    close = _close_series()
    result = bollinger_bands(close, period=5).dropna()
    assert (result["upper"] >= result["middle"]).all()
    assert (result["middle"] >= result["lower"]).all()
