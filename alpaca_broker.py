"""
Alpaca paper trading broker integration.
All functions require ALPACA_API_KEY and ALPACA_API_SECRET in the environment.
Call is_configured() before using any other function.
"""
import os
import re
from datetime import datetime, timedelta
from typing import Optional


def is_configured() -> bool:
    return bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"))


def _key() -> tuple[str, str]:
    return os.environ["ALPACA_API_KEY"], os.environ["ALPACA_API_SECRET"]


def _trading_client():
    from alpaca.trading.client import TradingClient
    k, s = _key()
    return TradingClient(k, s, paper=True)


def _stock_data_client():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    k, s = _key()
    return StockHistoricalDataClient(k, s)


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------

def get_account() -> dict:
    acct = _trading_client().get_account()
    return {
        "cash": float(acct.cash),
        "portfolio_value": float(acct.portfolio_value),
        "buying_power": float(acct.buying_power),
        "status": str(acct.status),
    }


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

def get_stock_bars(ticker: str, days: int = 180):
    """Return a daily OHLCV DataFrame for `ticker` covering the last `days` calendar days."""
    import pandas as pd
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = _stock_data_client()
    start = datetime.now() - timedelta(days=days)
    req = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=TimeFrame.Day,
        start=start,
    )
    bars = client.get_stock_bars(req)
    df = bars.df

    # Multi-index when multiple symbols requested; drop the symbol level
    if isinstance(df.index, pd.MultiIndex):
        df = df.xs(ticker, level="symbol")

    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.rename(columns={
        "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume",
    })
    return df[["Open", "High", "Low", "Close", "Volume"]]


# ---------------------------------------------------------------------------
# Options orders
# ---------------------------------------------------------------------------

def _make_occ(ticker: str, expiry: str, opt_type: str, strike: float) -> str:
    """
    Build the OCC option symbol used by Alpaca.
    Format: {ticker:6}{YYMMDD}{C|P}{strike*1000:08d}
    Example: SPY     240315 C  00500000  →  SPY240315C00500000
    """
    exp_short = datetime.strptime(expiry, "%Y-%m-%d").strftime("%y%m%d")
    cp = "C" if opt_type == "call" else "P"
    strike_int = int(round(strike * 1000))
    return f"{ticker:<6}{exp_short}{cp}{strike_int:08d}".replace(" ", "")


def occ_symbol(opt: dict) -> str:
    """
    Return OCC symbol for an option dict.
    Prefers the contractSymbol field (yfinance already provides OCC format);
    falls back to constructing one from ticker/expiry/type/strike.
    """
    cs = opt.get("contractSymbol")
    if cs and re.match(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$", str(cs)):
        return str(cs)
    return _make_occ(opt["ticker"], opt["expiry"], opt["option_type"], opt["strike"])


def submit_buy(opt: dict, limit_price: float, qty: int = 1) -> dict:
    """Submit a limit buy order for `qty` options contracts."""
    from alpaca.trading.requests import LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    symbol = occ_symbol(opt)
    req = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        limit_price=round(limit_price, 2),
    )
    order = _trading_client().submit_order(req)
    return {
        "order_id": str(order.id),
        "status": str(order.status),
        "symbol": symbol,
        "qty": qty,
        "limit_price": limit_price,
    }


def submit_close(occ: str, limit_price: float, qty: int = 1) -> dict:
    """Submit a limit sell order to close `qty` contracts."""
    from alpaca.trading.requests import LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    req = LimitOrderRequest(
        symbol=occ,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        limit_price=round(limit_price, 2),
    )
    order = _trading_client().submit_order(req)
    return {"order_id": str(order.id), "status": str(order.status), "qty": qty}


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

def get_open_positions() -> list:
    """Return all open options positions from Alpaca paper account."""
    positions = _trading_client().get_all_positions()
    result = []
    for p in positions:
        asset_class = str(getattr(p, "asset_class", "")).lower()
        if "option" not in asset_class:
            continue
        result.append({
            "symbol": p.symbol,
            "qty": int(float(p.qty)),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price) if p.current_price else None,
            "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else None,
            "market_value": float(p.market_value) if p.market_value else None,
        })
    return result
