"""
Trading 212 API wrapper — portfolio state, order placement, position monitoring.
UK-based broker, commission-free, FCA regulated.

API docs: https://trading212community.github.io/api-documentation/
Auth: Authorization: {api_key}  (raw key — NOT Basic auth, NOT Bearer)

Demo account:  set T212_MODE=demo  in .env  -> demo.trading212.com
Live account:  set T212_MODE=live  in .env  -> live.trading212.com
"""

import requests
import pandas as pd
from io import StringIO
import pytz
import time
import logging
from datetime import datetime, time as dtime
from config.settings import T212_API_KEY, T212_MODE

log = logging.getLogger(__name__)

BASE_URL = (
    "https://demo.trading212.com/api/v0"
    if T212_MODE == "demo"
    else "https://live.trading212.com/api/v0"
)

ET = pytz.timezone("America/New_York")


def _t212_ticker(symbol: str) -> str:
    """Convert standard ticker (AAPL) to Trading 212 format (AAPL_US_EQ)."""
    if "_" in symbol:
        return symbol  # already in T212 format
    return f"{symbol}_US_EQ"


class Trading212Client:
    """
    Drop-in replacement for AlpacaClient.
    Exposes identical method signatures so nothing else needs to change.
    """

    def __init__(self):
        self.session = requests.Session()
        # T212 API uses raw API key in Authorization header — NOT Basic auth
        self.session.headers.update({
            "Authorization": T212_API_KEY,
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make a request with automatic retry on 429 rate limit."""
        url = f"{BASE_URL}{path}"
        for attempt in range(4):
            resp = self.session.request(method, url, timeout=10, **kwargs)
            if resp.status_code == 429:
                wait = 2 ** attempt   # 1s, 2s, 4s, 8s
                log.warning(f"[T212] Rate limited — retrying in {wait}s (attempt {attempt+1}/4)")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def _get(self, path: str) -> dict:
        return self._request("GET", path).json()

    def _post(self, path: str, data: dict) -> dict:
        return self._request("POST", path, json=data).json()

    def _delete(self, path: str) -> None:
        self._request("DELETE", path)

    # -- Portfolio -------------------------------------------------------

    def get_account(self) -> dict:
        """Returns account info: equity, cash, daily P&L."""
        cash = self._get("/equity/account/cash")
        free     = float(cash.get("free", 0))
        invested = float(cash.get("invested", 0))
        ppl      = float(cash.get("ppl", 0))
        total    = float(cash.get("total", free + invested + ppl))
        return {
            "equity":        total,
            "cash":          free,
            "buying_power":  free,
            "last_equity":   total - ppl,
            "daily_pnl":     ppl,
            "daily_pnl_pct": ppl / max(total - ppl, 1),
        }

    def get_positions(self) -> list:
        """Returns list of current positions with unrealised P&L."""
        portfolio = self._get("/equity/portfolio")
        positions = []
        for p in portfolio:
            qty        = float(p.get("quantity", 0))
            avg_price  = float(p.get("averagePrice", 0))
            cur_price  = float(p.get("currentPrice", avg_price))
            ppl        = float(p.get("ppl", 0))
            cost_basis = qty * avg_price
            ticker_raw = p.get("ticker", "")
            symbol = ticker_raw.split("_")[0] if "_" in ticker_raw else ticker_raw
            positions.append({
                "symbol":             symbol,
                "t212_ticker":        ticker_raw,
                "qty":                qty,
                "avg_entry_price":    avg_price,
                "current_price":      cur_price,
                "market_value":       qty * cur_price,
                "unrealized_pnl":     ppl,
                "unrealized_pnl_pct": ppl / max(cost_basis, 0.01),
                "side":               "long",
            })
        return positions

    def get_position(self, symbol: str) -> dict | None:
        """Returns a single position by symbol, or None if not held."""
        for p in self.get_positions():
            if p["symbol"].upper() == symbol.upper():
                return p
        return None

    # -- Orders ----------------------------------------------------------

    def buy(self, symbol: str, notional: float) -> dict:
        """
        Buy a stock by notional value (e.g. notional=500 = buy £500 worth).
        Calculates share count from Stooq last-close price.
        """
        price = self._current_price(symbol)
        if price <= 0:
            raise ValueError(f"Could not get price for {symbol} — cannot size order")

        qty = round(notional / price, 4)
        t212_ticker = _t212_ticker(symbol)

        order = self._post("/equity/orders/market", {
            "ticker":   t212_ticker,
            "quantity": qty,
        })
        log.info(f"[T212] BUY {symbol}: {qty} shares @ ~£{price:.2f} (notional £{notional:.0f})")
        return {
            "order_id": order.get("id", "unknown"),
            "symbol":   symbol,
            "notional": notional,
            "qty":      qty,
            "status":   order.get("status", "submitted"),
        }

    def sell(self, symbol: str, qty: float = None) -> dict:
        """
        Sell a position. If qty is None, closes the full position via DELETE.
        """
        t212_ticker = _t212_ticker(symbol)

        if qty is None:
            self._delete(f"/equity/positions/{t212_ticker}")
            log.info(f"[T212] SELL (full close) {symbol}")
            return {"symbol": symbol, "action": "full_close", "status": "submitted"}

        order = self._post("/equity/orders/market", {
            "ticker":   t212_ticker,
            "quantity": -abs(qty),   # negative quantity = sell in T212 API
        })
        log.info(f"[T212] SELL {symbol}: {qty} shares")
        return {
            "order_id": order.get("id", "unknown"),
            "symbol":   symbol,
            "qty":      qty,
            "status":   order.get("status", "submitted"),
        }

    def set_trailing_stop(self, symbol: str, trail_percent: float) -> dict | None:
        """
        Place a stop-loss order at (current_price * (1 - trail_percent/100)).
        T212 doesn't support native trailing stops, so we place a fixed stop
        and position_check tightens it as price rises.
        """
        position = self.get_position(symbol)
        if not position:
            return None

        cur_price  = position["current_price"]
        stop_price = round(cur_price * (1 - trail_percent / 100), 4)
        t212_ticker = _t212_ticker(symbol)

        try:
            order = self._post("/equity/orders/stop", {
                "ticker":       t212_ticker,
                "quantity":     position["qty"],
                "stopPrice":    stop_price,
                "timeValidity": "GTC",
            })
            log.info(f"[T212] Stop set for {symbol} at £{stop_price:.2f} ({trail_percent:.0f}% trail)")
            return {
                "order_id":      order.get("id"),
                "symbol":        symbol,
                "stop_price":    stop_price,
                "trail_percent": trail_percent,
            }
        except Exception as e:
            # Stop orders may not be available on demo accounts — log but don't crash
            log.warning(f"[T212] Could not set stop for {symbol}: {e}")
            return {"symbol": symbol, "stop_price": stop_price, "note": str(e)}

    def cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        try:
            orders = self._get("/equity/orders")
            for o in orders:
                try:
                    self._delete(f"/equity/orders/{o['id']}")
                except Exception:
                    pass
        except Exception:
            pass

    # -- Price data ------------------------------------------------------

    def get_bars(self, symbol: str, days: int = 30, timeframe=None) -> pd.DataFrame:
        """Get daily OHLCV bars from Stooq (free, no rate limits)."""
        try:
            url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
            resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text), index_col="Date", parse_dates=True)
            return df.sort_index().tail(days)
        except Exception as e:
            log.warning(f"[T212] get_bars failed for {symbol}: {e}")
            return pd.DataFrame()

    def is_market_open(self) -> bool:
        """Returns True if NYSE is currently open (9:30-16:00 ET, Mon-Fri)."""
        now = datetime.now(ET)
        if now.weekday() >= 5:
            return False
        return dtime(9, 30) <= now.time() < dtime(16, 0)

    # -- Internal helpers ------------------------------------------------

    def _current_price(self, symbol: str) -> float:
        """
        Fetch latest close price from Stooq.
        Used to calculate share quantity for notional-value market orders.
        """
        try:
            url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            if df.empty or "Close" not in df.columns:
                return 0.0
            price = float(df["Close"].iloc[-1])
            log.debug(f"[T212] Price for {symbol}: ${price:.2f} (Stooq)")
            return price
        except Exception as e:
            log.warning(f"[T212] _current_price failed for {symbol}: {e}")
            return 0.0
