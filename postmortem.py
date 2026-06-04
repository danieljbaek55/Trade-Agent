"""
Trade postmortem analysis — inspired by signal-postmortem in claude-trading-skills.
Classifies closed trades into outcome categories and aggregates win-rate metrics
by signal type and regime.
"""
from datetime import datetime


def classify(trade: dict) -> str:
    """
    Categorize a closed trade:
      TRUE_POSITIVE        — signal direction matched outcome (profitable)
      FALSE_POSITIVE       — signal direction wrong, exited at loss
      EXPIRED_WORTHLESS    — held to expiry with exit price ~0
      THETA_DECAY          — moderate loss with no big move (time decay won)
      REGIME_MISMATCH      — entry regime opposed signal direction
    """
    pnl = trade.get("pnl", 0)
    pnl_pct = trade.get("pnl_pct", 0)
    reason = trade.get("exit_reason", "")
    exit_price = trade.get("exit_price", 0)

    if reason == "expired" or exit_price < 0.05:
        return "EXPIRED_WORTHLESS"

    if pnl > 0:
        return "TRUE_POSITIVE"

    # Loss cases — distinguish "wrong direction" from "time decay"
    if reason == "stop_loss" and pnl_pct <= -45:
        return "FALSE_POSITIVE"

    if -45 < pnl_pct < 0:
        return "THETA_DECAY"

    return "FALSE_POSITIVE"


def analyze(closed_trades: list) -> dict:
    """Return aggregated metrics across all closed trades."""
    if not closed_trades:
        return {"count": 0}

    classified = []
    for t in closed_trades:
        t = dict(t)
        t["outcome"] = classify(t)
        classified.append(t)

    total = len(classified)
    wins = sum(1 for t in classified if t["outcome"] == "TRUE_POSITIVE")
    total_pnl = sum(t.get("pnl", 0) for t in classified)
    total_cost = sum(t.get("cost", 0) for t in classified)

    by_outcome: dict = {}
    for t in classified:
        by_outcome.setdefault(t["outcome"], []).append(t)

    by_signal: dict = {}
    for t in classified:
        opt_type = t.get("option_type", "?")
        bucket = by_signal.setdefault(opt_type, {"trades": 0, "wins": 0, "pnl": 0.0})
        bucket["trades"] += 1
        bucket["pnl"] += t.get("pnl", 0)
        if t["outcome"] == "TRUE_POSITIVE":
            bucket["wins"] += 1

    avg_win = (
        sum(t["pnl"] for t in classified if t["pnl"] > 0)
        / max(wins, 1)
    )
    losses = [t for t in classified if t["pnl"] <= 0]
    avg_loss = sum(t["pnl"] for t in losses) / max(len(losses), 1)
    expectancy = (wins / total) * avg_win + (len(losses) / total) * avg_loss

    return {
        "count": total,
        "wins": wins,
        "losses": len(losses),
        "win_rate_pct": round(wins / total * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "total_cost_basis": round(total_cost, 2),
        "roi_pct": round(total_pnl / total_cost * 100, 1) if total_cost > 0 else 0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy_per_trade": round(expectancy, 2),
        "by_outcome": {k: len(v) for k, v in by_outcome.items()},
        "by_signal_type": {
            k: {
                "trades": v["trades"],
                "wins": v["wins"],
                "win_rate_pct": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0,
                "total_pnl": round(v["pnl"], 2),
            }
            for k, v in by_signal.items()
        },
    }
