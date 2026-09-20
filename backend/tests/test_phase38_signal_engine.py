import pytest
from app.core.config import settings, ExecutionMode
from app.risk.engine import RiskEngine
from app.strategy.plugin import (
    UnvalidatedResearchStrategy,
    SignalQualityGate,
    UnifiedSignal,
    SignalDirection
)

def test_phase38_safety_isolation():
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

def test_phase38_unvalidated_research_strategy_generation():
    strat = UnvalidatedResearchStrategy()
    assert strat.initialize({}) is True
    assert strat.strategy_name == "UNVALIDATED_RESEARCH_STRATEGY"

    # Feed dummy candle series
    candles = [{"close": 2400.0 + i*0.5} for i in range(25)]
    m_state = strat.evaluate_market("XAUUSD", {"candles": candles})
    assert m_state["status"] == "VALID"
    assert m_state["trend"] == "BULLISH"

    sig = strat.generate_signal("XAUUSD", m_state)
    assert sig is not None
    assert sig.instrument == "XAUUSD"
    assert sig.direction == SignalDirection.LONG
    assert sig.entry_price > 0
    assert sig.stop_loss < sig.entry_price
    assert sig.take_profit > sig.entry_price
    assert sig.data_snapshot_hash != ""
    assert "Unvalidated research strategy" in sig.explanation
    assert len(sig.reason_codes) >= 2

def test_phase38_signal_quality_gate_flow():
    strat = UnvalidatedResearchStrategy()
    risk = RiskEngine(config={"risk_per_trade_percent": 0.1})
    gate = SignalQualityGate(risk_engine=risk)

    candles = [{"close": 2400.0 + i*0.5} for i in range(25)]
    m_state = strat.evaluate_market("XAUUSD", {"candles": candles})
    sig = strat.generate_signal("XAUUSD", m_state)

    acc_info = {"equity": 10000.0}
    sym_info = {"digits": 2, "point_size": 0.01, "tick_size": 0.01, "tick_value": 1.0, "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01}

    # 1. Normal Approval
    approved, processed_sig = gate.process_signal(
        signal=sig,
        data_quality_ok=True,
        market_state_ok=True,
        account_info=acc_info,
        symbol_info=sym_info
    )
    assert approved is True
    assert processed_sig.approved is True

    # 2. Duplicate Signal Rejection
    app_dup, dup_sig = gate.process_signal(
        signal=sig,
        data_quality_ok=True,
        market_state_ok=True,
        account_info=acc_info,
        symbol_info=sym_info
    )
    assert app_dup is False
    assert dup_sig.rejection_stage == "DUPLICATE_PROTECTION"

def test_phase38_quality_gate_data_failure():
    strat = UnvalidatedResearchStrategy()
    gate = SignalQualityGate()

    candles = [{"close": 2400.0 + i*0.5} for i in range(25)]
    m_state = strat.evaluate_market("XAUUSD", {"candles": candles})
    sig = strat.generate_signal("XAUUSD", m_state)

    # Force a fresh hash so duplicate check passes
    sig.data_snapshot_hash = "FRESH_HASH_TEST"

    approved, rejected_sig = gate.process_signal(
        signal=sig,
        data_quality_ok=False,  # Corrupted data
        market_state_ok=True,
        account_info={"equity": 10000.0},
        symbol_info={"digits": 2}
    )
    assert approved is False
    assert rejected_sig.rejection_stage == "DATA_QUALITY"
