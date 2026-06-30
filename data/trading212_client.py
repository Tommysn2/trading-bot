"""
Trading 212 API wrapper — portfolio state, order placement, position monitoring.
UK-based broker, commission-free, FCA regulated.

API docs: https://trading212community.github.io/api-documentation/

Demo account:  set T212_MODE=demo  in .env  → demo.trading212.com
Live account:  set T212_MODE=live  in .env  → live.trading212.com
"""

import requests
import yfinance as yf
import pytz
import time
from datetime import datetime, time as dtime
from config.settings import T212_API_KEY, T212_SECRET_KEY, T212_MODE

# ── API base URL ────────────────────────────────────────────
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
        self.session.auth = (T212_API_KEY, T212_SECRET_KEY)
        self.session.headers.update({
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make a request with automatic retry on 429 rate limit."""
        url = f"{BASE_URL}{path}"
        for attempt in range(4):
            resp = self.session.request(method, url, timeout=10, **kwargs)
            if resp.status_code == 429:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s
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

    # ── Portfolio ────────────────────────────────────────────

    def get_account(self) -> dict:
        """Returns account info: equity, cash, daily P&L."""
        cash = self._get("/equity/account/cash")
        # T212 cash endpoint fields:
        # free = uninvested cash, invested = in positions, ppl = unrealised P&L
        # total = cash + invested + ppl  (total account value)
        free      = float(cash.get("free", 0))
        invested  = float(cash.get("invested", 0))
        ppl       = float(cash.get("ppl", 0))
        total     = float(cash.get("total", free + invested + ppl))

        # Daily P&L approximation: T212 doesn't expose yesterday's equity directly,
        # so we use the running unrealised P&L as a proxy.
        return {
            "equity":        total,
            "cash":          free,
            "buying_power":  free,
            "last_equity":   total - ppl,   # approximate
            "daily_pnl":     ppl,
            "daily_pnl_pct": ppl / max(total - ppl, 1),
        }

    def get_positions(self) -> list:
        """Returns list of current positions with unrealised P&L."""
        portfolio = self._get("/equity/portfolio")
        positions = []
        for p in portfolio:
            qty         = float(p.get("quantity", 0))
            avg_price   = float(p.get("averagePrice", 0))
            cur_price   = float(p.get("currentPrice", avg_price))
            ppl         = float(p.get("ppl", 0))
            cost_basis  = qty * avg_price
            ticker_raw  = p.get("ticker", "")
            # Strip T212 suffix to get standard symbol (AAPL_US_EQ → AAPL)
            symbol = ticker_raw.split("_")[0] if "_" in ticker_raw else ticker_raw

            positions.append({
                "symbol":            symbol,
                "t212_ticker":       ticker_raw,
                "qty":               qty,
                "avg_entry_price":   avg_price,
                "current_price":     cur_price,
                "market_value":      qty * cur_price,
                "unrealized_pnl":    ppl,
                "unrealized_pnl_pct": ppl / max(cost_basis, 0.01),
                "side":              "long",
            })
        return positions

    def get_position(self, symbol: str) -> dict | None:
        """Returns a single position by symbol, or None if not held."""
        positions = self.get_positions()
        for p in positions:
            if p["symbol"].upper() == symbol.upper():
                return p
        return None

    # ── Orders ──────────────────────────────────────────────

    def buy(self, symbol: str, notional: float) -> dict:
        """
        Buy a stock by notional value (e.g. notional=500 = buy £500 worth).
        Calculates share count from current price via yfinance.
        """
        # Get current price to calculate quantity
        price = self._current_price(symbol)
        if price <= 0:
            raise ValueError(f"Could not get price for {symbol}")

        qty = round(notional / price, 4)
        t212_ticker = _t212_ticker(symbol)

        order = self._post("/equity/orders/market", {
            "ticker":   t212_ticker,
            "quantity": qty,
        })
        return {
            "order_id": order.get("id", "unknown"),
            "symbol":   symbol,
            "notional": notional,
            "qty":      qty,
            "status":   order.get("status", "submitted"),
        }

    def sell(self, symbol: str, qty: float = None) -> dict:
        """
        Sell a position. If qty is None, closes the full position.
        T212 uses DELETE /equity/positions/{ticker} to close fully.
        """
        t212_ticker = _t212_ticker(symbol)

        if qty is None:
            # Close entire position
            self._delete(f"/equity/positions/{t212_ticker}")
            return {"symbol": symbol, "action": "full_close", "status": "submitted"}

        order = self._post("/equity/orders/market", {
            "ticker":   t212_ticker,
            "quantity": -abs(qty),   # negative = sell in T212 API
        })
        return {
            "order_id": order.get("id", "unknown"),
            "symbol":   symbol,
            "qty":      qty,
            "status":   order.get("status", "submitted"),
        }

    def set_trailing_stop(self, symbol: str, trail_percent: float) -> dict | None:
        """
        Place a stop-loss order at (current_price × (1 - trail_percent/100)).
        T212 doesn't support native trailing stops, so we place a fixed stop
        and the position_check loop will ratchet it upward as price rises.
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
            return {
                "order_id":     order.get("id"),
                "symbol":       symbol,
                "stop_price":   stop_price,
                "trail_percent": trail_percent,
            }
        except Exception as e:
            # Stop order may not be available on demo — log but don't crash
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

    # ── Price data ──────────────────────────────────────────

    def get_bars(self, symbol: str, days: int = 30, timeframe=None):
        """Get daily OHLCV bars via yfinance (same data, no extra API cost)."""
        df = yf.download(symbol, period=f"{days + 10}d", interval="1d",
                         progress=False, auto_adjust=True)
        return df.tail(days)

    def is_market_open(self) -> bool:
        """
        Returns True if NYSE is currently open (9:30–16:00 ET, Mon–Fri).
        T212 doesn't have a clock endpoint, so we derive from time.
        """
        now = datetime.now(ET)
        if now.weekday() >= 5:   # Saturday or Sunday
            return False
        market_open  = dtime(9, 30)
        market_close = dtime(16, 0)
        return market_open <= now.time() <= market_close

    # ── Internal helpers ─────────────────────────────────────

    def _current_price(self, symbol: str) -> float:
        """Fetch latest price from yfinance (free, accurate for US stocks)."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", 0)
            return float(price) if price else 0.0
        except Exception:
            return 0.0
