import numpy as np
from typing import List, Dict, Any
from app.context.timeframe_engine import Candle

class FeatureGenerator:
    """Generates 7 feature families from candle price history (using past data only, t <= idx)."""

    def generate_all_features(self, candles: List[Candle], idx: int) -> Dict[str, float]:
        if idx < 30:
            return {}

        c_curr = candles[idx]
        past_closes = [c.close for c in candles[idx-30:idx+1]]
        past_highs = [c.high for c in candles[idx-30:idx+1]]
        past_lows = [c.low for c in candles[idx-30:idx+1]]
        past_ranges = [c.high - c.low for c in candles[idx-30:idx+1]]

        # A. Momentum
        ret_1 = (c_curr.close - past_closes[-2]) / past_closes[-2] if past_closes[-2] > 0 else 0.0
        ret_5 = (c_curr.close - past_closes[-6]) / past_closes[-6] if past_closes[-6] > 0 else 0.0
        ret_15 = (c_curr.close - past_closes[-16]) / past_closes[-16] if past_closes[-16] > 0 else 0.0
        accel = ret_1 - ret_5

        # B. Volatility
        atr_14 = float(np.mean(past_ranges[-14:])) if len(past_ranges) >= 14 else 1.0
        realized_vol = float(np.std(np.diff(past_closes[-14:]))) if len(past_closes) >= 14 else 0.0
        vol_ratio = past_ranges[-1] / (atr_14 + 1e-6)

        # C. Market Structure
        max_30 = float(np.max(past_highs))
        min_30 = float(np.min(past_lows))
        range_pos = (c_curr.close - min_30) / (max_30 - min_30 + 1e-6)
        dist_high = (max_30 - c_curr.close) / (c_curr.close + 1e-6)

        # D. Liquidity / Price Location
        vwap = float(np.mean(past_closes))
        dist_vwap = (c_curr.close - vwap) / (vwap + 1e-6)

        # E. Trend / Mean Reversion
        ma20 = float(np.mean(past_closes[-20:]))
        dev_mean = (c_curr.close - ma20) / (ma20 + 1e-6)
        ma_slope = (past_closes[-1] - past_closes[-5]) / (past_closes[-5] + 1e-6)

        # F. Session / Time
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(c_curr.timestamp, tz=timezone.utc)
        hour = float(dt.hour)
        day_of_week = float(dt.weekday())

        # G. Activity Burst
        vol_burst = float(c_curr.volume) / (float(np.mean([c.volume for c in candles[idx-10:idx]])) + 1e-6)

        return {
            "mom_ret_1": ret_1,
            "mom_ret_5": ret_5,
            "mom_ret_15": ret_15,
            "mom_accel": accel,
            "vol_atr_14": atr_14,
            "vol_realized": realized_vol,
            "vol_ratio": vol_ratio,
            "struct_range_pos": range_pos,
            "struct_dist_high": dist_high,
            "liq_dist_vwap": dist_vwap,
            "trend_dev_mean": dev_mean,
            "trend_ma_slope": ma_slope,
            "time_hour": hour,
            "time_day_of_week": day_of_week,
            "activity_vol_burst": vol_burst
        }
