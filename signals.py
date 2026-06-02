import pandas as pd
import config


def generate_signal(df: pd.DataFrame) -> dict:
    """
    Analyze the last two rows of indicator data and return a signal dict:
    { 'signal': 'buy_call'|'buy_put'|'hold', 'strength': int, 'reasons': list[str] }

    Strength accumulates one point per confirmed indicator:
      - RSI oversold/overbought
      - MACD histogram crossover (zero-line cross)
      - MACD line position relative to signal
      - Price vs EMA alignment
    A trade signal fires when a direction reaches strength >= 2 and leads the other.
    """
    if len(df) < 2:
        return {"signal": "hold", "strength": 0, "reasons": []}

    row = df.iloc[-1]
    prev = df.iloc[-2]

    rsi = row["rsi"]
    macd_hist = row["macd_hist"]
    prev_hist = prev["macd_hist"]
    macd = row["macd"]
    macd_sig = row["macd_signal"]
    price = row["Close"]
    ema_short = row["ema_short"]
    ema_long = row["ema_long"]

    bull = 0.0
    bear = 0.0
    reasons = []

    if rsi < config.RSI_OVERSOLD:
        bull += 1
        reasons.append(f"RSI oversold ({rsi:.1f})")
    elif rsi > config.RSI_OVERBOUGHT:
        bear += 1
        reasons.append(f"RSI overbought ({rsi:.1f})")

    # MACD histogram zero-line crossover (stronger signal)
    if macd_hist > 0 and prev_hist <= 0:
        bull += 1
        reasons.append("MACD bullish crossover")
    elif macd_hist < 0 and prev_hist >= 0:
        bear += 1
        reasons.append("MACD bearish crossover")
    # MACD line vs signal line (weaker, ongoing signal)
    elif macd > macd_sig:
        bull += 0.5
    elif macd < macd_sig:
        bear += 0.5

    # EMA trend alignment
    if price > ema_short > ema_long:
        bull += 1
        reasons.append("Price above rising EMAs (uptrend)")
    elif price < ema_short < ema_long:
        bear += 1
        reasons.append("Price below falling EMAs (downtrend)")

    if bull >= 2 and bull > bear:
        return {"signal": "buy_call", "strength": int(bull), "reasons": reasons}
    if bear >= 2 and bear > bull:
        return {"signal": "buy_put", "strength": int(bear), "reasons": reasons}
    return {"signal": "hold", "strength": 0, "reasons": reasons}
