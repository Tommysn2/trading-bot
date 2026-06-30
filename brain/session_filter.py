"""
ICT Session Filter — controls WHEN the bot is allowed to trade.
Based on Inner Circle Trader session kill zones and timing rules.
All times in US Eastern Time.
"""

from datetime import datetime, time
import pytz
from config.settings import (
    NY_KILL_ZONE_START_ET, NY_KILL_ZONE_END_ET,
    LUNCH_AVOID_START_ET, LUNCH_AVOID_END_ET,
    LUNCH_SWEEP_WINDOW_ET, MARKET_OPEN_ET, MARKET_CLOSE_ET,
    FRIDAY_REVIEW_ET
)

ET = pytz.timezone("America/New_York")


def _et_now() -> datetime:
    return datetime.now(ET)


def _t(time_str: str) -> time:
    h, m = map(int, time_str.split(":"))
    return time(h, m)


def can_open_new_trade() -> tuple[bool, str]:
    """
    Returns (True, reason) if it's a valid time to open a new trade.
    Returns (False, reason) if we should wait.
    """
    now = _et_now()
    current_time = now.time()
    weekday = now.weekday()  # 0=Mon, 4=Fri

    # Weekend — no trading
    if weekday >= 5:
        return False, "Weekend — market closed."

    # Before market open
    if current_time < _t(MARKET_OPEN_ET):
        return False, f"Pre-market. Market opens at {MARKET_OPEN_ET} ET."

    # After market close
    if current_time >= _t(MARKET_CLOSE_ET):
        return False, f"Market closed at {MARKET_CLOSE_ET} ET."

    # Friday afternoon review window — no new trades, evaluate weekend hold
    if weekday == 4 and current_time >= _t(FRIDAY_REVIEW_ET):
        return False, "Friday 3:30 PM+ — weekend decision window, no new entries."

    # NY Lunch avoid window (ICT rule)
    if _t(LUNCH_AVOID_START_ET) <= current_time <= _t(LUNCH_AVOID_END_ET):
        return False, f"NY Lunch window ({LUNCH_AVOID_START_ET}–{LUNCH_AVOID_END_ET} ET) — no new entries."

    return True, "Market open. Valid trading window."


def is_kill_zone() -> tuple[bool, str]:
    """
    Returns (True, "NY Kill Zone") if we're in the primary high-probability entry window.
    7:00–10:00 AM ET is the NY Kill Zone (ICT).
    """
    now = _et_now()
    current_time = now.time()
    if _t(NY_KILL_ZONE_START_ET) <= current_time <= _t(NY_KILL_ZONE_END_ET):
        return True, f"NY Kill Zone ({NY_KILL_ZONE_START_ET}–{NY_KILL_ZONE_END_ET} ET) — highest probability entries."
    return False, "Outside Kill Zone — lower priority for new entries."


def is_lunch_sweep_window() -> bool:
    """
    True if we're in the 1:15–1:30 PM window where the algorithm often
    sweeps equal highs/lows before the lunch session closes (ICT concept).
    Watch for a liquidity sweep in this window — then fade it.
    """
    now = _et_now()
    return now.time() >= _t(LUNCH_SWEEP_WINDOW_ET) and now.time() < _t(LUNCH_AVOID_END_ET)


def is_friday_review_time() -> bool:
    """True if it's Friday 3:30 PM ET — time to decide whether to hold over weekend."""
    now = _et_now()
    return now.weekday() == 4 and now.time() >= _t(FRIDAY_REVIEW_ET)


def get_session_context() -> dict:
    """Returns a full snapshot of the current session state."""
    now = _et_now()
    can_trade, trade_reason = can_open_new_trade()
    in_kz, kz_reason = is_kill_zone()
    return {
        "time_et": now.strftime("%H:%M"),
        "day": now.strftime("%A"),
        "can_open_new_trade": can_trade,
        "trade_window_reason": trade_reason,
        "in_kill_zone": in_kz,
        "kill_zone_reason": kz_reason,
        "lunch_sweep_watch": is_lunch_sweep_window(),
        "friday_review": is_friday_review_time(),
    }
