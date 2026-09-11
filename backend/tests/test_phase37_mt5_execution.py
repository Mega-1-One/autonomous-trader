import pytest
from app.core.config import settings, ExecutionMode
from app.data.mt5_mock import MockMT5Adapter
from app.execution.engine import ExecutionEngine
from app.execution.models import (
    OrderRequest,
    OrderResult,
    OrderType,
    OrderStatus,
    DynamicSymbolSpecification,
    AccountState
)

def test_phase37_safety_isolation():
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

def test_phase37_dynamic_symbol_spec():
    spec = DynamicSymbolSpecification(
        symbol="XAUUSDm",
        canonical_name="XAUUSD",
        digits=3,
        point_size=0.001,
        tick_size=0.01,
        tick_value=1.0,
        contract_size=100.0,
        min_volume=0.01,
        max_volume=100.0,
        volume_step=0.01,
        spread_pips=1.5
    )
    d = spec.to_dict()
    assert d["symbol"] == "XAUUSDm"
    assert d["digits"] == 3
    assert d["volume_step"] == 0.01

def test_phase37_order_request_and_result_models():
    req = OrderRequest(
        client_order_id="ORD_P37_001",
        symbol="XAUUSDm",
        order_type=OrderType.BUY,
        volume=0.05,
        requested_price=2400.0,
        stop_loss=2395.0,
        take_profit=2410.0
    )
    assert req.order_type == OrderType.BUY
    assert req.volume == 0.05

    res = OrderResult(
        client_order_id=req.client_order_id,
        status=OrderStatus.EXECUTED,
        broker_ticket=123456,
        fill_price=2400.02,
        fill_volume=0.05,
        slippage_cost=0.10,
        commission_cost=0.35,
        spread_cost=0.20,
        latency_ms=12.4
    )
    assert res.status == OrderStatus.EXECUTED
    assert res.broker_ticket == 123456

def test_phase37_paper_execution_flow():
    adapter = MockMT5Adapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)

    signal = {
        "client_signal_id": "SIG_P37_TEST",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2410.0
    }

    result = engine.execute_signal(signal, current_spread_pips=1.0)
    assert result["status"] == "EXECUTED"
    assert "position" in result
    pos = result["position"]
    assert pos["symbol"] == "XAUUSD"
    assert pos["volume"] > 0
    assert pos["status"] == "OPEN"

def test_phase37_emergency_kill_switch_blocking():
    adapter = MockMT5Adapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)

    engine.risk_engine.trigger_emergency_stop("Phase 37 Security Test")
    assert engine.risk_engine.emergency_stop_active is True

    signal = {
        "client_signal_id": "SIG_P37_BLOCKED",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2410.0
    }

    res = engine.execute_signal(signal)
    assert res["status"] == "REJECTED"
    assert "Emergency Stop" in res["reason"]
