"""
Email notifications for trade events via SMTP.
Silent no-op when EMAIL_USERNAME / EMAIL_PASSWORD aren't set,
so local/demo runs don't try to send.

Defaults to Gmail SMTP. Override with EMAIL_HOST / EMAIL_PORT for other providers.
"""
import os
import smtplib
from email.message import EmailMessage


def _enabled() -> bool:
    return bool(os.getenv("EMAIL_USERNAME") and os.getenv("EMAIL_PASSWORD"))


def _send(subject: str, body_html: str, body_text: str) -> None:
    user = os.getenv("EMAIL_USERNAME")
    password = os.getenv("EMAIL_PASSWORD")
    if not (user and password):
        return

    host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    port = int(os.getenv("EMAIL_PORT", "587"))
    to_addr = os.getenv("EMAIL_TO", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
    except Exception as e:
        print(f"  [notify] Email send failed: {e}")


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td style="padding:4px 12px 4px 0;color:#666;font-size:13px;">{label}</td>'
        f'<td style="padding:4px 0;font-weight:600;font-size:14px;">{value}</td></tr>'
    )


def trade_opened(pos: dict) -> None:
    if not _enabled():
        return

    direction = "CALL" if pos["option_type"] == "call" else "PUT"
    tier = pos.get("conviction_tier", "STANDARD")
    accent = "#9333ea" if tier == "HIGH_CONVICTION" else "#22c55e"
    reasons = pos.get("signal_reasons", [])

    subject = (
        f"[Trade Agent] BOUGHT {pos['contracts']}x {pos['ticker']} "
        f"${pos['strike']:.0f}{direction[0]} exp {pos['expiry']}"
    )

    rows = "".join([
        _row("Position", f"{pos['contracts']}x {pos['ticker']} ${pos['strike']:.0f} {direction}"),
        _row("Expiry", f"{pos['expiry']} ({pos['dte_at_entry']} DTE)"),
        _row("Entry price", f"${pos['entry_price']:.2f}/share"),
        _row("Total cost", f"${pos['cost']:.2f}"),
        _row("Conviction", tier),
        _row("Regime", pos.get("regime_at_entry", "?")),
    ])
    if reasons:
        rows += _row("Signal", " · ".join(reasons))

    body_html = f"""<html><body style="font-family:-apple-system,sans-serif;color:#111;">
<div style="border-left:4px solid {accent};padding:0 0 0 16px;margin:8px 0;">
<h2 style="margin:0 0 4px 0;color:{accent};">Trade Opened</h2>
<p style="margin:0 0 12px 0;color:#666;font-size:13px;">Position {pos['id']}</p>
<table style="border-collapse:collapse;">{rows}</table>
</div></body></html>"""

    body_text = "\n".join([
        f"BOUGHT {pos['contracts']}x {pos['ticker']} ${pos['strike']:.0f} {direction} exp {pos['expiry']}",
        f"  Entry:     ${pos['entry_price']:.2f}/sh   Total: ${pos['cost']:.2f}",
        f"  DTE:       {pos['dte_at_entry']}",
        f"  Tier:      {tier}",
        f"  Regime:    {pos.get('regime_at_entry', '?')}",
        f"  Signal:    {' · '.join(reasons)}" if reasons else "",
        f"  Position:  {pos['id']}",
    ])
    _send(subject, body_html, body_text)


def trade_closed(pos: dict) -> None:
    if not _enabled():
        return

    pnl = pos.get("pnl", 0)
    pnl_pct = pos.get("pnl_pct", 0)
    accent = "#22c55e" if pnl >= 0 else "#ef4444"
    reason = pos.get("exit_reason", "closed").replace("_", " ").upper()
    sign = "+" if pnl >= 0 else ""
    outcome = "PROFIT" if pnl >= 0 else "LOSS"

    subject = (
        f"[Trade Agent] CLOSED {pos['ticker']} ${pos['strike']:.0f}"
        f"{pos['option_type'][0].upper()} — {outcome} {sign}${pnl:.0f}"
    )

    rows = "".join([
        _row("Position", f"{pos['contracts']}x {pos['ticker']} ${pos['strike']:.0f} {pos['option_type'].upper()}"),
        _row("Exit reason", reason),
        _row("Exit price", f"${pos.get('exit_price', 0):.2f}/share"),
        _row("P&L", f"{sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%)"),
    ])

    body_html = f"""<html><body style="font-family:-apple-system,sans-serif;color:#111;">
<div style="border-left:4px solid {accent};padding:0 0 0 16px;margin:8px 0;">
<h2 style="margin:0 0 4px 0;color:{accent};">Trade Closed — {outcome}</h2>
<p style="margin:0 0 12px 0;color:#666;font-size:13px;">Position {pos['id']}</p>
<table style="border-collapse:collapse;">{rows}</table>
</div></body></html>"""

    body_text = "\n".join([
        f"CLOSED {pos['ticker']} ${pos['strike']:.0f} {pos['option_type'].upper()}",
        f"  Exit:    ${pos.get('exit_price', 0):.2f}/sh  ({reason})",
        f"  P&L:     {sign}${pnl:.2f} ({sign}{pnl_pct:.1f}%)",
        f"  Position: {pos['id']}",
    ])
    _send(subject, body_html, body_text)
