"""
Forex Factory calendar scraper — identifies high-impact USD news events for the week.
Used for macro avoidance: hold cash on CPI, FOMC, NFP days.
Source: https://www.forexfactory.com/calendar
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import pytz
from config.settings import HIGH_IMPACT_EVENTS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_high_impact_days(week_start: date = None) -> dict:
    """
    Returns a dict mapping dates to list of high-impact events this week.
    Example: {date(2025, 3, 12): ["CPI", "Core CPI"], date(2025, 3, 20): ["FOMC"]}
    """
    if week_start is None:
        week_start = _this_monday()

    try:
        # Forex Factory's weekly calendar URL
        url = f"https://www.forexfactory.com/calendar?week={week_start.strftime('%b%d.%Y').lower()}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return _parse_calendar(resp.text, week_start)
    except Exception as e:
        print(f"[Forex Factory] Error: {e}")
        return {}


def is_no_trade_day(check_date: date = None) -> tuple[bool, list[str]]:
    """
    Returns (True, [event names]) if today is a high-impact macro event day.
    Returns (False, []) if it's safe to trade.
    """
    if check_date is None:
        check_date = date.today()

    high_impact = get_high_impact_days()
    events_today = high_impact.get(check_date, [])
    is_high_impact = len(events_today) > 0
    return is_high_impact, events_today


def get_week_flags() -> str:
    """
    Returns a human-readable summary of this week's no-trade days.
    Used in the Sunday prep routine.
    """
    high_impact = get_high_impact_days()
    if not high_impact:
        return "No high-impact macro events detected this week. Safe to trade all days."

    lines = ["⚠️ HIGH-IMPACT MACRO EVENTS THIS WEEK — hold cash on these days:"]
    for day, events in sorted(high_impact.items()):
        lines.append(f"  • {day.strftime('%A %d %b')}: {', '.join(events)}")
    return "\n".join(lines)


def _parse_calendar(html: str, week_start: date) -> dict:
    """Parse Forex Factory HTML and extract red-folder USD events."""
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    current_date = week_start

    rows = soup.select("tr.calendar__row")
    for row in rows:
        # Date cell may be empty (same day continues)
        date_cell = row.select_one("td.calendar__date")
        if date_cell and date_cell.get_text(strip=True):
            try:
                date_text = date_cell.get_text(strip=True)
                current_date = _parse_ff_date(date_text, week_start.year)
            except Exception:
                pass

        # Currency must be USD
        currency_cell = row.select_one("td.calendar__currency")
        if not currency_cell or "USD" not in currency_cell.get_text():
            continue

        # Impact must be high (red)
        impact_cell = row.select_one("td.calendar__impact span")
        if not impact_cell:
            continue
        impact_class = impact_cell.get("class", [])
        if not any("high" in c.lower() or "red" in c.lower() for c in impact_class):
            continue

        # Event name
        event_cell = row.select_one("td.calendar__event")
        if not event_cell:
            continue
        event_name = event_cell.get_text(strip=True)

        # Filter to our tracked events
        if any(keyword.lower() in event_name.lower() for keyword in HIGH_IMPACT_EVENTS):
            if current_date not in result:
                result[current_date] = []
            result[current_date].append(event_name)

    return result


def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def _parse_ff_date(text: str, year: int) -> date:
    """Parse Forex Factory date formats like 'Mon Mar 12'."""
    import re
    text = re.sub(r'\s+', ' ', text.strip())
    for fmt in ["%a %b %d", "%A %b %d", "%a %B %d"]:
        try:
            d = datetime.strptime(f"{text} {year}", f"{fmt} %Y")
            return d.date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {text}")
