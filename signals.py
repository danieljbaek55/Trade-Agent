"""
Generate buy_call / buy_put / hold signals from indicator data.

Strength scoring (max 4):
  +1  RSI oversold/overbought
  +1  RSI extreme (<25 or >75)          (additive on top of basic RSI point)
  +1  MACD histogram zero-line crossover
  +0.5 MACD line above/below signal     (no fresh crossover)
  +1  Price + EMA trend alignment
  +1  Market regime confirms direction

Final tier mapping (in agent.py):
  strength < 3       → hold
  strength = 3       → STANDARD
  strength >= 4      → HIGH_CONVICTION ("perfect setup")
"""
import pandas as pd
import config


def generate_signal(df: pd.DataFrame, regime: dict | None = None) -> dict:
    """
    Returns:
      {
        'signal': 'buy_call' | 'buy_put' | 'hold',
        'strength': float,
        'tier': 'NONE' | 'STANDARD' | 'HIGH_CONVICTION',
        'reasons': list[str],
      }
    """
    if len(df) < 2:
        return {"signal": "hold", "strength": 0, "tier": "NONE", "reasons": []}

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

    # --- RSI ---
    if rsi < config.RSI_EXTREME_LOW:
        bull += 2
        reasons.append(f"RSI extreme oversold ({rsi:.1f})")
    elif rsi < config.RSI_OVERSOLD:
        bull += 1
        reasons.append(f"RSI oversold ({rsi:.1f})")
    elif rsi > config.RSI_EXTREME_HIGH:
        bear += 2
        reasons.append(f"RSI extreme overbought ({rsi:.1f})")
    elif rsi > config.RSI_OVERBOUGHT:
        bear += 1
        reasons.append(f"RSI overbought ({rsi:.1f})")

    # --- MACD ---
    if macd_hist > 0 and prev_hist <= 0:
        bull += 1
        reasons.append("MACD bullish crossover")
    elif macd_hist < 0 and prev_hist >= 0:
        bear += 1
        reasons.append("MACD bearish crossover")
    elif macd > macd_sig:
        bull += 0.5
    elif macd < macd_sig:
        bear += 0.5

    # --- EMA trend ---
    if price > ema_short > ema_long:
        bull += 1
        reasons.append("Price above rising EMAs (uptrend)")
    elif price < ema_short < ema_long:
        bear += 1
        reasons.append("Price below falling EMAs (downtrend)")

    # --- Regime alignment (unlocks the HIGH_CONVICTION tier) ---
    if regime:
        regime_name = regime.get("regime", "")
        if regime_name in ("BULL", "STRONG_BULL") and bull > bear:
            bull += 1
            reasons.append(f"Regime aligned ({regime_name})")
        elif regime_name in ("BEAR", "STRONG_BEAR") and bear > bull:
            bear += 1
            reasons.append(f"Regime aligned ({regime_name})")

    # --- Pick direction ---
    if bull >= config.MIN_SIGNAL_STRENGTH and bull > bear:
        strength = bull
        signal = "buy_call"
    elif bear >= config.MIN_SIGNAL_STRENGTH and bear > bull:
        strength = bear
        signal = "buy_put"
    else:
        return {"signal": "hold", "strength": max(bull, bear), "tier": "NONE", "reasons": reasons}

    tier = "HIGH_CONVICTION" if strength >= config.HIGH_CONVICTION_THRESHOLD else "STANDARD"
    return {"signal": signal, "strength": strength, "tier": tier, "reasons": reasons}
