import numpy as np
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

@dataclass
class FeatureScoringResult:
    feature_name: str
    horizon: str
    instrument: str
    sample_count: int
    pearson_r: float
    raw_p_value: float
    fdr_adjusted_p_value: float
    is_fdr_significant: bool
    train_ic: float
    val_ic: float
    oos_ic: float
    oos_net_expectancy: float
    classification: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class FeatureStatisticalScorer:
    """Computes Information Coefficient (IC), Pearson Correlation, FDR p-value correction, and OOS Expectancy."""

    def compute_fdr_correction(self, raw_p_values: List[float], alpha: float = 0.05) -> Tuple[List[float], List[bool]]:
        """Benjamini-Hochberg False Discovery Rate (FDR) procedure (shared impl)."""
        from app.research.common.statistical_tests import compute_fdr_correction
        return compute_fdr_correction(raw_p_values, alpha=alpha)

    def evaluate_feature(
        self,
        feature_name: str,
        horizon: str,
        symbol: str,
        feature_vals: np.ndarray,
        returns: np.ndarray
    ) -> FeatureScoringResult:
        n = len(feature_vals)
        if n < 50 or np.std(feature_vals) == 0 or np.std(returns) == 0:
            return FeatureScoringResult(
                feature_name=feature_name, horizon=horizon, instrument=symbol,
                sample_count=n, pearson_r=0.0, raw_p_value=1.0, fdr_adjusted_p_value=1.0,
                is_fdr_significant=False, train_ic=0.0, val_ic=0.0, oos_ic=0.0,
                oos_net_expectancy=0.0, classification="D = No predictive edge"
            )

        r = float(np.corrcoef(feature_vals, returns)[0, 1])
        # Approximate p-value calculation
        t_stat = r * np.sqrt((n - 2) / max(1e-6, 1.0 - r**2))
        raw_p = float(2.0 * (1.0 - 0.5 * (1.0 + np.tanh(abs(t_stat) / np.sqrt(2.0)))))

        # Train (60%), Val (20%), OOS (20%)
        i_tr = int(n * 0.6)
        i_val = int(n * 0.8)

        tr_r = float(np.corrcoef(feature_vals[:i_tr], returns[:i_tr])[0, 1]) if i_tr > 10 else 0.0
        val_r = float(np.corrcoef(feature_vals[i_tr:i_val], returns[i_tr:i_val])[0, 1]) if (i_val - i_tr) > 10 else 0.0
        oos_r = float(np.corrcoef(feature_vals[i_val:], returns[i_val:])[0, 1]) if (n - i_val) > 10 else 0.0

        # Cost-adjusted OOS Expectancy estimate
        cost_drag = 0.0003
        oos_net = round(abs(oos_r) * float(np.mean(np.abs(returns[i_val:]))) - cost_drag, 5)

        classification = "D = No predictive edge"
        if oos_r > 0.03 and oos_net > 0 and n >= 100:
            classification = "A = Robust predictive edge"
        elif abs(oos_r) > 0.01:
            classification = "B = Promising but insufficient evidence"

        return FeatureScoringResult(
            feature_name=feature_name,
            horizon=horizon,
            instrument=symbol,
            sample_count=n,
            pearson_r=round(r, 4),
            raw_p_value=round(raw_p, 5),
            fdr_adjusted_p_value=round(raw_p, 5),
            is_fdr_significant=False,
            train_ic=round(tr_r, 4),
            val_ic=round(val_r, 4),
            oos_ic=round(oos_r, 4),
            oos_net_expectancy=oos_net,
            classification=classification
        )
