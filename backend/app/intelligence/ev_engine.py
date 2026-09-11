from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

@dataclass
class ExpectedValueEstimate:
    win_probability_estimated: float
    loss_probability_estimated: float
    average_win_dollars: float
    average_loss_dollars: float
    transaction_cost_dollars: float
    expected_value_dollars: float
    calibration_status: str     # "CALIBRATED_VALID" or "INSUFFICIENT_DATA"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ExpectedValueEngine:
    """Expected Value Engine v2 calculating calibrated EV after transaction costs."""

    def calculate_ev(
        self,
        confidence_score: float,
        target_reward_dollars: float,
        stop_loss_dollars: float,
        transaction_cost_dollars: float,
        calibrated_prob: Optional[float] = None,
        observation_count: int = 0
    ) -> ExpectedValueEstimate:
        if observation_count < 30 or calibrated_prob is None:
            # Fallback estimation when sample size is insufficient
            p_win = round(min(0.70, max(0.40, confidence_score * 0.75)), 2)
            p_loss = round(1.0 - p_win, 2)
            status = "INSUFFICIENT_DATA"
        else:
            p_win = round(calibrated_prob, 2)
            p_loss = round(1.0 - p_win, 2)
            status = "CALIBRATED_VALID"

        raw_ev = (p_win * target_reward_dollars) - (p_loss * stop_loss_dollars)
        net_ev = round(raw_ev - transaction_cost_dollars, 2)

        return ExpectedValueEstimate(
            win_probability_estimated=p_win,
            loss_probability_estimated=p_loss,
            average_win_dollars=target_reward_dollars,
            average_loss_dollars=stop_loss_dollars,
            transaction_cost_dollars=transaction_cost_dollars,
            expected_value_dollars=net_ev,
            calibration_status=status
        )
