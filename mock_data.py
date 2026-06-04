"""
Synthetic market data for demo/test mode.
Generates realistic SPY/QQQ price series and options chains
so the full agent pipeline can run without network access.
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random

# Reproducible seed so runs are consistent
_RNG = np.random.default_rng(42)

BASE_PRICES = {"SPY": 530.0, "QQQ": 455.0}
ANNUAL_VOL = 0.16       # 16% annualized volatility
ANNUAL_RET = 0.10       # 10% drift
TRADING_DAYS = 252      # ~1 year (needed for 200-day MA regime filter)


def _gbm_path(s0: float, n: int) -> np.ndarray:
    """
    GBM with a deliberate 8% selloff in the last 15 days followed by a small
    bounce — reliably creates RSI oversold + MACD crossover conditions for demo.
    """
    dt = 1 / 252
    sigma = ANNUAL_VOL
    mu = ANNUAL_RET
    log_returns = _RNG.normal(
        (mu - 0.5 * sigma**2) * dt,
        sigma * np.sqrt(dt),
        size=n,
    )
    # Inject a sharp correction in the last 20 bars then a bounce — creates RSI oversold
    log_returns[-20:-4] += np.linspace(-0.018, -0.010, 16)  # sustained selloff
    log_returns[-4:] += 0.006                                # small bounce
    path = s0 * np.exp(np.cumsum(log_returns))
    return np.concatenate([[s0], path[:-1]])


def get_price_history(ticker: str) -> pd.DataFrame:
    s0 = BASE_PRICES.get(ticker, 500.0)
    closes = _gbm_path(s0, TRADING_DAYS)

    spread = closes * 0.0003
    highs = closes + _RNG.uniform(0, spread * 3, TRADING_DAYS)
    lows = closes - _RNG.uniform(0, spread * 3, TRADING_DAYS)
    opens = closes + _RNG.normal(0, spread, TRADING_DAYS)
    volumes = _RNG.integers(50_000_000, 150_000_000, TRADING_DAYS).astype(float)

    end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dates = pd.bdate_range(end=end, periods=TRADING_DAYS)

    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=dates,
    )


def _bs_approx_call(S, K, T, sigma=0.16, r=0.04):
    """Very rough Black-Scholes approximation for call price."""
    if T <= 0:
        return max(S - K, 0)
    from math import log, sqrt, exp
    try:
        d1 = (log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
        d2 = d1 - sigma * sqrt(T)
        from scipy.special import ndtr
        price = S * ndtr(d1) - K * exp(-r * T) * ndtr(d2)
    except Exception:
        # Fallback: intrinsic + time value heuristic
        intrinsic = max(S - K, 0)
        time_val = S * sigma * (T**0.5) * 0.4
        price = intrinsic + time_val
    return max(price, 0.01)


def _approx_option_price(S, K, T_years, sigma=0.16, r=0.04, opt_type="call"):
    """Rough option price without scipy dependency."""
    from math import log, sqrt, exp, erf

    def norm_cdf(x):
        return 0.5 * (1 + erf(x / sqrt(2)))

    if T_years <= 0:
        return max(S - K, 0) if opt_type == "call" else max(K - S, 0)

    d1 = (log(S / K) + (r + 0.5 * sigma**2) * T_years) / (sigma * sqrt(T_years))
    d2 = d1 - sigma * sqrt(T_years)

    if opt_type == "call":
        price = S * norm_cdf(d1) - K * exp(-r * T_years) * norm_cdf(d2)
    else:
        price = K * exp(-r * T_years) * norm_cdf(-d2) - S * norm_cdf(-d1)

    return max(price, 0.01)


def get_options_chain(ticker: str) -> list:
    """
    Generate a synthetic options chain for a ticker.
    Produces options at multiple expirations (30–180 DTE) and strikes.
    """
    today = datetime.now().date()
    s0 = BASE_PRICES.get(ticker, 500.0)
    # Adjust for any drift in mock price series
    df = get_price_history(ticker)
    S = float(df["Close"].iloc[-1])

    dtes = [35, 65, 95, 125, 155, 175]
    strikes_pcts = [0.92, 0.94, 0.96, 0.98, 1.00, 1.02, 1.04, 1.06, 1.08, 1.10, 1.12, 1.15, 1.18]

    results = []
    for dte in dtes:
        exp_date = today + timedelta(days=dte)
        exp_str = exp_date.strftime("%Y-%m-%d")
        T = dte / 365.0
        sigma = ANNUAL_VOL * _RNG.uniform(0.85, 1.15)  # vary IV per expiry

        for pct in strikes_pcts:
            K = round(S * pct / 5) * 5  # round to nearest $5

            for opt_type in ("call", "put"):
                price = _approx_option_price(S, K, T, sigma=sigma, opt_type=opt_type)
                noise = _RNG.uniform(0.97, 1.03)
                mid = round(price * noise, 2)
                spread = max(mid * 0.04, 0.01)
                bid = round(max(mid - spread, 0.01), 2)
                ask = round(mid + spread, 2)

                volume = int(_RNG.integers(20, 600))
                oi = int(_RNG.integers(100, 3000))

                results.append({
                    "ticker": ticker,
                    "option_type": opt_type,
                    "expiry": exp_str,
                    "dte": dte,
                    "strike": float(K),
                    "lastPrice": mid,
                    "bid": bid,
                    "ask": ask,
                    "volume": volume,
                    "openInterest": oi,
                    "impliedVolatility": sigma,
                    "inTheMoney": (K < S if opt_type == "call" else K > S),
                })

    return results
