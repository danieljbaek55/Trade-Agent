"""
Technical indicators implemented with pandas — no C extensions required.
"""
import pandas as pd
import config


def _ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    df["rsi"] = _rsi(close, config.RSI_PERIOD)

    ema_fast = _ema(close, config.MACD_FAST)
    ema_slow = _ema(close, config.MACD_SLOW)
    df["macd"] = ema_fast - ema_slow
    df["macd_signal"] = _ema(df["macd"], config.MACD_SIGNAL)
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["ema_short"] = _ema(close, config.EMA_SHORT)
    df["ema_long"] = _ema(close, config.EMA_LONG)

    return df
