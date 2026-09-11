import pytest
import json
from pathlib import Path
from app.context.timeframe_engine import Candle
from app.research.market_state.market_state_engine import MarketStateEngine, RegimeDefinitionEngine

def test_phase33_market_state_full():
    engine = MarketStateEngine()

    # 1. Dataset Hash Lock Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. State Classification (Past Data Only)
    reg_engine = RegimeDefinitionEngine()
    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + i*0.1, 100, float(1000 + i*900)) for i in range(100)]
    state_name = reg_engine.classify_state(candles, 50)
    assert state_name in reg_engine.STATES or state_name == "SESSION_TRANSITION"

    # 3. Market State Distribution Analysis
    metrics_list = engine.evaluate_state_distributions("XAUUSD", candles, horizon_steps=15)
    assert len(metrics_list) > 0
    assert metrics_list[0].sample_size > 0

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
