#!/usr/bin/env python3
"""
Options Trading Agent — Paper Simulation
Account: $800 | Max $100/contract | SPY & QQQ | 30–180 DTE

Usage:
  python main.py run      # check exits + scan for new trades  (default)
  python main.py scan     # scan for new trades only
  python main.py exits    # check existing positions for stop-loss / take-profit
  python main.py status   # portfolio snapshot
  python main.py history  # closed trade log
  python main.py reset    # wipe portfolio and start fresh
"""
import sys
import os

# Load .env before importing anything that reads env vars
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import agent
import portfolio as port
import config


def cmd_history():
    pf = port.load()
    closed = pf.get("closed_trades", [])
    if not closed:
        print("No closed trades yet.")
        return

    print(f"\n{'='*75}")
    print(f"  TRADE HISTORY  ({len(closed)} trades)")
    print(f"{'='*75}")
    hdr = f"  {'ID':<10}{'TICKER':<7}{'TYPE':<6}{'STRIKE':<9}{'EXPIRY':<13}{'ENTRY':<8}{'EXIT':<8}{'P&L':<11}{'%'}"
    print(hdr)
    print(f"  {'-'*75}")

    for t in closed:
        pnl = t.get("pnl", 0)
        sign = "+" if pnl >= 0 else ""
        print(
            f"  {t['id']:<10}{t['ticker']:<7}{t['option_type'].upper():<6}"
            f"${t['strike']:<8.1f}{t['expiry']:<13}"
            f"${t.get('entry_price', 0):<7.2f}${t.get('exit_price', 0):<7.2f}"
            f"${sign}{pnl:<10.2f}{sign}{t.get('pnl_pct', 0):.1f}%"
        )

    total = sum(t.get("pnl", 0) for t in closed)
    wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
    win_rate = wins / len(closed) * 100 if closed else 0
    print(f"\n  Win rate : {win_rate:.0f}%  ({wins}/{len(closed)})")
    print(f"  Total P&L: ${total:+.2f}\n")


def cmd_reset():
    if os.path.exists(config.PORTFOLIO_FILE):
        os.remove(config.PORTFOLIO_FILE)
        print(f"Portfolio reset. Starting fresh with ${config.ACCOUNT_SIZE:.2f}.")
    else:
        print("No portfolio file found — already clean.")


COMMANDS = {
    "run": lambda: (agent.check_exits(), agent.scan_and_trade()),
    "scan": agent.scan_and_trade,
    "exits": agent.check_exits,
    "status": lambda: agent.print_status(port.load()),
    "history": cmd_history,
    "reset": cmd_reset,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    result = COMMANDS[cmd]()
