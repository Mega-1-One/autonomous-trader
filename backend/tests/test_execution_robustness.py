"""N2-H3/N2-M3/N2-L1 tests: retry after FAILED, adapter None-guard, FX break-even."""
import pytest

from app.data.mt5_mock import MockMT5Adapter
from app.execution.engine import ExecutionEngine


class _FlakyAdapter(MockMT5Adapter):
    """Fails the first send, succeeds afterwards (transient broker failure)."""
    def __init__(self):
        super().__init__()
        self.calls = 0

    def send_order(self, order_dict):
        self.calls += 1
        if self.calls == 1:
            return {"retcode": 10027, "comment": "Algo trading disabled"}
        return super().send_order(order_dict)


class _NoneAdapter(MockMT5Adapter):
    def send_order(self, order_dict):
        return None


def _order(order_id):
    return {
        "client_signal_id": order_id,
        "symbol": "XAUUSD", "direction": "LONG",
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
    }


def test_failed_does_not_consume_idempotency_id():
    """N2-H3: a broker FAILED leaves the ID reusable for a legitimate retry."""
    adapter = _FlakyAdapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    first = engine.execute_signal(_order("SIG_RETRY_A"))
    assert first["status"] == "FAILED"
    second = engine.execute_signal(_order("SIG_RETRY_A"))
    assert second["status"] == "EXECUTED", second
    assert "Duplicate" not in second.get("reason", "")


def test_duplicate_after_executed_still_blocked():
    adapter = MockMT5Adapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    assert engine.execute_signal(_order("SIG_RETRY_B"))["status"] == "EXECUTED"
    dup = engine.execute_signal(_order("SIG_RETRY_B"))
    assert dup["status"] == "REJECTED"
    assert "Duplicate order ID" in dup["reason"]


def test_concurrent_same_id_single_fill():
    """NEW-07: concurrent same-ID submissions yield exactly one fill."""
    import threading
    import time

    class _SlowAdapter(MockMT5Adapter):
        def send_order(self, order_dict):
            time.sleep(0.05)
            return super().send_order(order_dict)

    adapter = _SlowAdapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    results = []

    def _submit():
        results.append(engine.execute_signal(_order("SIG_RACE")))

    threads = [threading.Thread(target=_submit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert len(results) == 8
    executed = [r for r in results if r["status"] == "EXECUTED"]
    rejected = [r for r in results if r["status"] == "REJECTED"]
    assert len(executed) == 1
    assert len(rejected) == 7
    assert all("Duplicate order ID" in r["reason"] for r in rejected)


def test_none_adapter_response_is_failed_not_crash():
    """N2-L1: adapter returning None yields FAILED instead of AttributeError."""
    adapter = _NoneAdapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    res = engine.execute_signal(_order("SIG_NONE_A"))
    assert res["status"] == "FAILED"


def _break_even_engine():
    adapter = MockMT5Adapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    engine.break_even_enabled = True
    engine.break_even_trigger_r = 0.5
    engine.break_even_offset_pips = 0.1
    return engine


def test_break_even_uses_pip_size_fx():
    """NEW-02: FX offset = 0.1 pips x pip 0.0001 = 0.00001 (exact SL)."""
    engine = _break_even_engine()
    res = engine.execute_signal({
        "client_signal_id": "SIG_BE_FX",
        "symbol": "EURUSD", "direction": "LONG",
        "entry_price": 1.08500, "stop_loss": 1.08400, "take_profit": 1.09500,
    })
    assert res["status"] == "EXECUTED"
    pos_id = res["position"]["position_id"]
    # R = (1.08550-1.08500)/(1.08500-1.08400) = 0.5 >= trigger.
    engine.update_positions({"EURUSD": 1.08550})
    pos = engine.positions[pos_id]
    assert pos.break_even_activated is True
    assert pos.stop_loss == 1.08501


def test_break_even_uses_pip_size_gold():
    """NEW-02: gold offset = 0.1 pips x pip 0.1 = 0.01 (exact SL)."""
    engine = _break_even_engine()
    res = engine.execute_signal({
        "client_signal_id": "SIG_BE_XAU",
        "symbol": "XAUUSD", "direction": "LONG",
        "entry_price": 2400.0, "stop_loss": 2399.0, "take_profit": 2402.0,
    })
    assert res["status"] == "EXECUTED"
    pos_id = res["position"]["position_id"]
    # R = (2400.5-2400.0)/(2400.0-2399.0) = 0.5 >= trigger.
    engine.update_positions({"XAUUSD": 2400.5})
    pos = engine.positions[pos_id]
    assert pos.break_even_activated is True
    assert pos.stop_loss == 2400.01
