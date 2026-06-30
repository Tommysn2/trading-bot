"""
Alpaca API wrapper — portfolio state, order placement, position monitoring.
Supports both paper and live trading via ALPACA_BASE_URL in .env.
"""

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TrailingStopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta
import pytz
from config.settings import ALPACA_API_KEY, ALPACA_SECRET_KEY, PAPER_TRADING


class AlpacaClient:
    def __init__(self):
        self.trading = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=PAPER_TRADING
        )
        self.data = StockHistoricalDataClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY
        )

    # ── Portfolio ────────────────────────────────────────────

    def get_account(self):
        """Returns account info: equity, cash, buying_power, daily P&L."""
        acc = self.trading.get_account()
        return {
            "equity": float(acc.equity),
            "cash": float(acc.cash),
            "buying_power": float(acc.buying_power),
            "last_equity": float(acc.last_equity),
            "daily_pnl": float(acc.equity) - float(acc.last_equity),
            "daily_pnl_pct": (float(acc.equity) - float(acc.last_equity)) / float(acc.last_equity),
        }

    def get_positions(self):
        """Returns list of current positions with unrealised P&L."""
        positions = self.trading.get_all_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc),
                "side": p.side.value,
            }
            for p in positions
        ]

    def get_position(self, symbol: str):
        """Returns a single position, or None if not held."""
        try:
            p = self.trading.get_open_position(symbol)
            return {
                "symbol": p.symbol,
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl_pct": float(p.unrealized_plpc),
            }
        except Exception:
            return None

    # ── Orders ──────────────────────────────────────────────

    def buy(self, symbol: str, notional: float):
        """Buy a stock by dollar amount (e.g. notional=500 = buy £500 worth)."""
        req = MarketOrderRequest(
            symbol=symbol,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = self.trading.submit_order(req)
        return {"order_id": str(order.id), "symbol": symbol, "notional": notional, "status": order.status.value}

    def sell(self, symbol: str, qty: float = None):
        """Sell all shares of a symbol, or a specific qty."""
        if qty is None:
            # liquidate entire position
            self.trading.close_position(symbol)
            return {"symbol": symbol, "action": "full_close"}
        req = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        order = self.trading.submit_order(req)
        return {"order_id": str(order.id), "symbol": symbol, "qty": qty, "status": order.status.value}

    def set_trailing_stop(self, symbol: str, trail_percent: float):
        """
        Place a trailing stop order on an existing position.
        trail_percent = 10 means stop follows 10% below highest price.
        """
        position = self.get_position(symbol)
        if not position:
            return None
        req = TrailingStopOrderRequest(
            symbol=symbol,
            qty=position["qty"],
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            trail_percent=trail_percent,
        )
        order = self.trading.submit_order(req)
        return {"order_id": str(order.id), "symbol": symbol, "trail_percent": trail_percent}

    def cancel_all_orders(self):
        """Cancel all open orders."""
        self.trading.cancel_orders()

    # ── Price data ──────────────────────────────────────────

    def get_bars(self, symbol: str, days: int = 30, timeframe=TimeFrame.Day):
        """Get OHLCV bar data for regime/Markov calculation."""
        end = datetime.now(pytz.UTC)
        start = end - timedelta(days=days + 5)  # buffer for weekends
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=timeframe, start=start, end=end)
        bars = self.data.get_stock_bars(req)
        df = bars.df
        if hasattr(df.index, 'levels'):
            df = df.loc[symbol]
        return df.tail(days)

    def is_market_open(self):
        """Returns True if the US stock market is currently open."""
        clock = self.trading.get_clock()
        return clock.is_open
