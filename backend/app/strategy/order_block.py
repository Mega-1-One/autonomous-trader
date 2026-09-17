from dataclasses import dataclass, asdict
from typing import Any, Dict, List
from app.strategy.displacement import DisplacementCandle
from app.strategy.structure import StructureEvent

@dataclass
class OrderBlock:
    ob_type: str  # "BULLISH" or "BEARISH"
    candle_index: int
    timestamp: str
    high: float
    low: float
    open: float
    close: float
    mitigated: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class OrderBlockEngine:
    """Quantitative Order Block (OB) Identification Engine."""

    def detect_order_blocks(
        self,
        candles: List[Dict[str, Any]],
        displacements: List[DisplacementCandle],
        structure_events: List[StructureEvent]
    ) -> List[OrderBlock]:
        """Detects Bullish and Bearish Order Blocks associated with displacement and structure breaks."""
        obs: List[OrderBlock] = []
        if len(candles) < 3 or not displacements:
            return obs

        disp_indices = {d.index: d for d in displacements}
        break_trigger_indices = {e.trigger_candle_index: e for e in structure_events}

        for disp_idx, disp in disp_indices.items():
            if disp_idx == 0:
                continue

            # Check if there is a structure break near/after displacement
            has_break = any(
                abs(b_idx - disp_idx) <= 3 for b_idx in break_trigger_indices.keys()
            ) or (len(structure_events) > 0)

            if not has_break:
                continue

            # Bullish OB: last bearish candle prior to bullish displacement
            if disp.direction == "BULLISH":
                for lookback in range(disp_idx - 1, max(-1, disp_idx - 5), -1):
                    c = candles[lookback]
                    if c["close"] <= c["open"]:  # Bearish candle
                        obs.append(
                            OrderBlock(
                                ob_type="BULLISH",
                                candle_index=lookback,
                                timestamp=c["timestamp"],
                                high=c["high"],
                                low=c["low"],
                                open=c["open"],
                                close=c["close"],
                                mitigated=self._check_mitigation("BULLISH", c["low"], candles[disp_idx + 1:])
                            )
                        )
                        break

            # Bearish OB: last bullish candle prior to bearish displacement
            elif disp.direction == "BEARISH":
                for lookback in range(disp_idx - 1, max(-1, disp_idx - 5), -1):
                    c = candles[lookback]
                    if c["close"] >= c["open"]:  # Bullish candle
                        obs.append(
                            OrderBlock(
                                ob_type="BEARISH",
                                candle_index=lookback,
                                timestamp=c["timestamp"],
                                high=c["high"],
                                low=c["low"],
                                open=c["open"],
                                close=c["close"],
                                mitigated=self._check_mitigation("BEARISH", c["high"], candles[disp_idx + 1:])
                            )
                        )
                        break

        return obs

    def _check_mitigation(self, ob_type: str, boundary: float, subsequent: List[Dict[str, Any]]) -> bool:
        """Determines if order block has been mitigated by price retracing into it."""
        for c in subsequent:
            if ob_type == "BULLISH" and c["low"] <= boundary:
                return True
            elif ob_type == "BEARISH" and c["high"] >= boundary:
                return True
        return False
