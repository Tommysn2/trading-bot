"""
Self-Learning Loop -- the Hermes method.
Every Sunday 8 AM ET: analyse the last week of trades, find the worst pattern,
propose ONE rule change, test it for 2 weeks, then accept or revert.
Every day 4:30 PM ET: lightweight nightly summary.

Scientific method: change only ONE variable at a time.
"""

import json
import re
from datetime import date, timedelta
from anthropic import Anthropic
from config.settings import (
    CLAUDE_MODEL_FAST, CLAUDE_MODEL_ANALYST, ANTHROPIC_API_KEY,
    MIN_TRADES_FOR_REVIEW, HYPOTHESIS_TEST_WEEKS
)
from database.supabase_client import (
    get_recent_trades, get_trade_stats, log_learning_entry, log_daily_summary
)
from alerts.telegram_bot import alert_weekly_learning, alert_nightly_summary

client = Anthropic(api_key=ANTHROPIC_API_KEY)


def run_nightly_review(nightly_summary: dict):
    """
    Quick 4:30 PM review -- log the day, send Telegram summary.
    No rule changes here, just data collection.
    """
    log_daily_summary(nightly_summary)
    alert_nightly_summary(nightly_summary)
    return nightly_summary


def run_weekly_review() -> dict:
    """
    Full Sunday deep-review (Hermes loop):
    1. Fetch last ~2 weeks of trades from Supabase
    2. Score by category (regime, session time, news type, etc.)
    3. Find the worst performing pattern
    4. Ask Claude Sonnet to propose ONE rule change
    5. Log it and alert to Telegram
    6. Track for 2 weeks, then accept or revert
    """
    trades = get_recent_trades(limit=100)
    stats = get_trade_stats()

    if stats.get("total_trades", 0) < MIN_TRADES_FOR_REVIEW:
        return {
            "status": "skipped",
            "reason": "Only {} closed trades. Need {} minimum.".format(
                stats.get("total_trades", 0), MIN_TRADES_FOR_REVIEW
            )
        }

    # Ask Claude Sonnet to analyse the trades and propose a hypothesis
    analysis = _ask_claude_for_hypothesis(trades, stats)

    # Log the learning entry
    entry = {
        "week_start": (date.today() - timedelta(days=7)).isoformat(),
        "trades_analysed": stats["total_trades"],
        "worst_pattern": analysis.get("worst_pattern"),
        "hypothesis": analysis.get("hypothesis"),
        "outcome": "testing",
        "metric_before": stats.get("win_rate"),
        "metric_after": None,
    }
    log_learning_entry(entry)

    # Alert to Telegram
    alert_weekly_learning(
        hypothesis=analysis.get("hypothesis", "No clear pattern found"),
        outcome="testing",
        metric_before=stats.get("win_rate", 0),
    )

    return {
        "status": "complete",
        "stats": stats,
        "analysis": analysis,
        "hypothesis": analysis.get("hypothesis"),
        "testing_until": (date.today() + timedelta(weeks=HYPOTHESIS_TEST_WEEKS)).isoformat()
    }


def evaluate_hypothesis(current_stats: dict) -> dict:
    """
    Called after 2 weeks of testing a hypothesis.
    Compare metric_before vs metric_after -- accept or revert.
    """
    stats_now = get_trade_stats()
    win_rate_now = stats_now.get("win_rate", 0)
    win_rate_before = current_stats.get("win_rate_before", 0)

    # Accept if win rate improved by more than 2 percentage points
    improved = win_rate_now > win_rate_before + 0.02
    outcome = "accepted" if improved else "reverted"

    alert_weekly_learning(
        hypothesis=current_stats.get("hypothesis", "Unknown"),
        outcome=outcome,
        metric_before=win_rate_before,
        metric_after=win_rate_now,
    )

    return {
        "outcome": outcome,
        "win_rate_before": win_rate_before,
        "win_rate_after": win_rate_now
    }


def _ask_claude_for_hypothesis(trades: list, stats: dict) -> dict:
    """Ask Claude Sonnet to identify the worst pattern and propose ONE rule change."""
    prompt = (
        "You are reviewing a week of stock trades made by an autonomous trading bot.\n"
        "Your job: identify the WORST performing pattern and propose ONE specific rule change to fix it.\n\n"
        "== TRADE STATISTICS ==\n"
        "Total closed trades: {}\n"
        "Win rate: {:.0%}\n"
        "Total P&L: £{:+.2f}\n"
        "Avg win: £{:.2f}\n"
        "Avg loss: £{:.2f}\n"
        "Profit factor: {:.2f}\n\n"
        "Performance by regime:\n{}\n\n"
        "== RECENT TRADES (last 20) ==\n{}\n\n"
        "== YOUR TASK ==\n"
        "1. Identify the single worst performing pattern\n"
        "2. Propose ONE specific, testable rule change\n"
        "3. Output as JSON only.\n\n"
        "Output format:\n"
        '{{\n'
        '  "worst_pattern": "<description>",\n'
        '  "pattern_win_rate": 0.0,\n'
        '  "hypothesis": "<specific rule to add or change>",\n'
        '  "expected_improvement": "<why this should help>",\n'
        '  "change_one_thing": true\n'
        '}}'
    ).format(
        stats.get("total_trades", 0),
        stats.get("win_rate", 0),
        stats.get("total_pnl", 0),
        stats.get("avg_win", 0),
        stats.get("avg_loss", 0),
        stats.get("profit_factor", 0),
        json.dumps(stats.get("by_regime", {}), indent=2),
        json.dumps(trades[:20], indent=2, default=str)
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL_ANALYST,  # Sonnet for deeper pattern analysis
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print("[Learning] Claude analysis failed: {}".format(e))

    return {
        "worst_pattern": "Unknown -- analysis failed",
        "hypothesis": "Manual review required",
        "expected_improvement": "N/A",
    }
