"""ICT/scalp strategy behind the StrategyProvider seam (E2).

Behavior is intentionally identical to constructing StrategyEngine directly:
same inputs, same outputs, same config source. Replacing the default provider
name is the whole "replace the strategy" operation for API/runner/backtest.
"""
from typing import Any, Dict, Optional

from app.strategy.engine import StrategyEngine
from app.strategy.provider import (
    MarketInputs,
    StrategyProvider,
    register_provider,
    validate_decision,
)


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


register_provider(ICTStrategyAdapter.name, ICTStrategyAdapter)
