"""
News checker — checks for fresh breaking news on a ticker before any trade.
Core rule (Lance Breitstein):
  - Fresh news behind a move → trade WITH it (continuation)
  - Big move with NO news → trade AGAINST it (mean reversion)
Sources: Google News RSS (free), briefing.com headlines
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote
import pytz


def check_ticker_news(ticker: str, hours_back: int = 4) -> dict:
    """
    Check for fresh breaking news on a stock ticker.
    Returns a dict with:
        - has_news: bool
        - news_type: "bullish" | "bearish" | "neutral" | "none"
        - headlines: list of recent headlines
        - bias: "continuation" | "mean_reversion" | "hold"
        - summary: human-readable explanation
    """
    headlines = _fetch_google_news(ticker, hours_back)

    if not headlines:
        return {
            "ticker": ticker,
            "has_news": False,
            "news_type": "none",
            "bias": "mean_reversion",
            "headlines": [],
            "summary": f"No fresh news found for {ticker} in last {hours_back}h. Big moves without news = mean reversion bias."
        }

    # Classify the news sentiment
    news_type = _classify_news(headlines, ticker)
    bias = "continuation" if news_type in ("bullish", "bearish") else "mean_reversion"

    return {
        "ticker": ticker,
        "has_news": True,
        "news_type": news_type,
        "bias": bias,
        "headlines": headlines[:5],
        "summary": f"Found {len(headlines)} recent headlines for {ticker}. Type: {news_type}. Bias: {bias}."
    }


def check_macro_news(hours_back: int = 2) -> dict:
    """Check for broad market-moving macro news (Fed, tariffs, war, major events)."""
    macro_terms = ["Federal Reserve", "Fed rate", "tariff", "CPI", "inflation", "recession", "S&P 500"]
    all_headlines = []
    for term in macro_terms[:3]:  # Keep API calls limited
        all_headlines.extend(_fetch_google_news(term, hours_back))

    has_macro = len(all_headlines) > 0
    return {
        "has_macro_news": has_macro,
        "headline_count": len(all_headlines),
        "headlines": all_headlines[:5],
        "caution": has_macro,  # Any macro news = trade cautiously
    }


def _fetch_google_news(query: str, hours_back: int = 4) -> list[str]:
    """Fetch headlines from Google News RSS — completely free."""
    try:
        encoded = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        cutoff = datetime.now(pytz.UTC) - timedelta(hours=hours_back)
        headlines = []

        for item in root.findall(".//item"):
            pub_date_str = item.findtext("pubDate", "")
            title = item.findtext("title", "")
            if not title:
                continue

            # Parse publish date
            try:
                from email.utils import parsedate_to_datetime
                pub_date = parsedate_to_datetime(pub_date_str)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=pytz.UTC)
                if pub_date < cutoff:
                    continue
            except Exception:
                pass  # If we can't parse date, include the headline anyway

            headlines.append(title)

        return headlines
    except Exception as e:
        print(f"[News] Error fetching news for '{query}': {e}")
        return []


def _classify_news(headlines: list[str], ticker: str) -> str:
    """
    Simple keyword-based news classification.
    Returns "bullish", "bearish", or "neutral".
    Claude API will do deeper analysis during the decision step.
    """
    bullish_keywords = [
        "beats", "beat", "record", "surge", "jump", "rally", "upgrade",
        "buy", "raises guidance", "acquisition", "partnership", "dividend",
        "profit", "earnings beat", "strong", "growth"
    ]
    bearish_keywords = [
        "miss", "missed", "cut", "drops", "falls", "decline", "downgrade",
        "sell", "lowers guidance", "layoff", "lawsuit", "loss", "warning",
        "weak", "disappoints", "investigation", "recall"
    ]

    text = " ".join(headlines).lower()
    bull_score = sum(1 for kw in bullish_keywords if kw in text)
    bear_score = sum(1 for kw in bearish_keywords if kw in text)

    if bull_score > bear_score:
        return "bullish"
    elif bear_score > bull_score:
        return "bearish"
    else:
        return "neutral"
