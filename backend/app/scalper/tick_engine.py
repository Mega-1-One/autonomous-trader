from dataclasses import dataclass
from collections import deque
from typing import Dict, List, Optional
import time

from app.core.logging import logger
from app.core.pricing import spread_in_pips

@dataclass
class TickData:
    symbol: str
    bid: float
    ask: float
    last: float
    spread_pips: float
    timestamp: float  # Unix timestamp in seconds
    tick_volume: int = 1

    def is_stale(self, max_stale_seconds: float = 5.0, reference_time: Optional[float] = None) -> bool:
        """Returns True if the tick is older than max_stale_seconds relative to reference_time."""
        if max_stale_seconds <= 0 or max_stale_seconds == float('inf'):
            return False
        ref = reference_time if reference_time is not None else time.time()
        return (ref - self.timestamp) > max_stale_seconds


class TickBuffer:
    """Rolling tick buffer for high-frequency scalping feature extraction."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.ticks: deque[TickData] = deque(maxlen=max_size)

    def add_tick(self, tick: TickData) -> bool:
        """Appends a new tick to the buffer if it is not a duplicate."""
        if len(self.ticks) > 0:
            last_tick = self.ticks[-1]
            if (last_tick.timestamp == tick.timestamp and
                last_tick.bid == tick.bid and
                last_tick.ask == tick.ask):
                return False  # Duplicate tick rejected

        self.ticks.append(tick)
        return True

    def get_last_n(self, n: int) -> List[TickData]:
        """Returns the most recent n ticks."""
        return list(self.ticks)[-n:]

    def __len__(self) -> int:
        return len(self.ticks)

class TickEngine:
    """Real-time MT5 tick ingestion and buffer management engine."""

    def __init__(self, max_stale_seconds: float = 5.0):
        self.buffers: Dict[str, TickBuffer] = {}
        self.max_stale_seconds = max_stale_seconds

    def process_tick(self, symbol: str, bid: float, ask: float, last: Optional[float] = None,
                     timestamp: Optional[float] = None, tick_volume: int = 1,
                     point_size: float = 0.001, digits: int = 3) -> Optional[TickData]:
        """Processes and validates an incoming tick for a given symbol."""
        if timestamp is None:
            timestamp = time.time()

        if last is None:
            last = bid

        # Calculate spread in pips (canonical pip_size per ADR-4; legacy
        # digits rules only for symbols with no specification)
        spread_pips = spread_in_pips(bid, ask, symbol=symbol, digits=digits, point_size=point_size)

        tick = TickData(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            spread_pips=spread_pips,
            timestamp=timestamp,
            tick_volume=tick_volume
        )

        if tick.is_stale(self.max_stale_seconds):
            logger.warning(f"[TickEngine] STALE TICK REJECTED for {symbol}: age={round(time.time() - timestamp, 2)}s")
            return None

        if symbol not in self.buffers:
            self.buffers[symbol] = TickBuffer(max_size=1000)

        added = self.buffers[symbol].add_tick(tick)
        if not added:
            return None  # Duplicate ignored

        return tick

    def get_buffer(self, symbol: str) -> Optional[TickBuffer]:
        return self.buffers.get(symbol)
