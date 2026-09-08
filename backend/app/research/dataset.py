from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

@dataclass
class SignalResearchObservation:
    signal_id: str
    timestamp: float
    symbol: str
    direction: str                     # "BUY", "SELL"
    signal_type: str                   # "TRADED", "QUALIFIED", "REJECTED", "NEAR_MISS"
    regime: str
    strategy: str
    opportunity_score: float

    bullish_evidence: float
    bearish_evidence: float
    conflict_score: float

    technical_score: float
    structure_score: float
    liquidity_score: float
    momentum_score: float
    volatility_score: float
    session_score: float

    spread_pips: float
    estimated_slippage_pips: float
    estimated_commission_dollars: float
    estimated_total_cost_dollars: float

    entry_reference: float
    stop_reference: float
    target_reference: float

    ev_estimate_raw: float

    # Outcome Labels (Attached strictly post-hoc)
    outcomes_by_horizon: Optional[Dict[str, Dict[str, float]]] = None
    tp_hit_before_sl: Optional[bool] = None
    sl_hit_before_tp: Optional[bool] = None
    net_realized_r: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
