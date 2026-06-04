"""
Market data layer with three-tier fallback:
  1. Alpaca stock bars API  (when ALPACA_API_KEY is set)
  2. yfinance              (when available and network allows)
  3. Synthetic mock data   (always available; forced by TRADE_AGENT_DEMO=1)
Options chain data always uses yfinance → mock fallback
(Alpaca options data requires a paid subscription).
"""
import os
import pandas as pd
from datetime import datetime
import config

_DEMO = os.getenv("TRADE_AGENT_DEMO", "0") == "1"
_LIVE_FAILED: set = set()


def _use_mock(ticker: str) -> bool:
    return _DEMO or ticker in _LIVE_FAILED


def get_price_history(ticker: str) -> pd.DataFrame:
    if not _use_mock(ticker):
        # --- Tier 1: Alpaca ---
        try:
            import alpaca_broker
            if alpaca_broker.is_configured():
                df = alpaca_broker.get_stock_bars(ticker, days=180)
                if not df.empty:
                    return df
        except Exception:
            pass

        # --- Tier 2: yfinance ---
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            df = t.history(period=config.DATA_PERIOD, interval=config.DATA_INTERVAL)
            if not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df
        except Exception:
            pass

        _LIVE_FAILED.add(ticker)
        print(f"  [demo] Live data unavailable for {ticker}, using synthetic data.")

    import mock_data
    return mock_data.get_price_history(ticker)


def get_options_chain(ticker: str) -> list:
    """
    Returns a flat list of option dicts with ticker/option_type/expiry/dte fields.
    yfinance option dicts include contractSymbol (OCC format) used by Alpaca orders.
    """
    if not _use_mock(ticker):
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            today = datetime.now().date()
            results = []

            for exp_str in t.options:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                dte = (exp_date - today).days
                if dte < config.MIN_DTE or dte > config.MAX_DTE:
                    continue
                chain = t.option_chain(exp_str)
                for opt_type, df in [("call", chain.calls), ("put", chain.puts)]:
                    df = df.copy()
                    df["ticker"] = ticker
                    df["option_type"] = opt_type
                    df["expiry"] = exp_str
                    df["dte"] = dte
                    results.extend(df.to_dict("records"))

            if results:
                return results
        except Exception:
            pass

        if ticker not in _LIVE_FAILED:
            _LIVE_FAILED.add(ticker)

    import mock_data
    return mock_data.get_options_chain(ticker)
