from typing import List

from app.context.timeframe_engine import Candle

class DeterministicCandleBuilder:
    """Reconstructs multi-timeframe candles deterministically from validated tick streams."""

    TIMEFRAME_SECONDS = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400
    }

    def build_candles(self, symbol: str, tf: str, ticks: List[dict]) -> List[Candle]:
        if not ticks or tf not in self.TIMEFRAME_SECONDS:
            return []

        interval = self.TIMEFRAME_SECONDS[tf]
        candles = []

        current_bin = -1
        open_p = 0.0
        high_p = 0.0
        low_p = 0.0
        close_p = 0.0
        tick_cnt = 0

        for t in ticks:
            ts = float(t["timestamp"])
            last_p = float(t.get("last", t["bid"]))
            bin_idx = int(ts // interval)

            if bin_idx != current_bin:
                if current_bin != -1:
                    candles.append(Candle(
                        symbol=symbol, timeframe=tf, open=open_p, high=high_p, low=low_p, close=close_p,
                        volume=tick_cnt, timestamp=float(current_bin * interval)
                    ))
                current_bin = bin_idx
                open_p = last_p
                high_p = last_p
                low_p = last_p
                close_p = last_p
                tick_cnt = 1
            else:
                high_p = max(high_p, last_p)
                low_p = min(low_p, last_p)
                close_p = last_p
                tick_cnt += 1

        if current_bin != -1 and tick_cnt > 0:
            candles.append(Candle(
                symbol=symbol, timeframe=tf, open=open_p, high=high_p, low=low_p, close=close_p,
                volume=tick_cnt, timestamp=float(current_bin * interval)
            ))

        return candles
