"""Options analytics: Black-Scholes Greeks, implied volatility, PCR. Pure math, no I/O."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, sqrt

from scipy.stats import norm  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class Greeks:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float


def black_scholes_price(
    spot: float, strike: float, time_to_expiry_years: float, rate: float, volatility: float, is_call: bool
) -> float:
    if time_to_expiry_years <= 0 or volatility <= 0:
        return max(0.0, (spot - strike) if is_call else (strike - spot))

    d1 = (log(spot / strike) + (rate + 0.5 * volatility**2) * time_to_expiry_years) / (
        volatility * sqrt(time_to_expiry_years)
    )
    d2 = d1 - volatility * sqrt(time_to_expiry_years)

    if is_call:
        return spot * norm.cdf(d1) - strike * exp(-rate * time_to_expiry_years) * norm.cdf(d2)
    return strike * exp(-rate * time_to_expiry_years) * norm.cdf(-d2) - spot * norm.cdf(-d1)


def compute_greeks(
    spot: float, strike: float, time_to_expiry_years: float, rate: float, volatility: float, is_call: bool
) -> Greeks:
    if time_to_expiry_years <= 0 or volatility <= 0:
        return Greeks(delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)

    sqrt_t = sqrt(time_to_expiry_years)
    d1 = (log(spot / strike) + (rate + 0.5 * volatility**2) * time_to_expiry_years) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    pdf_d1 = norm.pdf(d1)

    delta = norm.cdf(d1) if is_call else norm.cdf(d1) - 1
    gamma = pdf_d1 / (spot * volatility * sqrt_t)
    vega = spot * pdf_d1 * sqrt_t / 100  # per 1% vol change
    if is_call:
        theta = (
            -spot * pdf_d1 * volatility / (2 * sqrt_t)
            - rate * strike * exp(-rate * time_to_expiry_years) * norm.cdf(d2)
        ) / 365
        rho = strike * time_to_expiry_years * exp(-rate * time_to_expiry_years) * norm.cdf(d2) / 100
    else:
        theta = (
            -spot * pdf_d1 * volatility / (2 * sqrt_t)
            + rate * strike * exp(-rate * time_to_expiry_years) * norm.cdf(-d2)
        ) / 365
        rho = -strike * time_to_expiry_years * exp(-rate * time_to_expiry_years) * norm.cdf(-d2) / 100

    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    rate: float,
    is_call: bool,
    tolerance: float = 1e-4,
    max_iterations: int = 100,
) -> float | None:
    """Newton-Raphson IV solver. Returns None if it fails to converge."""
    volatility = 0.3
    for _ in range(max_iterations):
        price = black_scholes_price(spot, strike, time_to_expiry_years, rate, volatility, is_call)
        greeks = compute_greeks(spot, strike, time_to_expiry_years, rate, volatility, is_call)
        vega = greeks.vega * 100  # undo the /100 scaling for the derivative
        diff = market_price - price
        if abs(diff) < tolerance:
            return volatility
        if vega == 0:
            break
        volatility += diff / vega
        if volatility <= 0:
            volatility = 0.01
    return None


def put_call_ratio(put_oi: float, call_oi: float) -> float | None:
    if call_oi == 0:
        return None
    return put_oi / call_oi
