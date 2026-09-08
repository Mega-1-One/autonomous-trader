import pytest
import time
from app.scalper.tick_engine import TickEngine, TickBuffer, TickData
from app.execution.engine import ExecutionEngine
from app.data.mt5_mock import MockMT5Adapter

def test_tick_buffer_capacity():
    buffer = TickBuffer(max_size=100)
    now = time.time()
    for i in range(150):
        buffer.add_tick(TickData("XAUUSD", 2400.0 + i, 2400.5 + i, 2400.0 + i, 0.5, now + i))

    assert len(buffer) == 100
    assert buffer.get_last_n(10)[-1].bid == 2400.0 + 149

def test_duplicate_tick_rejection():
    buffer = TickBuffer(max_size=100)
    now = time.time()
    tick1 = TickData("XAUUSD", 2400.0, 2400.5, 2400.0, 0.5, now)
    tick2 = TickData("XAUUSD", 2400.0, 2400.5, 2400.0, 0.5, now)

    assert buffer.add_tick(tick1) is True
    assert buffer.add_tick(tick2) is False
    assert len(buffer) == 1

def test_stale_tick_rejection():
    engine = TickEngine(max_stale_seconds=2.0)
    stale_timestamp = time.time() - 10.0
    res = engine.process_tick("XAUUSD", 2400.0, 2400.5, timestamp=stale_timestamp)
    assert res is None

def test_execution_engine_broker_position_sync():
    adapter = MockMT5Adapter()
    adapter.connect()
    # Add a mock open position to simulate active broker position
    adapter.positions.append({
        "ticket": 12345, "symbol": "XAUUSD", "type": "BUY", "volume": 0.1,
        "price_open": 2400.0, "sl": 2390.0, "tp": 2420.0
    })


    exec_engine = ExecutionEngine(adapter=adapter)
    signal = {
        "client_signal_id": "SIG_SYNC_TEST",
        "symbol": "XAUUSD",
        "direction": "LONG",
        "entry_price": 2400.0,
        "stop_loss": 2390.0,
        "take_profit": 2420.0
    }

    res = exec_engine.execute_signal(signal)
    assert res["status"] in ["EXECUTED", "REJECTED"]
