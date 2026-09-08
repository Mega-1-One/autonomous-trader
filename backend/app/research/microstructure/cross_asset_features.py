import numpy as np
from typing import List, Dict
from app.context.timeframe_engine import Candle

class CrossAssetFeatureGenerator:
    """Generates cross-asset lead/lag momentum, correlation, and risk divergence features."""

    def generate_cross_asset_features(
        self,
        asset_candles: Dict[str, List[Candle]],
        target_symbol: str,
        idx: int
    ) -> Dict[str, float]:
        target_series = asset_candles.get(target_symbol, [])
        if not target_series or idx < 30 or idx >= len(target_series):
            return {}

        c_curr = target_series[idx]

        # 1. Lead/Lag Relative Momentum (e.g. NAS100 ↔ XAUUSD ↔ EURUSD)
        lead_symbol = "NAS100" if target_symbol != "NAS100" else "XAUUSD"
        lead_series = asset_candles.get(lead_symbol, [])

        if lead_series and idx < len(lead_series):
            lead_ret = (lead_series[idx].close - lead_series[idx-5].close) / (lead_series[idx-5].close + 1e-6)
            target_ret = (c_curr.close - target_series[idx-5].close) / (target_series[idx-5].close + 1e-6)
            momentum_divergence = lead_ret - target_ret
        else:
            lead_ret = 0.0
            momentum_divergence = 0.0

        # 2. Contemporaneous Correlation over 20 periods
        if lead_series and idx >= 20 and idx < len(lead_series):
            t_closes = [c.close for c in target_series[idx-20:idx+1]]
            l_closes = [c.close for c in lead_series[idx-20:idx+1]]
            corr = float(np.corrcoef(t_closes, l_closes)[0, 1]) if len(t_closes) == len(l_closes) else 0.0
        else:
            corr = 0.0

        return {
            "cross_lead_return": lead_ret,
            "cross_momentum_divergence": momentum_divergence,
            "cross_asset_correlation": corr
        }
