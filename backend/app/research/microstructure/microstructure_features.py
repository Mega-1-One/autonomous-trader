import numpy as np
from typing import List, Dict
from app.context.timeframe_engine import Candle

class MicrostructureFeatureGenerator:
    """Generates market microstructure, spread dynamics, and session features."""

    def generate_microstructure_features(self, candles: List[Candle], idx: int) -> Dict[str, float]:
        if idx < 30:
            return {}

        c_curr = candles[idx]
        past_closes = [c.close for c in candles[idx-30:idx+1]]
        past_volumes = [c.volume for c in candles[idx-30:idx+1]]

        # 1. Spread dynamics proxy & expansion
        spread_proxy = abs(c_curr.high - c_curr.low) * 0.1
        spread_avg = float(np.mean([abs(c.high - c.low)*0.1 for c in candles[idx-14:idx]]))
        spread_expansion = spread_proxy / (spread_avg + 1e-6)

        # 2. Tick arrival intensity & acceleration
        vol_14 = float(np.mean(past_volumes[-14:]))
        tick_intensity = c_curr.volume / (vol_14 + 1e-6)
        tick_accel = tick_intensity - (past_volumes[-2] / (vol_14 + 1e-6))

        # 3. Consecutive directional movement
        direction_sum = 0
        for i in range(idx-5, idx):
            direction_sum += 1 if candles[i+1].close > candles[i].close else -1

        # 4. Short-term price impact proxy
        price_impact = abs(c_curr.close - candles[idx-1].close) / (float(c_curr.volume) + 1.0)

        # 5. Session Microstructure
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(c_curr.timestamp, tz=timezone.utc)
        hour = dt.hour
        is_london_open = 1.0 if (7 <= hour <= 9) else 0.0
        is_ny_open = 1.0 if (12 <= hour <= 14) else 0.0
        is_overlap = 1.0 if (13 <= hour <= 16) else 0.0

        return {
            "micro_spread_expansion": spread_expansion,
            "micro_tick_intensity": tick_intensity,
            "micro_tick_accel": tick_accel,
            "micro_consec_direction": float(direction_sum),
            "micro_price_impact": price_impact,
            "session_is_london_open": is_london_open,
            "session_is_ny_open": is_ny_open,
            "session_is_overlap": is_overlap
        }
