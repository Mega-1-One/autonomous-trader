"""N2-H2 tests: order direction is validated, never silently flipped to SELL."""
import pytest

from app.data.mt5_mock import MockMT5Adapter
from app.execution.engine import ExecutionEngine


def _engine():
    adapter = MockMT5Adapter()
    adapter.connect()
    return ExecutionEngine(adapter=adapter)


def _order(order_id, direction):
    return {
        "client_signal_id": order_id,
        "symbol": "XAUUSD", "direction": direction,
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
    }


def test_engine_rejects_garbage_direction():
    engine = _engine()
    res = engine.execute_signal(_order("SIG_DIR_A", "GARBAGE"))
    assert res["status"] == "REJECTED"
    assert "Invalid direction" in res["reason"]
    assert engine.positions == {}


def test_engine_rejects_empty_direction():
    engine = _engine()
    res = engine.execute_signal(_order("SIG_DIR_B", ""))
    assert res["status"] == "REJECTED"


def test_engine_normalizes_case():
    engine = _engine()
    res = engine.execute_signal(_order("SIG_DIR_C", "long"))
    assert res["status"] == "EXECUTED"
    assert res["position"]["direction"] == "LONG"


def test_engine_accepts_short():
    engine = _engine()
    res = engine.execute_signal(_order("SIG_DIR_D", "SHORT"))
    assert res["status"] == "EXECUTED"
    assert res["position"]["direction"] == "SHORT"


@pytest.mark.asyncio
async def test_api_rejects_garbage_direction_422(async_client):
    res = await async_client.post("/api/execution/orders", json={
        "client_signal_id": "SIG_DIR_E",
        "symbol": "XAUUSD", "direction": "GARBAGE",
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
    })
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_api_accepts_lowercase_direction(async_client):
    res = await async_client.post("/api/execution/orders", json={
        "client_signal_id": "SIG_DIR_F",
        "symbol": "XAUUSD", "direction": "short",
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
    })
    assert res.status_code == 200
    assert res.json()["position"]["direction"] == "SHORT"
    pos_id = res.json()["position"]["position_id"]
    await async_client.post(f"/api/execution/positions/{pos_id}/close")
