from typing import Optional
import config


def _mid(opt: dict) -> float:
    """Best-effort mid price; falls back to lastPrice when bid/ask unavailable."""
    bid = opt.get("bid") or 0
    ask = opt.get("ask") or 0
    last = opt.get("lastPrice") or 0
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    return last


def filter_options(options: list, option_type: str, current_price: float) -> list:
    """
    Keep options that meet all of:
      - Correct type (call/put)
      - Mid price <= MAX_PREMIUM_PER_SHARE  (total contract cost <= $100)
      - Mid price > 0
      - Volume OR open interest above minimums
      - Strike 1–20% OTM (direction-appropriate)
    """
    qualified = []
    for opt in options:
        if opt.get("option_type") != option_type:
            continue

        mid = _mid(opt)
        if mid <= 0 or mid > config.MAX_PREMIUM_PER_SHARE:
            continue

        volume = opt.get("volume") or 0
        oi = opt.get("openInterest") or 0
        if volume < config.MIN_VOLUME and oi < config.MIN_OPEN_INTEREST:
            continue

        strike = opt.get("strike") or 0
        if strike <= 0:
            continue

        if option_type == "call":
            ratio = strike / current_price   # >1 means OTM for call
            if not (1.01 <= ratio <= 1.20):
                continue
        else:
            ratio = current_price / strike   # >1 means OTM for put
            if not (1.01 <= ratio <= 1.20):
                continue

        row = opt.copy()
        row["mid_price"] = round(mid, 4)
        row["total_cost"] = round(mid * 100, 2)
        qualified.append(row)

    return qualified


def select_best_option(options: list) -> Optional[dict]:
    """
    Score and return the single best option.
    Weights: 50% DTE (prefer longer duration), 30% volume (prefer liquid), 20% cost (prefer cheaper).
    """
    if not options:
        return None

    def score(opt):
        dte_score = opt["dte"] / config.MAX_DTE
        vol_score = min((opt.get("volume") or 0) / 500, 1.0)
        cost_score = 1.0 - (opt["mid_price"] / config.MAX_PREMIUM_PER_SHARE)
        return dte_score * 0.5 + vol_score * 0.3 + cost_score * 0.2

    return max(options, key=score)
