from __future__ import annotations

from src.options_analytics.greeks import (
    black_scholes_price,
    compute_greeks,
    implied_volatility,
    put_call_ratio,
)


def test_call_price_increases_with_spot():
    low_spot = black_scholes_price(spot=90, strike=100, time_to_expiry_years=0.5, rate=0.05, volatility=0.2, is_call=True)
    high_spot = black_scholes_price(spot=110, strike=100, time_to_expiry_years=0.5, rate=0.05, volatility=0.2, is_call=True)
    assert high_spot > low_spot


def test_call_delta_between_0_and_1():
    greeks = compute_greeks(spot=100, strike=100, time_to_expiry_years=0.5, rate=0.05, volatility=0.2, is_call=True)
    assert 0 <= greeks.delta <= 1


def test_put_delta_between_minus1_and_0():
    greeks = compute_greeks(spot=100, strike=100, time_to_expiry_years=0.5, rate=0.05, volatility=0.2, is_call=False)
    assert -1 <= greeks.delta <= 0


def test_implied_volatility_recovers_known_volatility():
    true_vol = 0.25
    price = black_scholes_price(spot=100, strike=100, time_to_expiry_years=0.5, rate=0.05, volatility=true_vol, is_call=True)
    solved_vol = implied_volatility(price, spot=100, strike=100, time_to_expiry_years=0.5, rate=0.05, is_call=True)
    assert solved_vol is not None
    assert abs(solved_vol - true_vol) < 0.01


def test_put_call_ratio():
    assert put_call_ratio(put_oi=200, call_oi=100) == 2.0
    assert put_call_ratio(put_oi=100, call_oi=0) is None
