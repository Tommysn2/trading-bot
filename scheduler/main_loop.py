"""
Main Loop — the bot's heartbeat.
Runs 24/7 on Railway. Handles two separate schedules:
  • Every 5 min  → position check (stops, circuit breaker)
  • Every 30 min → trade decision cycle (during market hours only)
  • Daily 4:30 PM ET  → nightly summary
  • Sunday 8:00 AM ET → weekly self-learning review

This file is what Railway runs: python scheduler/main_loop.py
"""

import time
import schedule
import logging
import traceback
import pytz
from datetime import datetime

from execution.portfolio_manager import PortfolioManager
from learning.weekly_review import run_nightly_review, run_weekly_review
from alerts.telegram_bot import alert_bot_started, alert_bot_stopped, alert_error
from config.settings import (
    POSITION_CHECK_MINS, TRADE_DECISION_MINS,
    DAILY_REVIEW_TIME_ET, LEARNING_REVIEW_TIME, T212_MODE
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

manager = PortfolioManager()


# ── Scheduled jobs ───────────────────────────────────────────

def job_position_check():
    """Every 5 minutes: check stops, circuit breaker, tighten if needed."""
    try:
        result = manager.run_position_check()
        cb = result.get("circuit_breaker", "normal")
        n = result.get("positions", 0)
        pnl = result.get("daily_pnl_pct", 0)

        log.info(f"[Position check] {n} positions | Day P&L: {pnl:+.1%} | CB: {cb}")

        if result.get("stop_actions"):
            log.warning(f"[Stops tightened] {result['stop_actions']}")

    except Exception as e:
        log.error(f"[Position check] Error: {e}\n{traceback.format_exc()}")
        alert_error(str(e), context="position_check")


def job_trade_decision():
    """Every 30 minutes: full signal gather → Claude decision → execute."""
    try:
        result = manager.run_trade_decision()
        result_type = result.get("type", "")

        if result.get("result") == "skipped":
            log.info(f"[Trade decision] Skipped — {result.get('reason')}")
            return

        if result_type == "friday_review":
            log.info(f"[Friday review] {result.get('action')} — {result.get('reason')}")
            return

        decision = result.get("decision", {})
        execution = result.get("execution", {})
        action = decision.get("action", "HOLD")
        ticker = decision.get("ticker")

        if execution.get("executed"):
            log.info(f"[Trade executed] {action} {ticker} — {execution.get('message')}")
        else:
            log.info(f"[Decision] {action} {ticker or ''} — {decision.get('reasoning', '')[:100]}")

    except Exception as e:
        log.error(f"[Trade decision] Error: {e}\n{traceback.format_exc()}")
        alert_error(str(e), context="trade_decision")


def job_nightly_summary():
    """4:30 PM ET daily: log the day and send Telegram summary."""
    try:
        summary = manager.run_nightly_summary()
        run_nightly_review(summary)
        log.info(f"[Nightly] Day P&L: {summary.get('daily_pnl_pct', 0):+.1%} | Equity: £{summary.get('equity', 0):,.0f}")
    except Exception as e:
        log.error(f"[Nightly summary] Error: {e}")
        alert_error(str(e), context="nightly_summary")


def job_weekly_review():
    """Sunday 8:00 AM ET: full self-learning cycle."""
    try:
        log.info("[Weekly review] Starting self-learning cycle...")
        result = run_weekly_review()
        log.info(f"[Weekly review] {result.get('status')} — {result.get('hypothesis', 'N/A')}")
    except Exception as e:
        log.error(f"[Weekly review] Error: {e}")
        alert_error(str(e), context="weekly_review")


# ── Schedule setup ───────────────────────────────────────────

def setup_schedule():
    # Position monitoring — every N minutes (default 5)
    schedule.every(POSITION_CHECK_MINS).minutes.do(job_position_check)

    # Trade decisions — every N minutes (default 30)
    schedule.every(TRADE_DECISION_MINS).minutes.do(job_trade_decision)

    # Nightly summary — 4:30 PM ET (schedule library uses local time, so we wrap)
    # We run the check every minute and fire based on ET time
    schedule.every(1).minutes.do(_check_timed_jobs)

    log.info(f"Schedule configured:")
    log.info(f"  Position check: every {POSITION_CHECK_MINS} min")
    log.info(f"  Trade decisions: every {TRADE_DECISION_MINS} min")
    log.info(f"  Nightly summary: {DAILY_REVIEW_TIME_ET} ET")
    log.info(f"  Weekly review: Sunday {LEARNING_REVIEW_TIME} ET")


# Track which timed jobs have fired today to prevent duplicates
_fired_today = set()


def _check_timed_jobs():
    """Fires time-specific jobs by checking ET clock each minute."""
    global _fired_today
    ET = pytz.timezone("America/New_York")
    now = datetime.now(ET)
    key_today = now.date().isoformat()
    time_str = now.strftime("%H:%M")

    # Reset fired set at midnight
    if key_today not in _fired_today:
        _fired_today = {key_today}

    # Nightly summary
    nightly_key = f"{key_today}_nightly"
    if time_str == DAILY_REVIEW_TIME_ET and nightly_key not in _fired_today:
        _fired_today.add(nightly_key)
        job_nightly_summary()

    # Weekly review (Sunday only)
    weekly_key = f"{key_today}_weekly"
    if now.weekday() == 6 and time_str == LEARNING_REVIEW_TIME and weekly_key not in _fired_today:
        _fired_today.add(weekly_key)
        job_weekly_review()


# ── Entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    mode = "DEMO" if T212_MODE == "demo" else "LIVE"
    log.info(f"=== Trading Bot Starting ({mode} mode) ===")

    try:
        alert_bot_started(mode=mode)
        setup_schedule()

        # Run an immediate position check and trade decision on startup
        job_position_check()
        time.sleep(10)  # avoid T212 rate limit on startup
        job_trade_decision()

        # Main loop
        while True:
            schedule.run_pending()
            time.sleep(30)  # check schedule every 30 seconds

    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
        alert_bot_stopped("Keyboard interrupt.")
    except Exception as e:
        log.critical(f"Fatal error: {e}\n{traceback.format_exc()}")
        alert_error(str(e), context="main_loop_fatal")
        raise
