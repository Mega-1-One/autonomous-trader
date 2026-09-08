from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

@dataclass
class ScalpSignal:
    signal_id: str
    timestamp: float
    symbol: str
    direction: str            # "BUY", "SELL", or "NONE"
    status: str               # "APPROVED" or "REJECTED"
    confidence_score: float   # Deterministic score (0.0 to 1.0)
    entry_reference: float
    stop_reference: float
    target_reference: float
    spread: float
    momentum: float
    velocity: float
    volatility: float
    reasons: List[str]
    expiry_time: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
