from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional

@dataclass
class AnalysisResult:
    analyzer_name: str
    symbol: str
    timestamp: float
    direction: str            # "BUY", "SELL", or "NEUTRAL"
    confidence: float         # 0.0 to 1.0
    strength: float           # Signal magnitude (0.0 to 1.0)
    features: Dict[str, Any]  # Raw indicator/microstructure metrics
    reasons: List[str]        # Human-readable evidence audit trail
    valid_until: float        # Unix timestamp validity expiration

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
