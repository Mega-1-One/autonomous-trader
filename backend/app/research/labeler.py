from typing import List, Dict, Any, Optional
import numpy as np

from app.research.dataset import SignalResearchObservation
from app.scalper.instrument import InstrumentSpecification

class OutcomeLabeler:
    """Post-hoc outcome labeling engine computing MFE, MAE, and cost-adjusted Net R across 10 horizons."""

    HORIZONS_SEC = [0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0]
    HORIZON_NAMES = ["100ms", "250ms", "500ms", "1s", "2s", "5s", "10s", "15s", "30s", "60s"]

    def label_observation(
        self,
        obs: SignalResearchObservation,
        future_ticks: List[Dict[str, Any]],
        spec: InstrumentSpecification
    ) -> SignalResearchObservation:
        if not future_ticks:
            return obs

        entry_t = obs.timestamp
        entry_p = obs.entry_reference
        is_buy = (obs.direction == "BUY")
        pip_unit = spec.pip_size

        horizon_outcomes = {}

        # 1. Compute MFE & MAE per Horizon
        for h_sec, h_name in zip(self.HORIZONS_SEC, self.HORIZON_NAMES):
            ticks_in_h = [t for t in future_ticks if (t["timestamp"] - entry_t) <= h_sec]
            if not ticks_in_h:
                horizon_outcomes[h_name] = {"mfe_pips": 0.0, "mae_pips": 0.0, "net_pips": 0.0}
                continue

            prices = [t["bid"] if is_buy else t["ask"] for t in ticks_in_h]
            diffs = [(p - entry_p) / pip_unit if is_buy else (entry_p - p) / pip_unit for p in prices]

            mfe = max(0.0, max(diffs))
            mae = max(0.0, abs(min(0.0, min(diffs))))
            net_diff = diffs[-1]

            horizon_outcomes[h_name] = {
                "mfe_pips": round(mfe, 2),
                "mae_pips": round(mae, 2),
                "net_pips": round(net_diff, 2)
            }

        # 2. Evaluate TP / SL First-Hit Order
        tp_hit = False
        sl_hit = False

        tp_pips = abs(obs.target_reference - entry_p) / pip_unit
        sl_pips = abs(entry_p - obs.stop_reference) / pip_unit

        for t in future_ticks:
            curr_p = t["bid"] if is_buy else t["ask"]
            fav_move = (curr_p - entry_p) / pip_unit if is_buy else (entry_p - curr_p) / pip_unit
            adv_move = (entry_p - curr_p) / pip_unit if is_buy else (curr_p - entry_p) / pip_unit

            if fav_move >= tp_pips:
                tp_hit = True
                break
            if adv_move >= sl_pips:
                sl_hit = True
                break

        # 3. Calculate Cost-Adjusted Net R
        total_cost_pips = obs.estimated_total_cost_dollars / (100.0 * 0.05 * pip_unit) if pip_unit > 0 else 0.0
        final_h = horizon_outcomes.get("30s", {"net_pips": 0.0})
        net_move_pips = final_h["net_pips"] - total_cost_pips
        net_r = round(net_move_pips / max(1.0, sl_pips), 2)

        obs.outcomes_by_horizon = horizon_outcomes
        obs.tp_hit_before_sl = tp_hit
        obs.sl_hit_before_tp = sl_hit
        obs.net_realized_r = net_r
        return obs
