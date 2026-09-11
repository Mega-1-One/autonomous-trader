import pytest
from app.core.config import settings, ExecutionMode
from app.risk.failure_recovery_engine import Phase40FailureRecoveryEngine, CircuitBreakerMode

def test_phase40_safety_isolation():
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

def test_phase40_circuit_breaker_modes():
    engine = Phase40FailureRecoveryEngine()
    assert engine.circuit_breaker_mode == CircuitBreakerMode.NORMAL

    # 1. Soft Stop Blocks Entries
    engine.set_circuit_breaker(CircuitBreakerMode.SOFT_STOP)
    passed, reason = engine.evaluate_entry_safety("ORD_001", is_connected=True, tick_age_seconds=1.0, current_spread_pips=1.0)
    assert passed is False
    assert "SOFT_STOP" in reason

    # 2. Hard Stop Blocks Entries
    engine.set_circuit_breaker(CircuitBreakerMode.HARD_STOP)
    passed, reason = engine.evaluate_entry_safety("ORD_002", is_connected=True, tick_age_seconds=1.0, current_spread_pips=1.0)
    assert passed is False
    assert "HARD_STOP" in reason

    # 3. Emergency Stop Blocks Entries persistently
    engine.set_circuit_breaker(CircuitBreakerMode.EMERGENCY_STOP, reason="Manual admin kill switch")
    passed, reason = engine.evaluate_entry_safety("ORD_003", is_connected=True, tick_age_seconds=1.0, current_spread_pips=1.0)
    assert passed is False
    assert "EMERGENCY_STOP" in reason

    # Reset
    engine.reset_circuit_breaker()
    assert engine.circuit_breaker_mode == CircuitBreakerMode.NORMAL

def test_phase40_adversarial_data_rejections():
    engine = Phase40FailureRecoveryEngine()

    # Disconnected MT5
    passed, reason = engine.evaluate_entry_safety("ORD_D1", is_connected=False, tick_age_seconds=1.0, current_spread_pips=1.0)
    assert passed is False
    assert "DISCONNECTED" in reason

    # Stale Tick (10 seconds old)
    passed, reason = engine.evaluate_entry_safety("ORD_D2", is_connected=True, tick_age_seconds=10.0, current_spread_pips=1.0)
    assert passed is False
    assert "STALE_DATA" in reason

    # Crossed Book
    passed, reason = engine.evaluate_entry_safety("ORD_D3", is_connected=True, tick_age_seconds=1.0, current_spread_pips=1.0, is_crossed=True)
    assert passed is False
    assert "DATA_CORRUPTION" in reason

    # Spread Explosion (25 pips vs 5 pip threshold)
    passed, reason = engine.evaluate_entry_safety("ORD_D4", is_connected=True, tick_age_seconds=1.0, current_spread_pips=25.0, max_allowed_spread_pips=5.0)
    assert passed is False
    assert "SPREAD_EXPLOSION" in reason

def test_phase40_idempotency_duplicate_blocking():
    engine = Phase40FailureRecoveryEngine()

    # First attempt passes
    p1, r1 = engine.evaluate_entry_safety("ORD_IDEMPOTENT_001", is_connected=True, tick_age_seconds=1.0, current_spread_pips=1.0)
    assert p1 is True

    # Duplicate attempt is blocked
    p2, r2 = engine.evaluate_entry_safety("ORD_IDEMPOTENT_001", is_connected=True, tick_age_seconds=1.0, current_spread_pips=1.0)
    assert p2 is False
    assert "DUPLICATE_ORDER" in r2

def test_phase40_process_restart_recovery():
    engine = Phase40FailureRecoveryEngine()
    engine.persisted_positions["POS_001"] = {"symbol": "XAUUSD", "volume": 0.05}
    engine.executed_order_ids.add("ORD_EXISTING_001")

    res = engine.simulate_crash_and_restart()
    assert res["restart_successful"] is True
    assert res["recovered_positions"] == 1
    assert res["idempotent_order_ids_restored"] == 1
    assert res["unintended_orders_placed"] == 0
