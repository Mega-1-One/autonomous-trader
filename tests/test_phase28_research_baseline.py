import pytest
from pathlib import Path
from app.context.timeframe_engine import Candle
from app.scalper.instrument import InstrumentSpecification
from app.research.phase28_engine import Phase28BaselineEngine

def test_phase28_research_baseline_full():
    engine = Phase28BaselineEngine()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")

    # 1. Dataset Hash Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. Baseline Evaluation & Cost Calculation Integrity
    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + i*0.1, 100, float(1000 + i*900)) for i in range(200)]
    res = engine.run_baseline_evaluation("Random Entry", "XAUUSD", candles, spec, cost_scenario="realistic_median")

    assert res.trade_count > 0
    assert res.cost_drag_r > 0
    assert "tp_first" in res.label_quality
    assert res.classification in ["A = Robust Positive OOS Edge", "C = Gross Edge Destroyed by Costs", "D = No Demonstrated Edge"]

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
