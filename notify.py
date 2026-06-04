"""
Discord webhook notifications for trade events.
Silent no-op when DISCORD_WEBHOOK_URL is unset, so local/demo runs don't ping.
"""
import json
import os
import urllib.request


def _enabled() -> bool:
    return bool(os.getenv("DISCORD_WEBHOOK_URL"))


def _post(payload: dict) -> None:
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print(f"  [notify] Discord post failed: {e}")


def trade_opened(pos: dict) -> None:
    if not _enabled():
        return

    tier = pos.get("conviction_tier", "STANDARD")
    color = 0x9333EA if tier == "HIGH_CONVICTION" else 0x22C55E  # purple / green
    direction = "CALL" if pos["option_type"] == "call" else "PUT"
    reasons = pos.get("signal_reasons", [])

    fields = [
        {"name": "Contracts", "value": f"{pos['contracts']}x", "inline": True},
        {"name": "Entry", "value": f"${pos['entry_price']:.2f}/sh", "inline": True},
        {"name": "Cost", "value": f"${pos['cost']:.2f}", "inline": True},
        {"name": "DTE", "value": str(pos["dte_at_entry"]), "inline": True},
        {"name": "Tier", "value": tier, "inline": True},
        {"name": "Regime", "value": pos.get("regime_at_entry", "?"), "inline": True},
    ]
    if reasons:
        fields.append({"name": "Signal", "value": " · ".join(reasons), "inline": False})

    _post({
        "username": "Trade Agent",
        "embeds": [{
            "title": f"BOUGHT {pos['ticker']} ${pos['strike']:.0f} {direction} {pos['expiry']}",
            "color": color,
            "fields": fields,
            "footer": {"text": f"Position {pos['id']}"},
        }],
    })


def trade_closed(pos: dict) -> None:
    if not _enabled():
        return

    pnl = pos.get("pnl", 0)
    pnl_pct = pos.get("pnl_pct", 0)
    color = 0x22C55E if pnl >= 0 else 0xEF4444   # green / red
    reason = pos.get("exit_reason", "closed").replace("_", " ").upper()
    sign = "+" if pnl >= 0 else ""

    fields = [
        {"name": "Exit reason", "value": reason, "inline": True},
        {"name": "Exit", "value": f"${pos.get('exit_price', 0):.2f}/sh", "inline": True},
        {"name": "P&L", "value": f"{sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%)", "inline": True},
        {"name": "Held", "value": f"{pos['contracts']} contract(s)", "inline": True},
    ]

    _post({
        "username": "Trade Agent",
        "embeds": [{
            "title": f"CLOSED {pos['ticker']} ${pos['strike']:.0f} {pos['option_type'].upper()}",
            "color": color,
            "fields": fields,
            "footer": {"text": f"Position {pos['id']}"},
        }],
    })
