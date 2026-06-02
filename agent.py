"""
Core agent logic: scan signals, manage exits, open paper trades.

When ALPACA_API_KEY + ALPACA_API_SECRET are set, orders are submitted to
Alpaca's paper trading endpoint and positions are mirrored there.
Without credentials the agent runs in full local simulation mode.
"""
import os
from colorama import Fore, Style, init
import data_fetcher
import indicators
import signals
import options_scanner
import portfolio as port
import config

init(autoreset=True)

_USE_ALPACA = False  # resolved at first use


def _alpaca_enabled() -> bool:
    global _USE_ALPACA
    try:
        import alpaca_broker
        _USE_ALPACA = alpaca_broker.is_configured()
    except ImportError:
        _USE_ALPACA = False
    return _USE_ALPACA


def _color_signal(sig: str) -> str:
    colors = {"buy_call": Fore.GREEN, "buy_put": Fore.RED}
    label = {"buy_call": "BUY CALL", "buy_put": "BUY PUT"}.get(sig, "HOLD")
    return colors.get(sig, Fore.YELLOW) + label + Style.RESET_ALL


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def print_status(pf: dict):
    positions = port.open_positions(pf)
    closed = pf.get("closed_trades", [])

    print(f"\n{'='*62}")
    if _alpaca_enabled():
        try:
            import alpaca_broker
            acct = alpaca_broker.get_account()
            print(f"  ALPACA PAPER ACCOUNT  (status: {acct['status']})")
            print(f"{'='*62}")
            print(f"  Portfolio value : ${acct['portfolio_value']:.2f}")
            print(f"  Buying power    : ${acct['buying_power']:.2f}")
            print(f"  Cash            : ${acct['cash']:.2f}")

            alpaca_pos = alpaca_broker.get_open_positions()
            if alpaca_pos:
                print(f"\n  {'SYMBOL':<25}{'QTY':<5}{'ENTRY':<9}{'CURRENT':<10}{'UNRL P&L'}")
                print(f"  {'-'*62}")
                for p in alpaca_pos:
                    unrl = p.get("unrealized_pl")
                    unrl_str = f"${unrl:+.2f}" if unrl is not None else "n/a"
                    cur = p.get("current_price")
                    cur_str = f"${cur:.2f}" if cur is not None else "n/a"
                    print(f"  {p['symbol']:<25}{p['qty']:<5}${p['avg_entry_price']:<8.2f}{cur_str:<10}{unrl_str}")
            else:
                print(f"\n  No open options positions on Alpaca.")
        except Exception as e:
            print(f"  PAPER PORTFOLIO  (Alpaca error: {e})")
    else:
        print("  PAPER PORTFOLIO  (local simulation)")
    print(f"{'='*62}")

    # Always show local log (orders submitted + closed trades)
    if positions:
        print(f"\n  Local order log — {len(positions)} pending/open:")
        print(f"  {'ID':<10}{'TICKER':<7}{'TYPE':<6}{'STRIKE':<9}{'EXPIRY':<13}{'ENTRY $':<9}{'COST':<8}{'ORDER ID'}")
        print(f"  {'-'*62}")
        for p in positions:
            oid = (p.get("order_id") or "local")[:16]
            print(
                f"  {p['id']:<10}{p['ticker']:<7}{p['option_type'].upper():<6}"
                f"${p['strike']:<8.1f}{p['expiry']:<13}${p['entry_price']:<8.2f}"
                f"${p['cost']:<8.2f}{oid}"
            )

    if closed:
        total_pnl = sum(t.get("pnl", 0) for t in closed)
        wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
        pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
        print(f"\n  Closed trades : {len(closed)} ({wins} winners)")
        print(f"  Realized P&L  : {pnl_color}${total_pnl:+.2f}{Style.RESET_ALL}")

    print()


# ---------------------------------------------------------------------------
# Exit management
# ---------------------------------------------------------------------------

def check_exits():
    """Check open positions for stop-loss / take-profit and close if triggered."""
    pf = port.load()
    positions = port.open_positions(pf)
    if not positions:
        return

    print(f"{Fore.CYAN}Checking {len(positions)} position(s) for exits...{Style.RESET_ALL}")

    for pos in list(positions):
        try:
            opts = data_fetcher.get_options_chain(pos["ticker"])
        except Exception as e:
            print(f"  [{pos['id']}] Chain fetch error: {e}")
            continue

        match = next(
            (
                o for o in opts
                if o.get("option_type") == pos["option_type"]
                and o.get("expiry") == pos["expiry"]
                and abs(o.get("strike", 0) - pos["strike"]) < 0.01
            ),
            None,
        )

        if not match:
            print(f"  [{pos['id']}] Not found in current chain (expired or delisted).")
            continue

        mid = options_scanner._mid(match)
        if mid <= 0:
            continue

        change = (mid - pos["entry_price"]) / pos["entry_price"]
        chg_str = (Fore.GREEN if change >= 0 else Fore.RED) + f"{change*100:+.1f}%" + Style.RESET_ALL
        print(f"  [{pos['id']}] {pos['ticker']} {pos['option_type']} ${pos['strike']} "
              f"entry ${pos['entry_price']:.2f} → ${mid:.2f} ({chg_str})")

        reason = None
        if change <= -config.STOP_LOSS_PCT:
            reason = "stop_loss"
        elif change >= config.TAKE_PROFIT_PCT:
            reason = "take_profit"

        if reason:
            _close_position(pf, pos, mid, reason)

    print()


