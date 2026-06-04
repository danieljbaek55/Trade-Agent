#!/usr/bin/env python3
"""
Options Trading Agent — Paper Simulation
Account: $800 | Max $100/contract | SPY & QQQ | 30–180 DTE

Usage:
  python main.py run        # check exits + scan for new trades  (default)
  python main.py scan       # scan for new trades only
  python main.py exits      # check existing positions for stop-loss / take-profit
  python main.py status     # portfolio snapshot
  python main.py history    # closed trade log
  python main.py analytics  # postmortem stats: win rate, expectancy, by signal type
  python main.py reset      # wipe portfolio and start fresh
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
import postmortem
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


def cmd_analytics():
    pf = port.load()
    closed = pf.get("closed_trades", [])
    stats = postmortem.analyze(closed)

    if stats.get("count", 0) == 0:
        print("No closed trades yet — analytics will populate once positions exit.")
        return

    print(f"\n{'='*60}")
    print(f"  POSTMORTEM ANALYTICS  ({stats['count']} closed trades)")
    print(f"{'='*60}")
    print(f"  Win rate         : {stats['win_rate_pct']}%  ({stats['wins']}W / {stats['losses']}L)")
    print(f"  Total P&L        : ${stats['total_pnl']:+.2f}")
    print(f"  ROI on basis     : {stats['roi_pct']:+.1f}%")
    print(f"  Avg win          : ${stats['avg_win']:+.2f}")
    print(f"  Avg loss         : ${stats['avg_loss']:+.2f}")
    print(f"  Expectancy/trade : ${stats['expectancy_per_trade']:+.2f}")

    print(f"\n  Outcome breakdown:")
    for outcome, n in sorted(stats["by_outcome"].items(), key=lambda x: -x[1]):
        print(f"    {outcome:<22} {n}")

    print(f"\n  By signal type:")
    for sig_type, b in stats["by_signal_type"].items():
        print(
            f"    {sig_type.upper():<6} {b['trades']:3} trades | "
            f"{b['win_rate_pct']:5.1f}% win | ${b['total_pnl']:+.2f}"
        )
    print()


def cmd_reset():
    if os.path.exists(config.PORTFOLIO_FILE):
        os.remove(config.PORTFOLIO_FILE)
        print(f"Portfolio reset. Starting fresh with ${config.ACCOUNT_SIZE:.2f}.")
    else:
        print("No portfolio file found — already clean.")


def cmd_run():
    """Default run: exits + scan, but skip silently if market is closed."""
    if not agent.market_is_open():
        print("Market closed — skipping run.")
        return
    agent.check_exits()
    agent.scan_and_trade()


COMMANDS = {
    "run": cmd_run,
    "scan": agent.scan_and_trade,
    "exits": agent.check_exits,
    "status": lambda: agent.print_status(port.load()),
    "history": cmd_history,
    "analytics": cmd_analytics,
    "reset": cmd_reset,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    result = COMMANDS[cmd]()
