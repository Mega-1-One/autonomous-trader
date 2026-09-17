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


def test_none_adapter_response_is_failed_not_crash():
    """N2-L1: adapter returning None yields FAILED instead of AttributeError."""
    adapter = _NoneAdapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    res = engine.execute_signal(_order("SIG_NONE_A"))
    assert res["status"] == "FAILED"


def test_break_even_uses_symbol_point_size():
    """N2-M3: FX break-even offset uses the symbol point size, not 0.01."""
    adapter = MockMT5Adapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    engine.break_even_enabled = True
    engine.break_even_trigger_r = 0.5
    engine.break_even_offset_pips = 0.1
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
    # Offset = 0.1 pips * point 0.00001 = 0.000001 (not 0.1 * 0.01 = 0.001).
    assert pos.stop_loss == pytest.approx(1.085 + 0.000001)
    assert pos.stop_loss != pytest.approx(1.085 + 0.001)
