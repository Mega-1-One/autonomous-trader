import pytest
import json
from pathlib import Path
from app.context.timeframe_engine import Candle
from app.research.phase34_engine import Phase34ConfirmationEngine

def test_phase34_confirmation_full():
    engine = Phase34ConfirmationEngine()

    # 1. Dataset Hash Lock Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. Frozen State Definition Document
    frozen_path = Path(__file__).resolve().parent.parent / "data" / "phase34_frozen_state_definition.json"
    assert frozen_path.exists()
    with open(frozen_path, "r") as f:
        data = json.load(f)
    assert data["state_name"] == "VOLATILITY_COMPRESSION"
    assert data["definition_rules"]["condition"] == "atr_ratio < 0.70"

    # 3. Walk-Forward Validation & Placebo Tests
    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + (i%5)*0.1, 100, float(1000 + i*900)) for i in range(250)]
    folds = engine.run_walk_forward_validation("XAUUSD", candles)
    assert len(folds) == 4

    placebo_res = engine.run_placebo_test(candles)
    assert placebo_res["null_hypothesis_passed"] is True

    # 4. Multiple Testing Audit
    mt_audit = engine.run_multiple_testing_audit()
    assert mt_audit["expected_false_discoveries"] == 5.75
    assert mt_audit["family_wise_error_rate"] > 0.90

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
