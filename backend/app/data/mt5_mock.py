from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import numpy as np

from app.data.mt5_interface import AbstractMT5Adapter

DEFAULT_SYMBOL_SPECS = {
    "XAUUSD": {
        "canonical_name": "XAUUSD",
        "broker_name": "XAUUSD",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 100.0,
        "min_volume": 0.01,
        "max_volume": 100.0,
        "volume_step": 0.01,
        "base_price": 2400.0,
    },
    "EURUSD": {
        "canonical_name": "EURUSD",
        "broker_name": "EURUSD",
        "digits": 5,
        "point_size": 0.00001,
        "tick_size": 0.00001,
        "tick_value": 1.0,
        "contract_size": 100000.0,
        "min_volume": 0.01,
        "max_volume": 100.0,
        "volume_step": 0.01,
        "base_price": 1.0850,
    },
    "GBPUSD": {
        "canonical_name": "GBPUSD",
        "broker_name": "GBPUSD",
        "digits": 5,
        "point_size": 0.00001,
        "tick_size": 0.00001,
        "tick_value": 1.0,
        "contract_size": 100000.0,
        "min_volume": 0.01,
        "max_volume": 100.0,
        "volume_step": 0.01,
        "base_price": 1.2800,
    },
    "NAS100": {
        "canonical_name": "NAS100",
        "broker_name": "NAS100",
        "digits": 2,
        "point_size": 0.01,
        "tick_size": 0.01,
        "tick_value": 1.0,
        "contract_size": 20.0,
        "min_volume": 0.01,
        "max_volume": 100.0,
        "volume_step": 0.01,
        "base_price": 19500.0,
    },
}

class MockMT5Adapter(AbstractMT5Adapter):
    """Deterministic Mock MT5 Adapter for offline testing and paper trading."""

    def __init__(self, initial_balance: float = 10000.0):
        self._connected = False
        self.balance = initial_balance
        self.equity = initial_balance
        self.symbol_specs = DEFAULT_SYMBOL_SPECS
        self.orders: List[Dict[str, Any]] = []
        self.positions: List[Dict[str, Any]] = []
        self._ticket_counter = 1000000

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_symbols(self) -> List[str]:
        return list(self.symbol_specs.keys())

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.symbol_specs.get(symbol.upper())

    def get_ticks(self, symbol: str, count: int = 100) -> List[Dict[str, Any]]:
        info = self.get_symbol_info(symbol)
        if not info:
            return []
        
        base_price = info["base_price"]
        now = datetime.now(timezone.utc)
        ticks = []
        
        for i in range(count):
            tick_time = now - timedelta(seconds=(count - i))
            bid = base_price + (i * 0.01)
            ask = bid + (info["point_size"] * 10)
            ticks.append({
                "time": tick_time.isoformat(),
                "bid": round(bid, info["digits"]),
                "ask": round(ask, info["digits"]),
                "last": round(bid, info["digits"]),
                "volume": 1
            })
        return ticks

    def fetch_candles(self, symbol: str, timeframe: str, count: int = 100) -> List[Dict[str, Any]]:
        info = self.get_symbol_info(symbol)
        if not info:
            return []

        base_price = info["base_price"]
        now = datetime.now(timezone.utc)
        candles = []
        
        for i in range(count):
            candle_time = now - timedelta(minutes=(count - i) * 5)
            open_p = base_price + np.sin(i / 5.0) * 2.0
            close_p = open_p + np.cos(i / 5.0) * 1.5
            high_p = max(open_p, close_p) + 1.0
            low_p = min(open_p, close_p) - 1.0
            
            candles.append({
                "time": candle_time.isoformat(),
                "timestamp": candle_time.isoformat(),
                "open": round(open_p, info["digits"]),
                "high": round(high_p, info["digits"]),
                "low": round(low_p, info["digits"]),
                "close": round(close_p, info["digits"]),
                "tick_volume": 100 + i * 2,
                "volume": 100 + i * 2,
                "spread": 10,
                "real_volume": 0
            })


        return candles

    def get_historical_candles(self, symbol: str, timeframe: str, count: int = 100) -> List[Dict[str, Any]]:
        return self.fetch_candles(symbol, timeframe, count)


    def send_order(self, order_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Simulates placing an order and returns a mock retcode and order ticket."""
        if not self._connected:
            return {"retcode": 10014, "comment": "MT5 Adapter Not Connected"}

        self._ticket_counter += 1
        ticket = self._ticket_counter
        symbol = order_dict.get("symbol", "XAUUSD")
        price = order_dict.get("price", 2400.0)
        volume = order_dict.get("volume", 0.1)
        direction = order_dict.get("type", "BUY")

        pos_record = {
            "ticket": ticket,
            "symbol": symbol,
            "type": direction,
            "volume": volume,
            "price_open": price,
            "sl": order_dict.get("stop_loss", 0.0),
            "tp": order_dict.get("take_profit", 0.0),
        }
        self.positions.append(pos_record)

        resp = {
            "retcode": 10009,
            "order": ticket,
            "deal": ticket + 50000,
            "volume": volume,
            "price": price,
            "comment": "Request executed successfully"
        }
        self.orders.append(resp)
        return resp

    def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns mock active open positions."""
        if symbol:
            return [p for p in self.positions if p["symbol"] == symbol]
        return list(self.positions)

    def get_account_info(self) -> Dict[str, Any]:
        return {
            "login": 999999,
            "trade_mode": 0,
            "leverage": 100,
            "balance": self.balance,
            "equity": self.equity,
            "margin": 0.0,
            "free_margin": self.balance,
            "currency": "USD",
            "server": "MockServer"
        }
