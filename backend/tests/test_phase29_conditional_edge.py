import pytest
from pathlib import Path
from app.context.timeframe_engine import Candle
from app.scalper.instrument import InstrumentSpecification
from app.research.phase29_conditional_engine import Phase29ConditionalEngine

def test_phase29_conditional_edge_full():
    engine = Phase29ConditionalEngine()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")

    # 1. Dataset Hash Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. Regime Calculation (Past Data Only) & Conditional Evaluation
    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + i*0.1, 100, float(1000 + i*900)) for i in range(200)]
    regime = engine.determine_regime(candles, 50)
    assert "volatility" in regime
    assert "trend" in regime

    res = engine.evaluate_conditional_setup(
        "LIQUIDITY_SWEEP_REVERSAL", "XAUUSD", candles, spec, {"volatility": "HIGH_VOLATILITY"}
    )
    assert res.classification in [
        "A = Robust Positive OOS Edge", "C = Gross Edge Destroyed by Costs",
        "D = No Demonstrated Edge", "D = No Demonstrated Edge (INSUFFICIENT_SAMPLE)"
    ]

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
