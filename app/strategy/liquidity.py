from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum
from app.strategy.structure import SwingPoint, PointType


class LiquiditySide(str, Enum):
    BUYSIDE = "BUYSIDE"   # Buy-side liquidity (above highs)
    SELLSIDE = "SELLSIDE" # Sell-side liquidity (below lows)

class LiquidityType(str, Enum):
    PDH = "PDH"  # Previous Day High
    PDL = "PDL"  # Previous Day Low
    PWH = "PWH"  # Previous Week High
    PWL = "PWL"  # Previous Week Low
    EQH = "EQH"  # Equal Highs
    EQL = "EQL"  # Equal Lows
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    SESSION_HIGH = "SESSION_HIGH"
    SESSION_LOW = "SESSION_LOW"

@dataclass
class LiquidityLevel:
    level_type: str
    side: str
    price: float
    timestamp: str
    strength: float  # 1.0 = standard, 2.0 = double touch/EQH, 3.0+ = confluent
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class LiquidityEngine:
    """Deterministic Liquidity Engine identifying Buy-Side and Sell-Side liquidity pools."""

    def __init__(self, eqh_eql_tolerance_pips: float = 2.0):
        self.eqh_eql_tolerance_pips = eqh_eql_tolerance_pips

    def detect_pdh_pdl(self, candles: List[Dict[str, Any]]) -> List[LiquidityLevel]:
        """Detects Previous Day High (PDH) and Previous Day Low (PDL)."""
        if not candles:
            return []

        # Group candles by UTC calendar date
        days: Dict[str, List[Dict[str, Any]]] = {}
        for c in candles:
            dt = datetime.fromisoformat(c["timestamp"])
            day_str = dt.strftime("%Y-%m-%d")
            if day_str not in days:
                days[day_str] = []
            days[day_str].append(c)

        sorted_days = sorted(days.keys())
        if len(sorted_days) < 2:
            return []

        # Previous completed day is second to last in sorted dates
        prev_day_str = sorted_days[-2]
        day_candles = days[prev_day_str]

        pdh = max(c["high"] for c in day_candles)
        pdl = min(c["low"] for c in day_candles)
        pdh_candle = next(c for c in day_candles if c["high"] == pdh)
        pdl_candle = next(c for c in day_candles if c["low"] == pdl)

        return [
            LiquidityLevel(
                level_type=LiquidityType.PDH.value,
                side=LiquiditySide.BUYSIDE.value,
                price=pdh,
                timestamp=pdh_candle["timestamp"],
                strength=2.0,
                source=f"Previous Day ({prev_day_str}) High"
            ),
            LiquidityLevel(
                level_type=LiquidityType.PDL.value,
                side=LiquiditySide.SELLSIDE.value,
                price=pdl,
                timestamp=pdl_candle["timestamp"],
                strength=2.0,
                source=f"Previous Day ({prev_day_str}) Low"
            )
        ]

    def detect_equal_highs_lows(
        self, swing_points: List[SwingPoint], point_size: float = 0.01
    ) -> List[LiquidityLevel]:
        """Detects Equal Highs (EQH) and Equal Lows (EQL) within configurable pips tolerance."""
        levels: List[LiquidityLevel] = []
        tolerance = self.eqh_eql_tolerance_pips * point_size * 10.0 if point_size < 0.001 else self.eqh_eql_tolerance_pips * point_size

        highs = [p for p in swing_points if p.point_type == PointType.SWING_HIGH.value]
        lows = [p for p in swing_points if p.point_type == PointType.SWING_LOW.value]

        # EQH Check
        for i in range(len(highs)):
            for j in range(i + 1, len(highs)):
                h1, h2 = highs[i], highs[j]
                if abs(h1.price - h2.price) <= tolerance:
                    levels.append(
                        LiquidityLevel(
                            level_type=LiquidityType.EQH.value,
                            side=LiquiditySide.BUYSIDE.value,
                            price=max(h1.price, h2.price),
                            timestamp=h2.timestamp,
                            strength=3.0,
                            source=f"Equal Highs between idx {h1.index} and idx {h2.index}"
                        )
                    )

        # EQL Check
        for i in range(len(lows)):
            for j in range(i + 1, len(lows)):
                l1, l2 = lows[i], lows[j]
                if abs(l1.price - l2.price) <= tolerance:
                    levels.append(
                        LiquidityLevel(
                            level_type=LiquidityType.EQL.value,
                            side=LiquiditySide.SELLSIDE.value,
                            price=min(l1.price, l2.price),
                            timestamp=l2.timestamp,
                            strength=3.0,
                            source=f"Equal Lows between idx {l1.index} and idx {l2.index}"
                        )
                    )

        return levels

    def detect_session_highs_lows(self, candles: List[Dict[str, Any]]) -> List[LiquidityLevel]:
        """Detects Session Highs and Lows for Asian, London, and NY sessions."""
        if not candles:
            return []

        # Session UTC hours definition
        session_hours = {
            "ASIA": (0, 7),
            "LONDON": (7, 13),
            "NY": (13, 21),
        }

        levels: List[LiquidityLevel] = []

        for name, (start_h, end_h) in session_hours.items():
            session_candles = []
            for c in candles:
                dt = datetime.fromisoformat(c["timestamp"])
                if start_h <= dt.hour < end_h:
                    session_candles.append(c)

            if session_candles:
                sh = max(c["high"] for c in session_candles)
                sl = min(c["low"] for c in session_candles)
                sh_c = next(c for c in session_candles if c["high"] == sh)
                sl_c = next(c for c in session_candles if c["low"] == sl)

                levels.append(
                    LiquidityLevel(
                        level_type=LiquidityType.SESSION_HIGH.value,
                        side=LiquiditySide.BUYSIDE.value,
                        price=sh,
                        timestamp=sh_c["timestamp"],
                        strength=1.5,
                        source=f"{name} Session High"
                    )
                )
                levels.append(
                    LiquidityLevel(
                        level_type=LiquidityType.SESSION_LOW.value,
                        side=LiquiditySide.SELLSIDE.value,
                        price=sl,
                        timestamp=sl_c["timestamp"],
                        strength=1.5,
                        source=f"{name} Session Low"
                    )
                )

        return levels

    def get_all_liquidity_levels(
        self,
        candles: List[Dict[str, Any]],
        swing_points: List[SwingPoint],
        point_size: float = 0.01
    ) -> List[LiquidityLevel]:
        """Consolidates all buy-side and sell-side liquidity pools."""
        levels: List[LiquidityLevel] = []

        # 1. PDH / PDL
        levels.extend(self.detect_pdh_pdl(candles))

        # 2. EQH / EQL
        levels.extend(self.detect_equal_highs_lows(swing_points, point_size))

        # 3. Session Highs / Lows
        levels.extend(self.detect_session_highs_lows(candles))

        # 4. Recent Swing Highs / Lows
        for sp in swing_points[-4:]:  # last 4 swing points
            side = LiquiditySide.BUYSIDE.value if sp.point_type == PointType.SWING_HIGH.value else LiquiditySide.SELLSIDE.value
            ltype = LiquidityType.SWING_HIGH.value if sp.point_type == PointType.SWING_HIGH.value else LiquidityType.SWING_LOW.value
            levels.append(
                LiquidityLevel(
                    level_type=ltype,
                    side=side,
                    price=sp.price,
                    timestamp=sp.timestamp,
                    strength=1.0,
                    source=f"Swing {sp.point_type} at idx {sp.index}"
                )
            )

        return levels
