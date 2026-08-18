from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.logging import logger
from app.data.mt5_interface import AbstractMT5Adapter

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

class RealMT5Adapter(AbstractMT5Adapter):
    """Concrete MT5 Adapter wrapping MetaTrader 5 Python API."""

    def __init__(self):
        self._connected = False
        self.symbol_mappings: Dict[str, List[str]] = settings.risk_config.get(
            "symbol_mappings",
            {
                "XAUUSD": ["XAUUSD", "XAUUSDm", "GOLD", "GOLDm"],
                "EURUSD": ["EURUSD", "EURUSDm"],
                "GBPUSD": ["GBPUSD", "GBPUSDm"],
                "NAS100": ["NAS100", "US100", "USTECH"],
            }
        )

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            logger.warning("MetaTrader5 package is not installed on this system.")
            self._connected = False
            return False

        init_kwargs = {}
        if settings.MT5_PATH:
            init_kwargs["path"] = settings.MT5_PATH
        if settings.MT5_LOGIN:
            init_kwargs["login"] = settings.MT5_LOGIN
        if settings.MT5_PASSWORD:
            init_kwargs["password"] = settings.MT5_PASSWORD
        if settings.MT5_SERVER:
            init_kwargs["server"] = settings.MT5_SERVER

        if not mt5.initialize(**init_kwargs):
            logger.error(f"MT5 initialize failed, error code: {mt5.last_error()}")
            self._connected = False
            return False

        self._connected = True
        logger.info("Successfully connected to MetaTrader 5 terminal.")
        return True

    def disconnect(self) -> None:
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("Disconnected from MetaTrader 5 terminal.")

    def is_connected(self) -> bool:
        if not MT5_AVAILABLE or not self._connected:
            return False
        terminal_info = mt5.terminal_info()
        return terminal_info is not None and terminal_info.connected

    def get_symbols(self) -> List[str]:
        if not self.is_connected():
            return list(self.symbol_mappings.keys())
        symbols = mt5.symbols_get()
        if not symbols:
            return []
        return [s.name for s in symbols]

    def resolve_broker_symbol(self, canonical_symbol: str) -> str:
        """Maps canonical symbol (e.g. XAUUSD) to broker-specific name (e.g. XAUUSDm)."""
        candidates = self.symbol_mappings.get(canonical_symbol.upper(), [canonical_symbol.upper()])
        if not self.is_connected():
            return candidates[0]
        
        available = self.get_symbols()
        for cand in candidates:
            if cand in available:
                return cand
        return canonical_symbol

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        broker_symbol = self.resolve_broker_symbol(symbol)
        if not self.is_connected():
            return None

        info = mt5.symbol_info(broker_symbol)
        if info is None:
            return None

        return {
            "canonical_name": symbol.upper(),
            "broker_name": info.name,
            "digits": info.digits,
            "point_size": info.point,
            "tick_size": info.trade_tick_size,
            "tick_value": info.trade_tick_value,
            "contract_size": info.trade_contract_size,
            "min_volume": info.volume_min,
            "max_volume": info.volume_max,
            "volume_step": info.volume_step,
            "bid": info.bid,
            "ask": info.ask,
            "spread": info.spread
        }

    def get_ticks(self, symbol: str, count: int = 100) -> List[Dict[str, Any]]:
        broker_symbol = self.resolve_broker_symbol(symbol)
        if not self.is_connected():
            return []

        ticks = mt5.copy_ticks_from(broker_symbol, datetime.now(timezone.utc), count, mt5.COPY_TICKS_ALL)
        if ticks is None:
            return []

        result = []
        for t in ticks:
            result.append({
                "time": int(t[0]),
                "bid": float(t[1]),
                "ask": float(t[2]),
                "last": float(t[3]) if len(t) > 3 else float(t[1]),
                "volume": float(t[4]) if len(t) > 4 else 1.0
            })
        return result

    def get_historical_candles(
        self, symbol: str, timeframe: str, count: int = 500
    ) -> List[Dict[str, Any]]:
        broker_symbol = self.resolve_broker_symbol(symbol)
        if not self.is_connected():
            return []

        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
        }
        mt5_tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M5)

        rates = mt5.copy_rates_from_pos(broker_symbol, mt5_tf, 0, count)
        if rates is None:
            return []

        candles = []
        for r in rates:
            dt = datetime.fromtimestamp(r['time'], tz=timezone.utc)
            candles.append({
                "timestamp": dt.isoformat(),
                "time": int(r['time']),
                "open": float(r['open']),
                "high": float(r['high']),
                "low": float(r['low']),
                "close": float(r['close']),
                "volume": float(r['real_volume']) if r['real_volume'] > 0 else float(r['tick_volume'])
            })
        return candles

    def fetch_candles(self, symbol: str, timeframe: str, count: int = 500) -> List[Dict[str, Any]]:
        return self.get_historical_candles(symbol, timeframe, count)

    def send_order(self, order_request: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_connected():
            return {"retcode": -1, "comment": "MT5 Not Connected", "order": 0}

        broker_symbol = self.resolve_broker_symbol(order_request.get("symbol", "XAUUSD"))
        order_type_str = order_request.get("type", "BUY").upper()
        order_type = mt5.ORDER_TYPE_BUY if order_type_str == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": broker_symbol,
            "volume": float(order_request.get("volume", 0.01)),
            "type": order_type,
            "price": float(order_request.get("price", 0.0)),
            "sl": float(order_request.get("stop_loss", 0.0)),
            "tp": float(order_request.get("take_profit", 0.0)),
            "deviation": 20,
            "magic": 100001,
            "comment": order_request.get("comment", "Autonomous Trader Order"),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            return {"retcode": -1, "comment": "Order Send Returned None", "order": 0}

        return {
            "retcode": result.retcode,
            "comment": result.comment,
            "order": result.order,
            "deal": result.deal,
            "volume": result.volume,
            "price": result.price
        }

    def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves active open positions directly from MT5 terminal via mt5.positions_get()."""
        if not self.is_connected():
            return []

        if symbol:
            broker_symbol = self.resolve_broker_symbol(symbol)
            raw_positions = mt5.positions_get(symbol=broker_symbol)
        else:
            raw_positions = mt5.positions_get()

        if raw_positions is None:
            return []

        pos_list = []
        for pos in raw_positions:
            p_dict = pos._asdict()
            pos_list.append({
                "ticket": p_dict.get("ticket"),
                "symbol": symbol or p_dict.get("symbol"),
                "type": "BUY" if p_dict.get("type") == 0 else "SELL",
                "volume": p_dict.get("volume"),
                "price_open": p_dict.get("price_open"),
                "sl": p_dict.get("sl"),
                "tp": p_dict.get("tp"),
                "profit": p_dict.get("profit")
            })
        return pos_list

    def get_account_info(self) -> Dict[str, Any]:
        if not self.is_connected():
            return {}
        info = mt5.account_info()
        if info is None:
            return {}
        return {
            "login": info.login,
            "trade_mode": info.trade_mode,
            "leverage": info.leverage,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "currency": info.currency,
            "server": info.server
        }
