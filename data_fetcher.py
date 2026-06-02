"""
Fetches price history and options chains.
Falls back to synthetic mock data when Yahoo Finance is unreachable
(e.g., in sandboxed/offline environments).  Set TRADE_AGENT_DEMO=1
to force demo mode explicitly.
"""
import os
import pandas as pd
from datetime import datetime
import config

_DEMO = os.getenv("TRADE_AGENT_DEMO", "0") == "1"
_LIVE_FAILED: set = set()  # tickers that already failed live fetch


def _use_mock(ticker: str) -> bool:
    return _DEMO or ticker in _LIVE_FAILED


def get_price_history(ticker: str) -> pd.DataFrame:
    if not _use_mock(ticker):
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            df = t.history(period=config.DATA_PERIOD, interval=config.DATA_INTERVAL)
            if df.empty:
                raise ValueError("empty response")
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
        except Exception:
            _LIVE_FAILED.add(ticker)
            print(f"  [demo] Live data unavailable for {ticker}, using synthetic data.")

    import mock_data
    return mock_data.get_price_history(ticker)


def get_options_chain(ticker: str) -> list:
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
            return results
        except Exception:
            _LIVE_FAILED.add(ticker)

    import mock_data
    return mock_data.get_options_chain(ticker)
