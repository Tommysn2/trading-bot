"""
Insider Trades monitor -- scrapes OpenInsider for SEC Form 4 filings.
Focuses on clustered C-suite buys (CEO, CFO, COO, Chairman).

Logic: if multiple insiders at the SAME company buy on the same day, that's
a high-conviction signal. We only care about PURCHASES (not option exercises or sales).

Source: https://openinsider.com -- free, no login, no API key.
"""

import requests
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime, timedelta
import logging

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Only copy these roles -- not every employee option grant
EXECUTIVE_ROLES = {
    "CEO", "CFO", "COO", "President", "Chairman",
    "Chief Executive", "Chief Financial", "Chief Operating",
}

# Minimum $ value for an insider buy to count as meaningful
MIN_INSIDER_BUY = 25_000   # $25k+ = skin in the game

# FIX: HTTPS not HTTP
OPENINSIDER_URL = (
    "https://openinsider.com/screener?"
    "s=&o=&pl=&ph=&ll=&lh=&fd=7&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&"
    "xp=1&xs=1&vl=25&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&"
    "nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=100&page=1"
)


def fetch_insider_buys(days_back: int = 7) -> list[dict]:
    """
    Scrape OpenInsider for recent executive stock purchases.
    Returns list of individual trades (not yet clustered).
    """
    try:
        resp = requests.get(OPENINSIDER_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log.warning(f"[Insider] OpenInsider fetch failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", {"class": "tinytable"})
    if not table:
        log.warning("[Insider] Could not find trades table on OpenInsider")
        return []

    trades = []
    cutoff = datetime.now() - timedelta(days=days_back)

    rows = table.find_all("tr")[1:]   # skip header
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 13:
            continue
        try:
            filing_date_str = cells[1].get_text(strip=True)
            trade_date_str  = cells[2].get_text(strip=True)
            ticker          = cells[3].get_text(strip=True).upper()
            company         = cells[4].get_text(strip=True)
            insider_name    = cells[5].get_text(strip=True)
            title           = cells[6].get_text(strip=True)
            trade_type      = cells[7].get_text(strip=True)   # "P - Purchase"
            price_str       = cells[8].get_text(strip=True).replace("$", "").replace(",", "")
            qty_str         = cells[9].get_text(strip=True).replace(",", "").replace("+", "")
            value_str       = cells[11].get_text(strip=True).replace("$", "").replace(",", "").replace("+", "")

            # Only purchases (not option exercises or sales)
            if "P - Purchase" not in trade_type:
                continue

            # Only executive roles
            role_match = any(r.lower() in title.lower() for r in EXECUTIVE_ROLES)
            if not role_match:
                continue

            value = float(value_str) if value_str else 0
            if value < MIN_INSIDER_BUY:
                continue

            # Parse date
            try:
                trade_date = datetime.strptime(trade_date_str[:10], "%Y-%m-%d")
            except Exception:
                trade_date = datetime.now()

            if trade_date < cutoff:
                continue

            trades.append({
                "ticker": ticker,
                "company": company,
                "insider": insider_name,
                "title": title,
                "trade_date": trade_date_str,
                "price": float(price_str) if price_str else 0,
                "quantity": int(qty_str) if qty_str else 0,
                "value": value,
                "source": "openinsider",
            })

        except Exception as e:
            log.debug(f"[Insider] Row parse error: {e}")
            continue

    log.info(f"[Insider] Found {len(trades)} executive buys in past {days_back} days")
    return trades


def get_clustered_buys(trades: list[dict], min_insiders: int = 2) -> list[dict]:
    """
    Returns tickers where 2+ executives bought on the same day.
    Accepts already-fetched trades to avoid double HTTP requests.
    """
    if not trades:
        return []

    # Group by (ticker, trade_date)
    clusters: dict = defaultdict(list)
    for t in trades:
        key = (t["ticker"], t["trade_date"][:10])
        clusters[key].append(t)

    results = []
    for (ticker, date), group in clusters.items():
        if len(group) >= min_insiders:
            total_value = sum(t["value"] for t in group)
            buyers = [f"{t['insider']} ({t['title']})" for t in group]
            results.append({
                "ticker": ticker,
                "company": group[0]["company"],
                "date": date,
                "num_insiders": len(group),
                "total_value": total_value,
                "buyers": buyers,
                "signal": "STRONG_BUY",
                "source": "openinsider_cluster",
                "reason": f"{len(group)} executives bought ${total_value:,.0f} total on {date}",
            })

    results.sort(key=lambda x: x["total_value"], reverse=True)
    return results


def get_buy_candidates() -> list[str]:
    """
    Returns deduplicated list of tickers with clustered insider buys or large solo buys.
    FIX: fetch_insider_buys() called ONCE and reused -- avoids double HTTP request.
    """
    try:
        # Single fetch -- shared by both clustered and singles logic
        all_trades = fetch_insider_buys(days_back=7)

        clusters = get_clustered_buys(all_trades, min_insiders=2)
        singles  = [t for t in all_trades if t["value"] >= 500_000]

        seen = set()
        candidates = []
        for item in clusters:
            if item["ticker"] not in seen:
                seen.add(item["ticker"])
                candidates.append(item["ticker"])
        for t in singles:
            if t["ticker"] not in seen:
                seen.add(t["ticker"])
                candidates.append(t["ticker"])

        log.info(f"[Insider] {len(candidates)} insider buy candidates: {candidates}")
        return candidates
    except Exception as e:
        log.error(f"[Insider] get_buy_candidates failed: {e}")
        return []
