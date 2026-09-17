from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from app.core.logging import logger
from app.data.mt5_interface import AbstractMT5Adapter
from app.data.mt5_mock import MockMT5Adapter

TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
}

class MarketDataService:
    """Market Data Engine managing symbol resolution, historical candle polling, timestamp normalization, and data freshness validation."""

    def __init__(self, adapter: Optional[AbstractMT5Adapter] = None):
        if adapter is None:
            adapter = MockMT5Adapter()
            adapter.connect()
        self.adapter = adapter
        self._candle_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    def ensure_connected(self) -> bool:
        """Verifies MT5 connection; attempts auto-reconnection if connection drops."""
        if not self.adapter.is_connected():
            logger.warning("MT5 adapter disconnected. Attempting auto-reconnection...")
            return self.adapter.connect()
        return True

    def get_supported_symbols(self) -> List[str]:
        """Returns canonical list of supported instruments."""
        return self.adapter.get_symbols()

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Returns normalized symbol specification."""
        self.ensure_connected()
        return self.adapter.get_symbol_info(symbol)

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Latest tradable price for a symbol (P-17/N-06 fix).

        Prefers the adapter's live bid/ask, then falls back to the last
        cached candle close, then to one freshly fetched candle. Never
        returns a hard-coded constant.
        """
        self.ensure_connected()
        info = self.adapter.get_symbol_info(symbol) or {}
        bid = info.get("bid")
        if bid is not None:
            return float(bid)
        ask = info.get("ask")
        if ask is not None:
            return float(ask)
        cached = self._candle_cache.get(symbol, {})
        for timeframe in ("M1", "M5", "M15", "M30", "H1", "H4"):
            series = cached.get(timeframe)
            if series:
                close = series[-1].get("close")
                if close is not None:
                    return float(close)
        candles = self.fetch_candles(symbol, "M5", count=1)
        if candles:
            close = candles[-1].get("close")
            if close is not None:
                return float(close)
        return None

    def fetch_candles(
        self, symbol: str, timeframe: str, count: int = 500
    ) -> List[Dict[str, Any]]:
        """Fetches historical candles, normalizes timestamps to UTC ISO format, and updates local cache."""
        self.ensure_connected()
        candles = self.adapter.get_historical_candles(symbol, timeframe, count)

        # Normalize timestamps to UTC ISO format if needed
        normalized = []
        for c in candles:
            t = c.get("time")
            if isinstance(t, (int, float)):
                dt = datetime.fromtimestamp(t, tz=timezone.utc)
                c["timestamp"] = dt.isoformat()
            normalized.append(c)

        if symbol not in self._candle_cache:
            self._candle_cache[symbol] = {}
        self._candle_cache[symbol][timeframe] = normalized
        return normalized

    def is_data_stale(
        self, symbol: str, timeframe: str, max_delay_multiplier: float = 2.5
    ) -> bool:
        """Determines if the latest candle in cache/feed is stale based on timeframe duration."""
        tf_mins = TIMEFRAME_MINUTES.get(timeframe.upper(), 5)
        max_allowed_delay = timedelta(minutes=tf_mins * max_delay_multiplier)

        candles = self._candle_cache.get(symbol, {}).get(timeframe, [])
        if not candles:
            candles = self.fetch_candles(symbol, timeframe, count=10)

        if not candles:
            return True

        latest = candles[-1]
        latest_ts = latest.get("timestamp")
        if not latest_ts:
            return True

        latest_dt = datetime.fromisoformat(latest_ts)
        now_utc = datetime.now(timezone.utc)

        if (now_utc - latest_dt) > max_allowed_delay:
            logger.warning(f"Stale data detected for {symbol} {timeframe}. Latest candle: {latest_ts}, Now: {now_utc.isoformat()}")
            return True

        return False

    def detect_missing_candles(
        self, candles: List[Dict[str, Any]], timeframe: str
    ) -> List[Dict[str, Any]]:
        """Scans a candle series for missing gaps in the timeline."""
        if len(candles) < 2:
            return []

        tf_mins = TIMEFRAME_MINUTES.get(timeframe.upper(), 5)
        expected_delta = timedelta(minutes=tf_mins)
        gaps = []

        for i in range(1, len(candles)):
            prev_dt = datetime.fromisoformat(candles[i - 1]["timestamp"])
            curr_dt = datetime.fromisoformat(candles[i]["timestamp"])
            
            # Skip gaps across weekend closes (>= 48h)
            diff = curr_dt - prev_dt
            if diff > (expected_delta * 1.5) and diff < timedelta(hours=48):
                gaps.append({
                    "timeframe": timeframe,
                    "gap_start": prev_dt.isoformat(),
                    "gap_end": curr_dt.isoformat(),
                    "missing_minutes": int((diff - expected_delta).total_seconds() / 60)
                })

        return gaps
