"""ICT/scalp strategy behind the StrategyProvider seam (E2).

Behavior is intentionally identical to constructing StrategyEngine directly:
same inputs, same outputs, same config source. Replacing the default provider
name is the whole "replace the strategy" operation for API/runner/backtest.
"""
from typing import Any, Dict, List, Optional

from app.strategy.displacement import DisplacementEngine
from app.strategy.engine import StrategyEngine
from app.strategy.fvg import FVGEngine
from app.strategy.liquidity import LiquidityEngine
from app.strategy.order_block import OrderBlockEngine
from app.strategy.provider import (
    MarketInputs,
    StrategyProvider,
    register_provider,
    validate_decision,
)
from app.strategy.structure import StructureEngine
from app.strategy.sweeps import SweepEngine


class ICTStrategyAdapter(StrategyProvider):
    """Adapts the ICT/SMC scalp engine to the platform decision contract."""

    name = "ict_scalp"

    def __init__(self) -> None:
        super().__init__()
        self._engine: Optional[StrategyEngine] = None

    def configure(self, config: Optional[Dict[str, Any]]) -> None:
        super().configure(config)
        # None falls back to settings.strategy_config inside StrategyEngine,
        # exactly as before; an explicit dict is used verbatim.
        self._engine = StrategyEngine(self._config or None)

    def evaluate(self, inputs: MarketInputs) -> Dict[str, Any]:
        assert self._engine is not None, "provider used before configure()"
        signal = self._engine.evaluate_setup(
            symbol=inputs.symbol,
            htf_candles=inputs.candles.get("HTF", []),
            ltf_candles=inputs.candles.get("LTF", []),
            point_size=inputs.point_size,
        )
        return validate_decision(signal.to_dict())

    def describe(
        self,
        *,
        symbol: str,
        candles: List[Dict[str, Any]],
        timeframe: str = "M5",
        point_size: float = 0.01,
        **options: Any,
    ) -> Optional[Dict[str, Any]]:
        """ICT analysis payload (superset used by the three analysis routers).

        Option keys mirror the routers' historical parameters so outputs are
        bit-identical: swing_lookback, confirm_on_close, tolerance_pips.
        """
        struct = StructureEngine(
            swing_lookback=options.get("swing_lookback", 3),
            confirm_on_close=options.get("confirm_on_close", False),
        )
        analysis = struct.analyze_structure(candles)
        tolerance = options.get("tolerance_pips", None)
        liq = LiquidityEngine() if tolerance is None else LiquidityEngine(
            eqh_eql_tolerance_pips=tolerance
        )
        levels = liq.get_all_liquidity_levels(candles, analysis.swing_points, point_size)
        displacements = DisplacementEngine().detect_displacement(candles)
        fvgs = FVGEngine().detect_fvgs(candles, timeframe=timeframe, point_size=point_size)
        sweeps = SweepEngine().detect_sweeps(candles, levels, point_size=point_size)
        order_blocks = OrderBlockEngine().detect_order_blocks(
            candles, displacements, analysis.events
        )
        buyside = [lv.to_dict() for lv in levels if lv.side == "BUYSIDE"]
        sellside = [lv.to_dict() for lv in levels if lv.side == "SELLSIDE"]
        return {
            "trend": analysis.trend,
            "analysis": analysis.to_dict(),
            "total_levels": len(levels),
            "buyside_liquidity": buyside,
            "sellside_liquidity": sellside,
            "displacements": [d.to_dict() for d in displacements],
            "fair_value_gaps": [f.to_dict() for f in fvgs],
            "liquidity_sweeps": [s.to_dict() for s in sweeps],
            "order_blocks": [ob.to_dict() for ob in order_blocks],
        }


register_provider(ICTStrategyAdapter.name, ICTStrategyAdapter)