def _close_position(pf: dict, pos: dict, mid_price: float, reason: str):
    label = Fore.RED + "STOP LOSS" if reason == "stop_loss" else Fore.GREEN + "TAKE PROFIT"
    print(f"    {label}{Style.RESET_ALL}", end=" → ")

    if _alpaca_enabled() and pos.get("order_id") and pos.get("occ_symbol"):
        try:
            import alpaca_broker
            alpaca_broker.submit_close(pos["occ_symbol"], mid_price)
            print(f"close order submitted to Alpaca", end=" | ")
        except Exception as e:
            print(f"Alpaca close failed ({e}), logging locally", end=" | ")

    closed = port.close_trade(pf, pos["id"], mid_price, reason)
    pnl = closed.get("pnl", 0)
    print(f"P&L ${pnl:+.2f} ({closed.get('pnl_pct', 0):+.1f}%)")


# ---------------------------------------------------------------------------
# Signal scan + trade entry
# ---------------------------------------------------------------------------

def scan_and_trade():
    pf = port.load()
    using_alpaca = _alpaca_enabled()

    mode = "Alpaca paper" if using_alpaca else "local simulation"
    print(f"{Fore.CYAN}Scanning SPY/QQQ — {mode}{Style.RESET_ALL}")

    if using_alpaca:
        try:
            import alpaca_broker
            acct = alpaca_broker.get_account()
            cash = acct["cash"]
        except Exception:
            cash = pf["cash"]
    else:
        cash = pf["cash"]

    open_count = len(port.open_positions(pf))
    print(f"Cash: ${cash:.2f} | Open: {open_count}/{config.MAX_POSITIONS}\n")

    for ticker in config.TICKERS:
        print(f"{Fore.CYAN}[{ticker}]{Style.RESET_ALL}", end=" ")

        try:
            df = data_fetcher.get_price_history(ticker)
            df = indicators.calculate_indicators(df)
        except Exception as e:
            print(f"Data error: {e}")
            continue

        price = float(df["Close"].iloc[-1])
        rsi_val = df["rsi"].iloc[-1]
        sig = signals.generate_signal(df)

        print(f"${price:.2f} | RSI {rsi_val:.1f} | {_color_signal(sig['signal'])}")
        if sig["reasons"]:
            print(f"         {' | '.join(sig['reasons'])}")

        if sig["signal"] == "hold" or sig["strength"] < 2:
            print()
            continue

        if not port.can_open(pf):
            print(f"         {Fore.YELLOW}Skipped — max positions or insufficient cash{Style.RESET_ALL}\n")
            continue

        opt_type = "call" if sig["signal"] == "buy_call" else "put"
        print(f"         Scanning {opt_type}s (DTE {config.MIN_DTE}–{config.MAX_DTE}, "
              f"max ${config.MAX_CONTRACT_COST:.0f}/contract)...")

        try:
            opts = data_fetcher.get_options_chain(ticker)
        except Exception as e:
            print(f"         Options error: {e}\n")
            continue

        qualified = options_scanner.filter_options(opts, opt_type, price)
        print(f"         {len(qualified)} qualifying {opt_type}(s) found")

        best = options_scanner.select_best_option(qualified)
        if not best:
            print(f"         No suitable option found.\n")
            continue

        best["signal_reasons"] = sig["reasons"]
        _open_position(pf, best)

    print_status(pf)


def _open_position(pf: dict, opt: dict):
    """Submit order to Alpaca (if configured) and log locally."""
    order_id = None
    occ = None

    if _alpaca_enabled():
        try:
            import alpaca_broker
            occ = alpaca_broker.occ_symbol(opt)
            result = alpaca_broker.submit_buy(opt, opt["mid_price"])
            order_id = result["order_id"]
            status = result["status"]
            print(f"         {Fore.GREEN}ORDER SENT TO ALPACA{Style.RESET_ALL} "
                  f"OCC={occ} status={status}")
        except Exception as e:
            print(f"         {Fore.YELLOW}Alpaca order failed ({e}) — logging locally{Style.RESET_ALL}")

    opt["order_id"] = order_id
    opt["occ_symbol"] = occ
    pos = port.open_trade(pf, opt)

    print(
        f"         {Fore.GREEN if order_id else ''}LOGGED:{Style.RESET_ALL} "
        f"ID {pos['id']} | {pos['ticker']} ${pos['strike']} {pos['option_type'].upper()} "
        f"exp {pos['expiry']} | ${pos['entry_price']:.2f}/sh = ${pos['cost']:.2f} | "
        f"DTE {pos['dte_at_entry']}"
    )
    print()
