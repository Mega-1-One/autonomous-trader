from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from enum import Enum

class FVGType(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"

class MitigationStatus(str, Enum):
    UNMITIGATED = "UNMITIGATED"
    PARTIALLY_MITIGATED = "PARTIALLY_MITIGATED"
    FILLED = "FILLED"

@dataclass
class FairValueGap:
    fvg_type: str
    creation_index: int
    creation_timestamp: str
    timeframe: str
    upper_boundary: float
    lower_boundary: float
    gap_size: float
    mitigation_status: str
    fill_percentage: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class FVGEngine:
    """Fair Value Gap (FVG) Detection & Mitigation Tracking Engine."""

    def __init__(self, min_gap_size_pips: float = 0.5):
        self.min_gap_size_pips = min_gap_size_pips

    def detect_fvgs(
        self, candles: List[Dict[str, Any]], timeframe: str = "M5", point_size: float = 0.01
    ) -> List[FairValueGap]:
        """Detects 3-candle Fair Value Gaps and updates mitigation state across subsequent candles."""
        fvgs: List[FairValueGap] = []
        n = len(candles)
        if n < 3:
            return fvgs

        min_gap = self.min_gap_size_pips * point_size * 10.0 if point_size < 0.001 else self.min_gap_size_pips * point_size

        for i in range(2, n):
            c1 = candles[i - 2]
            c2 = candles[i - 1]
            c3 = candles[i]

            # Bullish FVG: Low of candle 3 > High of candle 1
            if c3["low"] > c1["high"]:
                gap_size = c3["low"] - c1["high"]
                if gap_size >= min_gap:
                    fvg = FairValueGap(
                        fvg_type=FVGType.BULLISH.value,
                        creation_index=i,
                        creation_timestamp=c3["timestamp"],
                        timeframe=timeframe,
                        upper_boundary=c3["low"],
                        lower_boundary=c1["high"],
                        gap_size=gap_size,
                        mitigation_status=MitigationStatus.UNMITIGATED.value,
                        fill_percentage=0.0
                    )
                    self._update_mitigation(fvg, candles[i + 1:])
                    fvgs.append(fvg)

            # Bearish FVG: High of candle 3 < Low of candle 1
            elif c3["high"] < c1["low"]:
                gap_size = c1["low"] - c3["high"]
                if gap_size >= min_gap:
                    fvg = FairValueGap(
                        fvg_type=FVGType.BEARISH.value,
                        creation_index=i,
                        creation_timestamp=c3["timestamp"],
                        timeframe=timeframe,
                        upper_boundary=c1["low"],
                        lower_boundary=c3["high"],
                        gap_size=gap_size,
                        mitigation_status=MitigationStatus.UNMITIGATED.value,
                        fill_percentage=0.0
                    )
                    self._update_mitigation(fvg, candles[i + 1:])
                    fvgs.append(fvg)

        return fvgs

    def _update_mitigation(self, fvg: FairValueGap, subsequent_candles: List[Dict[str, Any]]) -> None:
        """Evaluates subsequent price action to update FVG mitigation status and fill percentage."""
        if not subsequent_candles or fvg.gap_size <= 0:
            return

        max_penetration = 0.0

        for c in subsequent_candles:
            if fvg.fvg_type == FVGType.BULLISH.value:
                # Price retraces downwards into gap
                if c["low"] < fvg.upper_boundary:
                    penetration = fvg.upper_boundary - c["low"]
                    max_penetration = max(max_penetration, penetration)
            else:
                # Price retraces upwards into gap
                if c["high"] > fvg.lower_boundary:
                    penetration = c["high"] - fvg.lower_boundary
                    max_penetration = max(max_penetration, penetration)

        fill_pct = min(100.0, (max_penetration / fvg.gap_size) * 100.0)
        fvg.fill_percentage = round(fill_pct, 2)

        if fill_pct >= 100.0:
            fvg.mitigation_status = MitigationStatus.FILLED.value
        elif fill_pct > 0.0:
            fvg.mitigation_status = MitigationStatus.PARTIALLY_MITIGATED.value
        else:
            fvg.mitigation_status = MitigationStatus.UNMITIGATED.value
