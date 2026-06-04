"""
Black-Scholes Greeks for European options.
Used to surface delta/theta/gamma/vega at trade entry and in exit checks.
Pure standard library — no scipy dependency.
"""
from math import log, sqrt, exp, erf, pi
from datetime import datetime


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def _norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2 * pi)


def days_to_years(dte: int) -> float:
    return max(dte, 0) / 365.0


def calculate_greeks(
    S: float,
    K: float,
    dte: int,
    sigma: float,
    opt_type: str,
    r: float = 0.04,
) -> dict:
    """
    Return per-share Greeks for one option contract.
    Multiply delta/gamma by 100 for "per contract" share exposure when reporting.
    """
    T = days_to_years(dte)
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

    sqrt_T = sqrt(T)
    d1 = (log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    pdf_d1 = _norm_pdf(d1)
    discount = exp(-r * T)

    if opt_type == "call":
        delta = _norm_cdf(d1)
        theta = (
            -(S * pdf_d1 * sigma) / (2 * sqrt_T)
            - r * K * discount * _norm_cdf(d2)
        ) / 365.0
    else:
        delta = _norm_cdf(d1) - 1
        theta = (
            -(S * pdf_d1 * sigma) / (2 * sqrt_T)
            + r * K * discount * _norm_cdf(-d2)
        ) / 365.0

    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vega = S * pdf_d1 * sqrt_T / 100  # per 1% IV move

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 4),   # per-day $ change per share
        "vega": round(vega, 4),
    }


def estimate_greeks_for_option(opt: dict, underlying_price: float) -> dict:
    """
    Wrap calculate_greeks with sane defaults pulled from option dict.
    Uses impliedVolatility if available, else falls back to 25% (typical SPY/QQQ).
    """
    sigma = opt.get("impliedVolatility") or 0.25
    if sigma <= 0 or sigma > 3.0:
        sigma = 0.25  # sometimes yfinance returns 0 or absurd values
    return calculate_greeks(
        S=underlying_price,
        K=opt["strike"],
        dte=opt["dte"],
        sigma=sigma,
        opt_type=opt["option_type"],
    )


def days_remaining(expiry_str: str) -> int:
    expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    return (expiry - datetime.now().date()).days
