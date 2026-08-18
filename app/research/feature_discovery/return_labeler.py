from typing import List, Dict
from app.context.timeframe_engine import Candle

class ReturnLabeler:
    """Computes future forward returns for 1M, 5M, 15M, 30M, 1H, and 4H horizons."""

    HORIZONS = {
        "1M": 1,
        "5M": 5,
        "15M": 15,
        "30M": 30,
        "1H": 60,
        "4H": 240
    }

    def compute_forward_returns(self, candles: List[Candle], idx: int) -> Dict[str, float]:
        labels = {}
        c_curr = candles[idx]
        entry_p = c_curr.close

        for h_name, steps in self.HORIZONS.items():
            target_idx = idx + steps
            if target_idx < len(candles):
                exit_p = candles[target_idx].close
                ret = (exit_p - entry_p) / entry_p if entry_p > 0 else 0.0
                labels[f"fwd_ret_{h_name}"] = ret
            else:
                labels[f"fwd_ret_{h_name}"] = 0.0

        return labels
