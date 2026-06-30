"""
Telegram alerts — sends instant messages to your phone for key bot events.
Free service. Requires: BotFather token + your chat ID.
Setup: See SETUP.md for how to get these.
"""

import requests
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def _send(text: str) -> bool:
    """Send a text message to your Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram] Not configured. Message: {text}")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram] Send failed: {e}")
        return False


# ── Specific alert types ─────────────────────────────────────

def alert_trade_opened(ticker: str, action: str, notional: float, reasoning: str, regime: str):
    msg = (
        f"🟢 <b>TRADE OPENED</b>\n"
        f"Action: <b>{action} {ticker}</b>\n"
        f"Size: £{notional:.0f}\n"
        f"Regime: {regime}\n"
        f"Reason: {reasoning}"
    )
    _send(msg)


def alert_trade_closed(ticker: str, pnl: float, pnl_pct: float, reason: str = ""):
    emoji = "✅" if pnl >= 0 else "🔴"
    msg = (
        f"{emoji} <b>TRADE CLOSED</b>\n"
        f"Ticker: <b>{ticker}</b>\n"
        f"P&L: £{pnl:+.2f} ({pnl_pct:+.1%})\n"
        f"Reason: {reason or 'Trailing stop hit'}"
    )
    _send(msg)


def alert_circuit_breaker(level: str, daily_pnl_pct: float):
    emoji = "⛔" if level == "halt" else "⚠️"
    label = "HALT" if level == "halt" else "DEFENSIVE MODE"
    msg = (
        f"{emoji} <b>CIRCUIT BREAKER — {label}</b>\n"
        f"Daily P&L: {daily_pnl_pct:+.1%}\n"
        f"{'No new trades for rest of day.' if level == 'halt' else 'No new trades. Stops tightened to 5%.'}"
    )
    _send(msg)


def alert_nightly_summary(summary: dict):
    pnl = summary.get("daily_pnl", 0)
    pnl_pct = summary.get("daily_pnl_pct", 0)
    equity = summary.get("equity", 0)
    positions = summary.get("open_positions", 0)
    regime = summary.get("regime", "unknown")
    emoji = "📈" if pnl >= 0 else "📉"
    msg = (
        f"{emoji} <b>DAILY SUMMARY</b> — {summary.get('date', 'today')}\n"
        f"Portfolio: £{equity:,.0f} ({pnl_pct:+.1%})\n"
        f"Day P&L: £{pnl:+.2f}\n"
        f"Open positions: {positions}\n"
        f"Regime: {regime}"
    )
    _send(msg)


def alert_weekly_learning(hypothesis: str, outcome: str, metric_before: float, metric_after: float = None):
    msg = (
        f"🧠 <b>WEEKLY SELF-LEARNING</b>\n"
        f"Worst pattern found and rule proposed:\n"
        f"<i>{hypothesis}</i>\n"
        f"Win rate before: {metric_before:.0%}\n"
    )
    if metric_after is not None:
        delta = metric_after - metric_before
        msg += f"Win rate after: {metric_after:.0%} ({delta:+.0%})\n"
        msg += f"Decision: <b>{outcome.upper()}</b>"
    else:
        msg += f"Status: <b>TESTING (2 weeks)</b>"
    _send(msg)


def alert_error(error: str, context: str = ""):
    msg = (
        f"🚨 <b>BOT ERROR</b>\n"
        f"Context: {context}\n"
        f"Error: {error[:500]}"
    )
    _send(msg)


def alert_bot_started(mode: str = "paper"):
    _send(f"🤖 <b>Bot started</b> — running in {mode.upper()} mode. Watching the market.")


def alert_bot_stopped(reason: str = ""):
    _send(f"🛑 <b>Bot stopped.</b> {reason}")
