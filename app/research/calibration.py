from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple
import numpy as np

from app.research.dataset import SignalResearchObservation

@dataclass
class BucketCalibrationStats:
    score_range: str
    sample_count: int
    raw_positive_rate: float
    calibrated_probability: float
    avg_mfe_pips: float
    avg_mae_pips: float
    avg_net_r: float
    median_net_r: float
    status: str                         # "VALID" or "INSUFFICIENT_DATA"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CalibrationModelResult:
    brier_score: float
    log_loss: float
    platt_slope: float
    platt_intercept: float
    bucket_stats: List[BucketCalibrationStats]
    calibration_status: str             # "CALIBRATED", "INSUFFICIENT_DATA"
    reliability_summary: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["bucket_stats"] = [b.to_dict() for b in self.bucket_stats]
        return d

class ProbabilityCalibrator:
    """Platt Scaling probability calibration & Brier score evaluation engine."""

    SCORE_BUCKETS = [
        (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.75),
        (0.75, 0.80), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.00)
    ]
    MIN_SAMPLE_THRESHOLD = 30

    def fit_and_evaluate(self, train_obs: List[SignalResearchObservation]) -> CalibrationModelResult:
        if len(train_obs) < self.MIN_SAMPLE_THRESHOLD:
            return CalibrationModelResult(
                brier_score=1.0,
                log_loss=1.0,
                platt_slope=0.0,
                platt_intercept=0.0,
                bucket_stats=[],
                calibration_status="INSUFFICIENT_DATA",
                reliability_summary=f"Insufficient training observations (N={len(train_obs)} < {self.MIN_SAMPLE_THRESHOLD})"
            )

        scores = np.array([o.opportunity_score for o in train_obs])
        labels = np.array([1.0 if (o.net_realized_r is not None and o.net_realized_r > 0) else 0.0 for o in train_obs])

        # 1. Simple Logistic Fit (Platt Scaling approximation: z = a*score + b)
        mean_s = np.mean(scores)
        mean_y = np.mean(labels)
        cov_sy = np.cov(scores, labels)[0][1] if len(scores) > 1 else 0.0
        var_s = np.var(scores) if len(scores) > 1 else 1.0

        slope = float(cov_sy / var_s) if var_s > 1e-6 else 0.0
        intercept = float(mean_y - slope * mean_s)

        def predict_prob(s: float) -> float:
            z = slope * s + intercept
            return float(1.0 / (1.0 + np.exp(-np.clip(z, -5.0, 5.0))))

        # 2. Evaluate Brier Score & Log Loss
        probs = np.array([predict_prob(s) for s in scores])
        brier = float(np.mean((probs - labels) ** 2))

        eps = 1e-15
        clipped_probs = np.clip(probs, eps, 1.0 - eps)
        log_loss = float(-np.mean(labels * np.log(clipped_probs) + (1.0 - labels) * np.log(1.0 - clipped_probs)))

        # 3. Bucket Statistics
        bucket_results = []
        for low, high in self.SCORE_BUCKETS:
            bucket_obs = [o for o in train_obs if low <= o.opportunity_score < high]
            n_b = len(bucket_obs)
            range_str = f"{low:.2f}–{high:.2f}"

            if n_b < 10:
                bucket_results.append(BucketCalibrationStats(
                    score_range=range_str,
                    sample_count=n_b,
                    raw_positive_rate=0.0,
                    calibrated_probability=round(predict_prob((low + high) / 2.0), 2),
                    avg_mfe_pips=0.0,
                    avg_mae_pips=0.0,
                    avg_net_r=0.0,
                    median_net_r=0.0,
                    status="INSUFFICIENT_DATA"
                ))
                continue

            pos_cnt = sum(1 for o in bucket_obs if o.net_realized_r is not None and o.net_realized_r > 0)
            raw_pos_rate = round(pos_cnt / n_b, 2)
            cal_p = round(predict_prob((low + high) / 2.0), 2)

            mfes = [o.outcomes_by_horizon["30s"]["mfe_pips"] for o in bucket_obs if o.outcomes_by_horizon]
            maes = [o.outcomes_by_horizon["30s"]["mae_pips"] for o in bucket_obs if o.outcomes_by_horizon]
            net_rs = [o.net_realized_r for o in bucket_obs if o.net_realized_r is not None]

            avg_mfe = round(float(np.mean(mfes)), 2) if mfes else 0.0
            avg_mae = round(float(np.mean(maes)), 2) if maes else 0.0
            avg_r = round(float(np.mean(net_rs)), 2) if net_rs else 0.0
            med_r = round(float(np.median(net_rs)), 2) if net_rs else 0.0

            bucket_results.append(BucketCalibrationStats(
                score_range=range_str,
                sample_count=n_b,
                raw_positive_rate=raw_pos_rate,
                calibrated_probability=cal_p,
                avg_mfe_pips=avg_mfe,
                avg_mae_pips=avg_mae,
                avg_net_r=avg_r,
                median_net_r=med_r,
                status="VALID"
            ))

        return CalibrationModelResult(
            brier_score=round(brier, 4),
            log_loss=round(log_loss, 4),
            platt_slope=round(slope, 4),
            platt_intercept=round(intercept, 4),
            bucket_stats=bucket_results,
            calibration_status="CALIBRATED",
            reliability_summary=f"Platt Scaling Calibrated on N={len(train_obs)} observations (Brier: {brier:.4f})"
        )
