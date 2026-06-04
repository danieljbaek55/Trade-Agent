import json
import os
import uuid
from datetime import datetime
import config

_EMPTY = {
    "account_size": config.ACCOUNT_SIZE,
    "cash": config.ACCOUNT_SIZE,
    "positions": [],
    "closed_trades": [],
}


def load() -> dict:
    if os.path.exists(config.PORTFOLIO_FILE):
        with open(config.PORTFOLIO_FILE) as f:
            return json.load(f)
    return dict(_EMPTY)


def save(portfolio: dict):
    with open(config.PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)


def open_positions(portfolio: dict) -> list:
    return [p for p in portfolio["positions"] if p["status"] == "open"]


def can_open(portfolio: dict) -> bool:
    """Room for another position (count + minimum cash for at least one contract)."""
    min_contract = 50.0   # need at least $50 to buy any contract
    return (
        len(open_positions(portfolio)) < config.MAX_POSITIONS
        and portfolio["cash"] >= min_contract
    )


def open_trade(portfolio: dict, opt: dict) -> dict:
    contracts = int(opt.get("contracts", 1))
    cost_per = float(opt["total_cost"])           # $ per contract (mid * 100)
    total_cost = round(cost_per * contracts, 2)

    position = {
        "id": str(uuid.uuid4())[:8],
        "ticker": opt["ticker"],
        "option_type": opt["option_type"],
        "strike": opt["strike"],
        "expiry": opt["expiry"],
        "dte_at_entry": opt["dte"],
        "contracts": contracts,
        "entry_price": opt["mid_price"],
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "cost_per_contract": cost_per,
        "cost": total_cost,
        "status": "open",
        "signal_reasons": opt.get("signal_reasons", []),
        "signal_strength": opt.get("signal_strength"),
        "conviction_tier": opt.get("conviction_tier"),
        "regime_at_entry": opt.get("regime_at_entry"),
        "greeks_at_entry": opt.get("greeks"),
        "order_id": opt.get("order_id"),
        "occ_symbol": opt.get("occ_symbol"),
    }
    portfolio["cash"] = round(portfolio["cash"] - total_cost, 2)
    portfolio["positions"].append(position)
    save(portfolio)
    return position


def close_trade(portfolio: dict, position_id: str, exit_price: float, reason: str) -> dict:
    for pos in portfolio["positions"]:
        if pos["id"] != position_id or pos["status"] != "open":
            continue

        contracts = int(pos.get("contracts", 1))
        proceeds = round(exit_price * 100 * contracts, 2)
        pnl = round(proceeds - pos["cost"], 2)
        pnl_pct = round(pnl / pos["cost"] * 100, 2) if pos["cost"] else 0

        pos.update(
            status="closed",
            exit_price=exit_price,
            exit_date=datetime.now().strftime("%Y-%m-%d"),
            exit_reason=reason,
            proceeds=proceeds,
            pnl=pnl,
            pnl_pct=pnl_pct,
        )
        portfolio["cash"] = round(portfolio["cash"] + proceeds, 2)
        portfolio["closed_trades"].append(pos)
        portfolio["positions"] = [p for p in portfolio["positions"] if p["id"] != position_id]
        save(portfolio)
        return pos

    return {}
