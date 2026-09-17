from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class Candle:
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: float

class TimeframeEngine:
    """Aggregates real-time ticks into synchronized candles for 1m, 5m, 15m, 1h, and 4h timeframes."""

    TIMEFRAME_SECONDS = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400
    }

    def __init__(self):
        self.candles: Dict[str, List[Candle]] = {tf: [] for tf in self.TIMEFRAME_SECONDS}
        self.current_drafts: Dict[str, Optional[Candle]] = {tf: None for tf in self.TIMEFRAME_SECONDS}

    def process_tick(self, symbol: str, price: float, timestamp: float, volume: int = 1) -> None:
        for tf, duration in self.TIMEFRAME_SECONDS.items():
            bucket_ts = (timestamp // duration) * duration
            draft = self.current_drafts[tf]

            if draft is None or draft.timestamp != bucket_ts:
                if draft is not None:
                    self.candles[tf].append(draft)
                    if len(self.candles[tf]) > 200:
                        self.candles[tf].pop(0)

                self.current_drafts[tf] = Candle(
                    symbol=symbol, timeframe=tf, open=price, high=price, low=price, close=price,
                    volume=volume, timestamp=bucket_ts
                )
            else:
                draft.high = max(draft.high, price)
                draft.low = min(draft.low, price)
                draft.close = price
                draft.volume += volume

    def get_candles(self, timeframe: str) -> List[Candle]:
        candles = list(self.candles.get(timeframe, []))
        if self.current_drafts.get(timeframe):
            candles.append(self.current_drafts[timeframe])
        return candles
