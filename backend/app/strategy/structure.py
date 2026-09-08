from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from enum import Enum

class TrendRegime(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"

class PointType(str, Enum):
    SWING_HIGH = "HIGH"
    SWING_LOW = "LOW"

class StructureEventType(str, Enum):
    BOS = "BOS" # Break of Structure (Continuation)
    MSS = "MSS" # Market Structure Shift / CHOCH (Reversal)

@dataclass
class SwingPoint:
    index: int
    timestamp: str
    point_type: str  # "HIGH" or "LOW"
    price: float
    label: Optional[str] = None  # "HH", "HL", "LH", "LL"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class StructureEvent:
    event_type: str  # "BOS" or "MSS"
    direction: str  # "BULLISH" or "BEARISH"
    broken_level: float
    broken_point_index: int
    trigger_candle_index: int
    timestamp: str
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class StructureAnalysisResult:
    trend: str  # BULLISH, BEARISH, RANGING
    swing_points: List[SwingPoint]
    events: List[StructureEvent]
    latest_bos: Optional[StructureEvent]
    latest_mss: Optional[StructureEvent]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trend": self.trend,
            "swing_points": [p.to_dict() for p in self.swing_points],
            "events": [e.to_dict() for e in self.events],
            "latest_bos": self.latest_bos.to_dict() if self.latest_bos else None,
            "latest_mss": self.latest_mss.to_dict() if self.latest_mss else None,
        }

class StructureEngine:
    """Deterministic Market Structure Engine for identifying Swing Points, HH/HL/LH/LL, BOS, and MSS/CHOCH."""

    def __init__(self, swing_lookback: int = 3, confirm_on_close: bool = True):
        self.swing_lookback = swing_lookback
        self.confirm_on_close = confirm_on_close

    def detect_swing_points(self, candles: List[Dict[str, Any]]) -> List[SwingPoint]:
        """Detects Swing Highs and Swing Lows deterministically using configured lookback window."""
        n = len(candles)
        swing_points: List[SwingPoint] = []

        if n < (2 * self.swing_lookback + 1):
            return swing_points

        lb = self.swing_lookback

        for i in range(lb, n - lb):
            curr_high = candles[i]["high"]
            curr_low = candles[i]["low"]

            # Check Swing High
            is_high = True
            for k in range(1, lb + 1):
                if candles[i - k]["high"] >= curr_high or candles[i + k]["high"] > curr_high:
                    is_high = False
                    break

            if is_high:
                swing_points.append(
                    SwingPoint(
                        index=i,
                        timestamp=candles[i]["timestamp"],
                        point_type=PointType.SWING_HIGH.value,
                        price=curr_high,
                    )
                )

            # Check Swing Low
            is_low = True
            for k in range(1, lb + 1):
                if candles[i - k]["low"] <= curr_low or candles[i + k]["low"] < curr_low:
                    is_low = False
                    break

            if is_low:
                swing_points.append(
                    SwingPoint(
                        index=i,
                        timestamp=candles[i]["timestamp"],
                        point_type=PointType.SWING_LOW.value,
                        price=curr_low,
                    )
                )

        # Sort swing points chronologically by candle index
        swing_points.sort(key=lambda x: x.index)
        return swing_points

    def label_swing_points(self, swing_points: List[SwingPoint]) -> None:
        """Labels swing points as HH (Higher High), HL (Higher Low), LH (Lower High), LL (Lower Low)."""
        last_high: Optional[float] = None
        last_low: Optional[float] = None

        for pt in swing_points:
            if pt.point_type == PointType.SWING_HIGH.value:
                if last_high is None:
                    pt.label = "HIGH"
                elif pt.price > last_high:
                    pt.label = "HH"
                else:
                    pt.label = "LH"
                last_high = pt.price
            elif pt.point_type == PointType.SWING_LOW.value:
                if last_low is None:
                    pt.label = "LOW"
                elif pt.price > last_low:
                    pt.label = "HL"
                else:
                    pt.label = "LL"
                last_low = pt.price

    def analyze_structure(self, candles: List[Dict[str, Any]]) -> StructureAnalysisResult:
        """Performs full market structure breakdown: Swing Points, Labels, BOS, MSS/CHOCH, and Trend Regime."""
        swing_points = self.detect_swing_points(candles)
        self.label_swing_points(swing_points)

        events: List[StructureEvent] = []
        current_trend: TrendRegime = TrendRegime.RANGING

        active_swing_high: Optional[SwingPoint] = None
        active_swing_low: Optional[SwingPoint] = None

        sp_idx = 0
        num_sp = len(swing_points)

        for i, candle in enumerate(candles):
            # Update active swing points as we move forward through candles
            while sp_idx < num_sp and swing_points[sp_idx].index <= i:
                sp = swing_points[sp_idx]
                if sp.point_type == PointType.SWING_HIGH.value:
                    active_swing_high = sp
                elif sp.point_type == PointType.SWING_LOW.value:
                    active_swing_low = sp
                sp_idx += 1

            check_price_high = candle["close"] if self.confirm_on_close else candle["high"]
            check_price_low = candle["close"] if self.confirm_on_close else candle["low"]

            # Bullish Break Check (above active swing high)
            if active_swing_high and check_price_high > active_swing_high.price:
                event_type = StructureEventType.BOS.value if current_trend == TrendRegime.BULLISH else StructureEventType.MSS.value
                current_trend = TrendRegime.BULLISH
                
                events.append(
                    StructureEvent(
                        event_type=event_type,
                        direction="BULLISH",
                        broken_level=active_swing_high.price,
                        broken_point_index=active_swing_high.index,
                        trigger_candle_index=i,
                        timestamp=candle["timestamp"],
                        description=f"Bullish {event_type} breaking Swing High at {active_swing_high.price}"
                    )
                )
                active_swing_high = None  # Consume broken swing high

            # Bearish Break Check (below active swing low)
            elif active_swing_low and check_price_low < active_swing_low.price:
                event_type = StructureEventType.BOS.value if current_trend == TrendRegime.BEARISH else StructureEventType.MSS.value
                current_trend = TrendRegime.BEARISH

                events.append(
                    StructureEvent(
                        event_type=event_type,
                        direction="BEARISH",
                        broken_level=active_swing_low.price,
                        broken_point_index=active_swing_low.index,
                        trigger_candle_index=i,
                        timestamp=candle["timestamp"],
                        description=f"Bearish {event_type} breaking Swing Low at {active_swing_low.price}"
                    )
                )
                active_swing_low = None  # Consume broken swing low

        latest_bos = next((e for e in reversed(events) if e.event_type == StructureEventType.BOS.value), None)
        latest_mss = next((e for e in reversed(events) if e.event_type == StructureEventType.MSS.value), None)

        return StructureAnalysisResult(
            trend=current_trend.value,
            swing_points=swing_points,
            events=events,
            latest_bos=latest_bos,
            latest_mss=latest_mss
        )
