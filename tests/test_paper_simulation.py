import pytest
from app.core.config import settings, ExecutionMode
from app.execution.realtime_paper_simulation import RealtimePaperSimulationEngine

def test_paper_simulation_safety_and_init():
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

    engine = RealtimePaperSimulationEngine()
    assert engine.account_balance == 0.0
    assert len(engine.active_positions) == 0

def test_paper_simulation_cycle():
    engine = RealtimePaperSimulationEngine()
    if engine.initialize():
        summary = engine.run_continuous_stream(duration_seconds=2)
        assert summary["ticks_processed"] >= 0
        assert summary["status"] == "STREAM_FINISHED"
        engine.shutdown()
