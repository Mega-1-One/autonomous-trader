from dataclasses import dataclass
from typing import List, Dict, Any

from app.research.common.splits import chronological_split_indices
from app.research.dataset import SignalResearchObservation
from app.research.calibration import ProbabilityCalibrator, CalibrationModelResult

@dataclass
class WalkForwardCalibrationReport:
    total_observations: int
    train_count: int
    validation_count: int
    out_of_sample_count: int
    train_result: CalibrationModelResult
    validation_result: CalibrationModelResult
    out_of_sample_result: CalibrationModelResult
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_observations": self.total_observations,
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "out_of_sample_count": self.out_of_sample_count,
            "train_result": self.train_result.to_dict(),
            "validation_result": self.validation_result.to_dict(),
            "out_of_sample_result": self.out_of_sample_result.to_dict(),
            "summary": self.summary
        }

class WalkForwardCalibrator:
    """Splits research observations into TRAIN (60%), VALIDATION (20%), and OUT-OF-SAMPLE (20%)."""

    def run_split(self, observations: List[SignalResearchObservation]) -> WalkForwardCalibrationReport:
        n = len(observations)
        if n < 50:
            calibrator = ProbabilityCalibrator()
            empty_res = calibrator.fit_and_evaluate([])
            return WalkForwardCalibrationReport(
                total_observations=n,
                train_count=0,
                validation_count=0,
                out_of_sample_count=0,
                train_result=empty_res,
                validation_result=empty_res,
                out_of_sample_result=empty_res,
                summary=f"INSUFFICIENT DATA: Total observations ({n}) below minimum threshold (50)"
            )

        split1, split2 = chronological_split_indices(n)

        train_obs = observations[:split1]
        val_obs = observations[split1:split2]
        oos_obs = observations[split2:]

        calibrator = ProbabilityCalibrator()
        train_res = calibrator.fit_and_evaluate(train_obs)
        val_res = calibrator.fit_and_evaluate(val_obs)
        oos_res = calibrator.fit_and_evaluate(oos_obs)

        summary = f"Walk-Forward Calibration Complete: Train N={len(train_obs)}, Val N={len(val_obs)}, OOS N={len(oos_obs)}. OOS Brier Score: {oos_res.brier_score:.4f}"

        return WalkForwardCalibrationReport(
            total_observations=n,
            train_count=len(train_obs),
            validation_count=len(val_obs),
            out_of_sample_count=len(oos_obs),
            train_result=train_res,
            validation_result=val_res,
            out_of_sample_result=oos_res,
            summary=summary
        )
