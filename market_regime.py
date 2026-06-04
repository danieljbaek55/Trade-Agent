"""
Simple market regime filter — inspired by the breadth-analyzer concept in
claude-trading-skills, scaled down to what we can compute from SPY price alone.

Regime states:
  STRONG_BULL : SPY > 200MA, 50MA > 200MA, 200MA rising      → allow calls only
  BULL        : SPY > 200MA, 50MA > 200MA                    → allow calls only
  NEUTRAL     : SPY near 200MA OR mixed signals              → allow both (caution)
  BEAR        : SPY < 200MA, 50MA < 200MA                    → allow puts only
  STRONG_BEAR : SPY < 200MA, 50MA < 200MA, 200MA falling     → allow puts only
"""
import pandas as pd


def _slope(series: pd.Series, lookback: int = 20) -> float:
    """% change over lookback window."""
    if len(series) < lookback:
        return 0.0
    return (series.iloc[-1] / series.iloc[-lookback] - 1) * 100


def detect_regime(df: pd.DataFrame) -> dict:
    """
    Classify regime from a DataFrame that already has price history.
    Requires at least ~210 daily bars for the 200MA to be valid.
    """
    close = df["Close"]
    if len(close) < 50:
        return {
            "regime": "UNKNOWN",
            "allow_calls": True,
            "allow_puts": True,
            "reason": "Insufficient history",
        }

    price = float(close.iloc[-1])
    ma50 = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(min(200, len(close))).mean().iloc[-1])
    ma200_slope = _slope(close.rolling(min(200, len(close))).mean(), 20)

    price_vs_200 = (price / ma200 - 1) * 100
    ma50_vs_200 = (ma50 / ma200 - 1) * 100

    if price > ma200 and ma50 > ma200 and ma200_slope > 0.5:
        regime = "STRONG_BULL"
    elif price > ma200 and ma50 > ma200:
        regime = "BULL"
    elif price < ma200 and ma50 < ma200 and ma200_slope < -0.5:
        regime = "STRONG_BEAR"
    elif price < ma200 and ma50 < ma200:
        regime = "BEAR"
    else:
        regime = "NEUTRAL"

    allow_calls = regime in ("STRONG_BULL", "BULL", "NEUTRAL")
    allow_puts = regime in ("STRONG_BEAR", "BEAR", "NEUTRAL")

    return {
        "regime": regime,
        "allow_calls": allow_calls,
        "allow_puts": allow_puts,
        "price_vs_200ma_pct": round(price_vs_200, 2),
        "ma50_vs_200ma_pct": round(ma50_vs_200, 2),
        "ma200_slope_20d_pct": round(ma200_slope, 2),
        "reason": (
            f"Price {price_vs_200:+.1f}% vs 200MA, "
            f"50MA {ma50_vs_200:+.1f}% vs 200MA, "
            f"200MA slope {ma200_slope:+.1f}%/20d"
        ),
    }
