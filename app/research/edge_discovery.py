from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple
import numpy as np

from app.research.dataset import SignalResearchObservation

@dataclass
class DecileAnalysisResult:
    decile: str
    sample_count: int
    raw_positive_rate: float
    avg_mfe_pips: float
    avg_mae_pips: float
    avg_net_r: float
    avg_transaction_cost_dollars: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class BaselineComparisonResult:
    train_baseline_brier: float
    train_model_brier: float
    val_baseline_brier: float
    val_model_brier: float
    oos_baseline_brier: float
    oos_model_brier: float
    oos_baseline_log_loss: float
    oos_model_log_loss: float
    outperforms_baseline: bool
    brier_improvement_percent: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class EdgeDiscoveryEngine:
    """Phase 19 Engine performing Baseline Comparison, Decile Monotonicity, and Feature Importance Analysis."""

    def evaluate_baseline_comparison(
        self,
        train_obs: List[SignalResearchObservation],
        val_obs: List[SignalResearchObservation],
        oos_obs: List[SignalResearchObservation],
        calibrated_model_func
    ) -> BaselineComparisonResult:
        def get_labels(obs_list):
            return np.array([1.0 if (o.net_realized_r is not None and o.net_realized_r > 0) else 0.0 for o in obs_list])

        y_train = get_labels(train_obs)
        y_val = get_labels(val_obs)
        y_oos = get_labels(oos_obs)

        base_p = float(np.mean(y_train)) if len(y_train) > 0 else 0.5

        # Brier scores
        tr_base_brier = float(np.mean((base_p - y_train) ** 2)) if len(y_train) > 0 else 1.0
        val_base_brier = float(np.mean((base_p - y_val) ** 2)) if len(y_val) > 0 else 1.0
        oos_base_brier = float(np.mean((base_p - y_oos) ** 2)) if len(y_oos) > 0 else 1.0

        # Model predictions
        tr_preds = np.array([calibrated_model_func(o.opportunity_score) for o in train_obs]) if len(train_obs) > 0 else np.array([])
        val_preds = np.array([calibrated_model_func(o.opportunity_score) for o in val_obs]) if len(val_obs) > 0 else np.array([])
        oos_preds = np.array([calibrated_model_func(o.opportunity_score) for o in oos_obs]) if len(oos_obs) > 0 else np.array([])

        tr_model_brier = float(np.mean((tr_preds - y_train) ** 2)) if len(y_train) > 0 else 1.0
        val_model_brier = float(np.mean((val_preds - y_val) ** 2)) if len(y_val) > 0 else 1.0
        oos_model_brier = float(np.mean((oos_preds - y_oos) ** 2)) if len(y_oos) > 0 else 1.0

        eps = 1e-15
        oos_base_log_loss = float(-np.mean(y_oos * np.log(np.clip(base_p, eps, 1-eps)) + (1 - y_oos) * np.log(np.clip(1-base_p, eps, 1-eps)))) if len(y_oos) > 0 else 1.0
        oos_model_log_loss = float(-np.mean(y_oos * np.log(np.clip(oos_preds, eps, 1-eps)) + (1 - y_oos) * np.log(np.clip(1-oos_preds, eps, 1-eps)))) if len(y_oos) > 0 else 1.0

        improvement = ((oos_base_brier - oos_model_brier) / max(1e-6, oos_base_brier)) * 100.0
        outperforms = (oos_model_brier < oos_base_brier)

        return BaselineComparisonResult(
            train_baseline_brier=round(tr_base_brier, 4),
            train_model_brier=round(tr_model_brier, 4),
            val_baseline_brier=round(val_base_brier, 4),
            val_model_brier=round(val_model_brier, 4),
            oos_baseline_brier=round(oos_base_brier, 4),
            oos_model_brier=round(oos_model_brier, 4),
            oos_baseline_log_loss=round(oos_base_log_loss, 4),
            oos_model_log_loss=round(oos_model_log_loss, 4),
            outperforms_baseline=outperforms,
            brier_improvement_percent=round(improvement, 2)
        )

    def analyze_opportunity_deciles(self, observations: List[SignalResearchObservation]) -> List[DecileAnalysisResult]:
        if not observations:
            return []

        sorted_obs = sorted(observations, key=lambda x: x.opportunity_score)
        n = len(sorted_obs)
        chunk = max(1, n // 10)

        results = []
        for i in range(10):
            start = i * chunk
            end = n if i == 9 else (i + 1) * chunk
            decile_obs = sorted_obs[start:end]
            if not decile_obs:
                continue

            dec_str = f"Decile {i+1} ({i*10}-{(i+1)*10}%)"
            n_d = len(decile_obs)
            pos_cnt = sum(1 for o in decile_obs if o.net_realized_r is not None and o.net_realized_r > 0)
            raw_pos = round(pos_cnt / n_d, 2)

            mfes = [o.outcomes_by_horizon["30s"]["mfe_pips"] for o in decile_obs if o.outcomes_by_horizon]
            maes = [o.outcomes_by_horizon["30s"]["mae_pips"] for o in decile_obs if o.outcomes_by_horizon]
            net_rs = [o.net_realized_r for o in decile_obs if o.net_realized_r is not None]
            costs = [o.estimated_total_cost_dollars for o in decile_obs]

            results.append(DecileAnalysisResult(
                decile=dec_str,
                sample_count=n_d,
                raw_positive_rate=raw_pos,
                avg_mfe_pips=round(float(np.mean(mfes)), 2) if mfes else 0.0,
                avg_mae_pips=round(float(np.mean(maes)), 2) if maes else 0.0,
                avg_net_r=round(float(np.mean(net_rs)), 2) if net_rs else 0.0,
                avg_transaction_cost_dollars=round(float(np.mean(costs)), 2) if costs else 0.0
            ))

        return results
