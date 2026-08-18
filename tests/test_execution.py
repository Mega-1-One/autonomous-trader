import pytest
from app.execution.engine import ExecutionEngine
from app.data.mt5_mock import MockMT5Adapter

@pytest.fixture
def exec_engine():
    mock_adapter = MockMT5Adapter()
    mock_adapter.connect()
    return ExecutionEngine(adapter=mock_adapter)

def test_execute_signal_success(exec_engine):
    signal = {
        "client_signal_id": "SIG_TEST_001",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2420.0
    }

    res = exec_engine.execute_signal(signal, current_spread_pips=1.0)
    assert res["status"] == "EXECUTED"
    assert "position" in res
    pos = res["position"]
    assert pos["symbol"] == "XAUUSD"
    assert pos["direction"] == "LONG"
    assert pos["volume"] == 0.05

def test_idempotency_protection(exec_engine):
    signal = {
        "client_signal_id": "SIG_TEST_DUP",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2420.0
    }

    res1 = exec_engine.execute_signal(signal)
    assert res1["status"] == "EXECUTED"

    # Second submission with identical signal ID
    res2 = exec_engine.execute_signal(signal)
    assert res2["status"] == "REJECTED"
    assert "Duplicate order ID" in res2["reason"]

def test_position_break_even_activation(exec_engine):
    signal = {
        "client_signal_id": "SIG_TEST_BE",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2420.0
    }
    res = exec_engine.execute_signal(signal)
    pos_id = res["position"]["position_id"]

    # Price moves to 2410.0 (1.0 R gain -> triggers Break-Even)
    exec_engine.update_positions({"XAUUSD": 2410.0})
    pos = exec_engine.positions[pos_id]

    assert pos.break_even_activated is True
    assert pos.stop_loss > 2390.0  # SL moved up to entry + offset

def test_emergency_close_all(exec_engine):
    signal = {
        "client_signal_id": "SIG_TEST_CLOSE",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2420.0
    }
    exec_engine.execute_signal(signal)

    closed = exec_engine.close_all_positions("EMERGENCY_TEST")
    assert len(closed) == 1
    assert closed[0]["status"] == "CLOSED"
    assert closed[0]["exit_reason"] == "EMERGENCY_TEST"

@pytest.mark.asyncio
async def test_api_get_positions(async_client):
    res = await async_client.get("/api/execution/positions")
    assert res.status_code == 200
    data = res.json()
    assert "total_positions" in data
    assert "open_positions" in data
    assert "closed_positions" in data
