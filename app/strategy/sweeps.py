from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
from app.strategy.liquidity import LiquidityLevel, LiquiditySide

@dataclass
class SweepEvent:
    sweep_type: str  # "BULLISH_SWEEP" or "BEARISH_SWEEP"
    liquidity_level_type: str
    liquidity_price: float
    sweep_extreme_price: float
    reclaim_close_price: float
    candle_index: int
    timestamp: str
    displacement_confirmed: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SweepEngine:
    """Objective Liquidity Sweep Detection Engine."""

    def __init__(self, sweep_threshold_pips: float = 1.0):
        self.sweep_threshold_pips = sweep_threshold_pips

    def detect_sweeps(
        self,
        candles: List[Dict[str, Any]],
        liquidity_levels: List[LiquidityLevel],
        point_size: float = 0.01
    ) -> List[SweepEvent]:
        """Scans candle series for objective liquidity sweeps."""
        sweeps: List[SweepEvent] = []
        if not candles or not liquidity_levels:
            return sweeps

        threshold = self.sweep_threshold_pips * point_size * 10.0 if point_size < 0.001 else self.sweep_threshold_pips * point_size

        for level in liquidity_levels:
            for i, c in enumerate(candles):
                # Bullish Liquidity Sweep (Sweeping Sell-Side Liquidity Below)
                if level.side == LiquiditySide.SELLSIDE.value:
                    if c["low"] <= (level.price - threshold) and c["close"] > level.price:
                        sweeps.append(
                            SweepEvent(
                                sweep_type="BULLISH_SWEEP",
                                liquidity_level_type=level.level_type,
                                liquidity_price=level.price,
                                sweep_extreme_price=c["low"],
                                reclaim_close_price=c["close"],
                                candle_index=i,
                                timestamp=c["timestamp"],
                                displacement_confirmed=False
                            )
                        )

                # Bearish Liquidity Sweep (Sweeping Buy-Side Liquidity Above)
                elif level.side == LiquiditySide.BUYSIDE.value:
                    if c["high"] >= (level.price + threshold) and c["close"] < level.price:
                        sweeps.append(
                            SweepEvent(
                                sweep_type="BEARISH_SWEEP",
                                liquidity_level_type=level.level_type,
                                liquidity_price=level.price,
                                sweep_extreme_price=c["high"],
                                reclaim_close_price=c["close"],
                                candle_index=i,
                                timestamp=c["timestamp"],
                                displacement_confirmed=False
                            )
                        )

        return sweeps
