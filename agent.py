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
import greeks
import market_regime
import postmortem

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
        print(f"\n  Local order log — {len(positions)} open position(s):")
        print(f"  {'ID':<10}{'TICKER':<6}{'TYPE':<6}{'STRIKE':<8}{'EXPIRY':<12}{'QTY':<5}{'ENTRY':<8}{'COST':<9}{'TIER'}")
        print(f"  {'-'*70}")
        for p in positions:
            tier = (p.get("conviction_tier") or "")[:14]
            print(
                f"  {p['id']:<10}{p['ticker']:<6}{p['option_type'].upper():<6}"
                f"${p['strike']:<7.1f}{p['expiry']:<12}"
                f"{p.get('contracts', 1):<5}${p['entry_price']:<7.2f}${p['cost']:<8.2f}{tier}"
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
    contracts = int(pos.get("contracts", 1))
    print(f"    {label}{Style.RESET_ALL}", end=" → ")

    if _alpaca_enabled() and pos.get("order_id") and pos.get("occ_symbol"):
        try:
            import alpaca_broker
            alpaca_broker.submit_close(pos["occ_symbol"], mid_price, qty=contracts)
            print(f"close order ({contracts}x) sent to Alpaca", end=" | ")
        except Exception as e:
            print(f"Alpaca close failed ({e}), logging locally", end=" | ")

    closed = port.close_trade(pf, pos["id"], mid_price, reason)
    pnl = closed.get("pnl", 0)
    print(f"P&L ${pnl:+.2f} ({closed.get('pnl_pct', 0):+.1f}%)")


# ---------------------------------------------------------------------------
# Signal scan + trade entry
# ---------------------------------------------------------------------------

def _size_position(tier: str, available_cash: float, cost_per_contract: float) -> int:
    """
    Return number of contracts to buy based on conviction tier.
    Respects target deployment, available cash, and a 1-contract minimum.
    """
    if tier == "HIGH_CONVICTION":
        target = config.ACCOUNT_SIZE * config.HIGH_CONVICTION_DEPLOY_PCT
    elif tier == "STANDARD":
        target = config.ACCOUNT_SIZE * config.STANDARD_DEPLOY_PCT
    else:
        return 0

    if cost_per_contract <= 0 or available_cash < cost_per_contract:
        return 0

    n = max(1, int(target // cost_per_contract))
    # Don't exceed cash
    while n * cost_per_contract > available_cash and n > 0:
        n -= 1
    return n


def scan_and_trade():
    pf = port.load()
    using_alpaca = _alpaca_enabled()

    mode = "Alpaca paper" if using_alpaca else "local simulation"
    tickers_str = "/".join(config.TICKERS)
    print(f"{Fore.CYAN}Scanning {tickers_str} — {mode}{Style.RESET_ALL}")
    print(f"Pretend account size: ${config.ACCOUNT_SIZE:.0f} | "
          f"Min strength: {config.MIN_SIGNAL_STRENGTH} | "
          f"High conviction at: {config.HIGH_CONVICTION_THRESHOLD}")

    if using_alpaca:
        try:
            import alpaca_broker
            acct = alpaca_broker.get_account()
            real_cash = acct["cash"]
            print(f"Alpaca paper cash: ${real_cash:.2f} (real) | "
                  f"Local pretend cash: ${pf['cash']:.2f}")
        except Exception:
            pass

    open_count = len(port.open_positions(pf))
    print(f"Pretend cash: ${pf['cash']:.2f} | Open: {open_count}/{config.MAX_POSITIONS}\n")

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
        regime = market_regime.detect_regime(df)
        sig = signals.generate_signal(df, regime=regime)

        tier_color = (
            Fore.MAGENTA if sig["tier"] == "HIGH_CONVICTION"
            else Fore.GREEN if sig["tier"] == "STANDARD"
            else Fore.YELLOW
        )
        print(
            f"${price:.2f} | RSI {rsi_val:.1f} | regime {regime['regime']} | "
            f"{_color_signal(sig['signal'])} | strength {sig['strength']:.1f} | "
            f"{tier_color}{sig['tier']}{Style.RESET_ALL}"
        )
        if sig["reasons"]:
            print(f"         {' | '.join(sig['reasons'])}")

        if sig["tier"] == "NONE":
            print()
            continue

        # Regime filter — block trades against the prevailing trend
        if config.USE_REGIME_FILTER:
            if sig["signal"] == "buy_call" and not regime["allow_calls"]:
                print(f"         {Fore.YELLOW}Skipped — calls blocked in {regime['regime']} regime{Style.RESET_ALL}\n")
                continue
            if sig["signal"] == "buy_put" and not regime["allow_puts"]:
                print(f"         {Fore.YELLOW}Skipped — puts blocked in {regime['regime']} regime{Style.RESET_ALL}\n")
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

        contracts = _size_position(sig["tier"], pf["cash"], best["total_cost"])
        if contracts <= 0:
            print(f"         {Fore.YELLOW}Insufficient pretend cash for even 1 contract{Style.RESET_ALL}\n")
            continue

        best["contracts"] = contracts
        best["signal_reasons"] = sig["reasons"]
        best["signal_strength"] = sig["strength"]
        best["conviction_tier"] = sig["tier"]
        best["regime_at_entry"] = regime["regime"]
        best["greeks"] = greeks.estimate_greeks_for_option(best, price)
        _open_position(pf, best)

    print_status(pf)


def _open_position(pf: dict, opt: dict):
    """Submit order to Alpaca (if configured) and log locally."""
    order_id = None
    occ = None
    contracts = int(opt.get("contracts", 1))

    if _alpaca_enabled():
        try:
            import alpaca_broker
            occ = alpaca_broker.occ_symbol(opt)
            result = alpaca_broker.submit_buy(opt, opt["mid_price"], qty=contracts)
            order_id = result["order_id"]
            status = result["status"]
            print(f"         {Fore.GREEN}ORDER SENT TO ALPACA{Style.RESET_ALL} "
                  f"OCC={occ} qty={contracts} status={status}")
        except Exception as e:
            print(f"         {Fore.YELLOW}Alpaca order failed ({e}) — logging locally{Style.RESET_ALL}")

    opt["order_id"] = order_id
    opt["occ_symbol"] = occ
    pos = port.open_trade(pf, opt)

    tier_color = Fore.MAGENTA if pos.get("conviction_tier") == "HIGH_CONVICTION" else Fore.GREEN
    print(
        f"         {tier_color}{pos.get('conviction_tier','')}{Style.RESET_ALL} | "
        f"ID {pos['id']} | {pos['ticker']} ${pos['strike']} {pos['option_type'].upper()} "
        f"exp {pos['expiry']} | DTE {pos['dte_at_entry']}"
    )
    print(
        f"         {pos['contracts']} contract(s) × ${pos['entry_price']:.2f}/sh = "
        f"${pos['cost']:.2f} total"
    )
    g = pos.get("greeks_at_entry") or {}
    if g:
        # Per-position dollar Greeks (delta*100*contracts → $/share-move; theta*100*contracts → $/day)
        per = pos["contracts"]
        print(
            f"         Greeks (position): Δ ≈${g['delta']*100*per:+.0f}/$1 move | "
            f"Θ ${g['theta']*100*per:+.2f}/day | "
            f"ν ${g['vega']*per:.2f}/1%IV"
        )
    risk_pct = pos["cost"] / config.ACCOUNT_SIZE * 100
    print(
        f"         Risk: ${pos['cost']:.0f} = {risk_pct:.1f}% of ${config.ACCOUNT_SIZE:.0f} account"
    )
    print()
