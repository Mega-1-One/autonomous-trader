from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class AbstractMT5Adapter(ABC):
    """Abstract interface defining required contract for MetaTrader 5 broker interaction."""

    @abstractmethod
    def connect(self) -> bool:
        """Establishes connection to MT5 terminal / account."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Closes connection to MT5 terminal."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Returns True if connected to MT5 broker, False otherwise."""
        pass

    @abstractmethod
    def get_symbols(self) -> List[str]:
        """Returns list of available trading symbols."""
        pass

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Returns symbol specification details (digits, point_size, tick_size, contract_size, volume limits)."""
        pass

    @abstractmethod
    def get_ticks(self, symbol: str, count: int = 100) -> List[Dict[str, Any]]:
        """Returns recent tick data for symbol."""
        pass

    @abstractmethod
    def get_historical_candles(
        self, symbol: str, timeframe: str, count: int = 500
    ) -> List[Dict[str, Any]]:
        """Returns historical OHLCV candle data."""
        pass

    @abstractmethod
    def send_order(self, order_request: Dict[str, Any]) -> Dict[str, Any]:
        """Submits trade order to MT5 and returns broker execution response."""
        pass

    @abstractmethod
    def get_open_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves active open positions directly from MT5 terminal or mock engine."""
        pass

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """Returns account balance, equity, leverage, margin."""
        pass
