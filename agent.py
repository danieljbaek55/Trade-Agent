"""
Core agent logic: scan signals, manage exits, open new paper trades.
"""
from colorama import Fore, Style, init
import data_fetcher
import indicators
import signals
import options_scanner
import portfolio as port
import config

init(autoreset=True)


def _color_signal(sig: str) -> str:
    colors = {"buy_call": Fore.GREEN, "buy_put": Fore.RED}
    label = {"buy_call": "BUY CALL", "buy_put": "BUY PUT"}.get(sig, "HOLD")
    return colors.get(sig, Fore.YELLOW) + label + Style.RESET_ALL


def print_status(pf: dict):
    positions = port.open_positions(pf)
    closed = pf.get("closed_trades", [])

    print(f"\n{'='*60}")
    print("  PAPER PORTFOLIO")
    print(f"{'='*60}")
    print(f"  Cash available : ${pf['cash']:.2f}")
    print(f"  Open positions : {len(positions)} / {config.MAX_POSITIONS}")

    if positions:
        print(f"\n  {'ID':<10}{'TICKER':<7}{'TYPE':<6}{'STRIKE':<9}{'EXPIRY':<13}{'ENTRY $':<9}{'COST'}")
        print(f"  {'-'*60}")
        for p in positions:
            print(
                f"  {p['id']:<10}{p['ticker']:<7}{p['option_type'].upper():<6}"
                f"${p['strike']:<8.1f}{p['expiry']:<13}${p['entry_price']:<8.2f}${p['cost']:.2f}"
            )

    if closed:
        total_pnl = sum(t.get("pnl", 0) for t in closed)
        wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
        pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
        print(f"\n  Closed trades  : {len(closed)} ({wins} winners)")
        print(f"  Realized P&L   : {pnl_color}${total_pnl:+.2f}{Style.RESET_ALL}")

    print()


def check_exits():
    """Look up current option prices and apply stop-loss / take-profit rules."""
    pf = port.load()
    positions = port.open_positions(pf)
    if not positions:
        return

    print(f"{Fore.CYAN}Checking {len(positions)} open position(s) for exit signals...{Style.RESET_ALL}")

    for pos in list(positions):
        try:
            opts = data_fetcher.get_options_chain(pos["ticker"])
        except Exception as e:
            print(f"  [{pos['id']}] Error fetching chain: {e}")
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
            print(f"  [{pos['id']}] Option no longer in chain (may be expired or delisted).")
            continue

        mid = options_scanner._mid(match)
        if mid <= 0:
            continue

        change = (mid - pos["entry_price"]) / pos["entry_price"]
        direction = Fore.GREEN + f"+{change*100:.1f}%" if change >= 0 else Fore.RED + f"{change*100:.1f}%"
        print(f"  [{pos['id']}] {pos['ticker']} {pos['option_type']} ${pos['strike']} "
              f"entry ${pos['entry_price']:.2f} → current ${mid:.2f} {direction}{Style.RESET_ALL}")

        if change <= -config.STOP_LOSS_PCT:
            closed = port.close_trade(pf, pos["id"], mid, "stop_loss")
            print(f"    {Fore.RED}STOP LOSS triggered{Style.RESET_ALL} | P&L: ${closed.get('pnl', 0):+.2f}")

        elif change >= config.TAKE_PROFIT_PCT:
            closed = port.close_trade(pf, pos["id"], mid, "take_profit")
            print(f"    {Fore.GREEN}TAKE PROFIT triggered{Style.RESET_ALL} | P&L: ${closed.get('pnl', 0):+.2f}")

    print()


def scan_and_trade():
    """Generate signals and open paper trades when conditions are met."""
    pf = port.load()

    print(f"{Fore.CYAN}Scanning SPY/QQQ for options opportunities...{Style.RESET_ALL}")
    print(f"Cash: ${pf['cash']:.2f} | Open: {len(port.open_positions(pf))}/{config.MAX_POSITIONS}\n")

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

        print(f"Price ${price:.2f} | RSI {rsi_val:.1f} | Signal: {_color_signal(sig['signal'])}")
        if sig["reasons"]:
            print(f"         Reasons: {', '.join(sig['reasons'])}")

        if sig["signal"] == "hold" or sig["strength"] < 2:
            print()
            continue

        if not port.can_open(pf):
            print(f"         {Fore.YELLOW}Skipped: max positions or insufficient cash{Style.RESET_ALL}\n")
            continue

        opt_type = "call" if sig["signal"] == "buy_call" else "put"
        print(f"         Scanning {opt_type} options (DTE {config.MIN_DTE}–{config.MAX_DTE}, "
              f"max ${config.MAX_CONTRACT_COST}/contract)...")

        try:
            opts = data_fetcher.get_options_chain(ticker)
        except Exception as e:
            print(f"         Options fetch error: {e}\n")
            continue

        qualified = options_scanner.filter_options(opts, opt_type, price)
        print(f"         {len(qualified)} qualifying {opt_type}(s) found")

        best = options_scanner.select_best_option(qualified)
        if not best:
            print(f"         No suitable option found.\n")
            continue

        best["signal_reasons"] = sig["reasons"]
        pos = port.open_trade(pf, best)

        print(
            f"         {Fore.GREEN}OPENED:{Style.RESET_ALL} ID {pos['id']} | "
            f"{pos['ticker']} ${pos['strike']} {pos['option_type'].upper()} "
            f"exp {pos['expiry']} | "
            f"${pos['entry_price']:.2f}/sh × 100 = ${pos['cost']:.2f} | "
            f"DTE {pos['dte_at_entry']}"
        )
        print()

    print_status(pf)
