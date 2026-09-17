"""B-03 tests: destination-aware safety gate (ADR-3 truth table).

Covers: mode × destination per cell, emergency-stop sentinel override,
and gate placement in all six order-path files / twelve mt5.order_send sites.
"""
import importlib
import inspect

import pytest

from app.core import safety
from app.core.config import ExecutionMode, Settings
import app.core.config as config_module
from app.core.safety import (
    ensure_trading_allowed,
    destination_for_adapter,
    account_trade_mode_from_adapter,
    account_trade_mode_from_mt5,
    SafetyViolation,
)
from app.data.mt5_mock import MockMT5Adapter
from app.execution.engine import ExecutionEngine


@pytest.fixture
def mode_env():
    """Yields a setter that rewrites the live settings' execution mode / flags."""
    original = config_module.settings
    def _set(mode, live=False, confirm=False):
        s = Settings()
        object.__setattr__(s, "EXECUTION_MODE", mode)
        object.__setattr__(s, "ENABLE_LIVE_TRADING", live)
        object.__setattr__(s, "LIVE_TRADING_CONFIRMATION", confirm)
        config_module.settings = s
        return s
    yield _set
    config_module.settings = original


# ---------------------------------------------------------------------------
# Truth table — MOCK destination (paper sim / mock adapter)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", [ExecutionMode.BACKTEST, ExecutionMode.PAPER, ExecutionMode.DEMO, ExecutionMode.LIVE])
def test_mock_destination_allowed_in_all_modes(mode, mode_env):
    mode_env(mode, live=True, confirm=True)  # LIVE requires flags even for mock
    assert ensure_trading_allowed("MOCK") is None


def test_live_mock_requires_flags(mode_env):
    # LIVE without flags: mock is still allowed per ADR-3 (the boot validator
    # already refuses to *start* in LIVE without flags).
    mode_env(ExecutionMode.LIVE, live=False, confirm=False)
    assert ensure_trading_allowed("MOCK") is None


# ---------------------------------------------------------------------------
# Truth table — REAL destination
# ---------------------------------------------------------------------------

def test_real_refused_in_paper(mode_env):
    mode_env(ExecutionMode.PAPER)
    with pytest.raises(SafetyViolation):
        ensure_trading_allowed("REAL")


def test_real_refused_in_backtest(mode_env):
    mode_env(ExecutionMode.BACKTEST)
    with pytest.raises(SafetyViolation):
        ensure_trading_allowed("REAL")


def test_real_demo_requires_demo_account(mode_env):
    mode_env(ExecutionMode.DEMO)
    with pytest.raises(SafetyViolation):
        ensure_trading_allowed("REAL", account_trade_mode=None)
    with pytest.raises(SafetyViolation):
        ensure_trading_allowed("REAL", account_trade_mode=1)  # live account
    assert ensure_trading_allowed("REAL", account_trade_mode=0) is None


def test_real_live_requires_flags(mode_env):
    mode_env(ExecutionMode.LIVE, live=True, confirm=False)
    with pytest.raises(SafetyViolation):
        ensure_trading_allowed("REAL")
    mode_env(ExecutionMode.LIVE, live=True, confirm=True)
    assert ensure_trading_allowed("REAL", account_trade_mode=1) is None


def test_run_demo_trader_style_real_send_refused_in_paper(mode_env):
    """The run_demo_trader.py --enable-demo scenario: a REAL send with a demo
    account (trade_mode 0) is still refused while EXECUTION_MODE=PAPER."""
    mode_env(ExecutionMode.PAPER)
    with pytest.raises(SafetyViolation, match="forbids real broker order submission"):
        ensure_trading_allowed("REAL", account_trade_mode=0)


def test_mock_paper_execution_remains_valid(mode_env):
    """Legitimate mock paper flows are preserved by the table."""
    mode_env(ExecutionMode.PAPER)
    assert ensure_trading_allowed("MOCK") is None
    mode_env(ExecutionMode.BACKTEST)
    assert ensure_trading_allowed("MOCK") is None
    from app.core import stop_state
    mode_env(ExecutionMode.LIVE, live=True, confirm=True)
    try:
        stop_state.trigger("gate test")
        with pytest.raises(SafetyViolation, match="EMERGENCY STOP"):
            ensure_trading_allowed("REAL")
        with pytest.raises(SafetyViolation):
            ensure_trading_allowed("MOCK")
    finally:
        stop_state.reset()


def test_unknown_destination_refused(mode_env):
    mode_env(ExecutionMode.PAPER)
    with pytest.raises(SafetyViolation):
        ensure_trading_allowed("SOMEWHERE")


def test_close_intent_allowed_under_sentinel(mode_env):
    """H-1: the kill switch blocks new entries but never traps closes."""
    from app.core import stop_state
    mode_env(ExecutionMode.DEMO)
    try:
        stop_state.trigger("H-1 test")
        with pytest.raises(SafetyViolation, match="EMERGENCY STOP"):
            ensure_trading_allowed("REAL", account_trade_mode=0)
        with pytest.raises(SafetyViolation, match="EMERGENCY STOP"):
            ensure_trading_allowed("MOCK")
        # Close/reduce sends pass through on both destinations.
        assert ensure_trading_allowed("REAL", account_trade_mode=0, intent="close") is None
        assert ensure_trading_allowed("MOCK", intent="close") is None
    finally:
        stop_state.reset()


def test_close_intent_still_enforces_mode(mode_env):
    """Close intent bypasses only the sentinel, not the mode/destination rules."""
    mode_env(ExecutionMode.PAPER)
    with pytest.raises(SafetyViolation, match="forbids real broker"):
        ensure_trading_allowed("REAL", account_trade_mode=0, intent="close")


def test_unknown_intent_refused(mode_env):
    mode_env(ExecutionMode.PAPER)
    with pytest.raises(SafetyViolation, match="Unknown order intent"):
        ensure_trading_allowed("MOCK", intent="reduce")


def test_unknown_mode_fail_closed(mode_env):
    """N2-M1: a mode outside the enum table must refuse, never fall through."""
    mode_env(ExecutionMode.PAPER)
    import app.core.safety as safety_module
    orig_mode = config_module.settings.EXECUTION_MODE
    try:
        object.__setattr__(config_module.settings, "EXECUTION_MODE", "SOMEDAY")
        with pytest.raises(SafetyViolation, match="not a known execution mode"):
            safety_module.ensure_trading_allowed("REAL")
    finally:
        object.__setattr__(config_module.settings, "EXECUTION_MODE", orig_mode)


# ---------------------------------------------------------------------------
# Destination derivation + account trade mode
# ---------------------------------------------------------------------------

def test_destination_for_adapter():
    mock = MockMT5Adapter()
    mock.connect()
    assert destination_for_adapter(mock) == "MOCK"

    class _FakeReal:
        def get_account_info(self):
            return {"trade_mode": 0}
    assert destination_for_adapter(_FakeReal()) == "REAL"

    assert account_trade_mode_from_adapter(mock) == 0


def test_account_trade_mode_from_mt5_without_terminal():
    # MetaTrader5 not installed in test env -> None (fail-safe input to gate)
    assert account_trade_mode_from_mt5() is None


# ---------------------------------------------------------------------------
# ExecutionEngine gate integration
# ---------------------------------------------------------------------------

def test_engine_real_destination_refused_in_paper():
    class _FakeRealAdapter(MockMT5Adapter):
        """Real-destination-like adapter for the gate path test."""
        pass
    adapter = _FakeRealAdapter()
    adapter.connect()
    engine = ExecutionEngine(adapter=adapter)
    # Force the gate to classify this adapter as REAL by patching derivation
    import app.execution.engine as ee
    orig = ee.destination_for_adapter
    ee.destination_for_adapter = lambda a: "REAL"
    try:
        result = engine.execute_signal({
            "client_signal_id": "SIG_GATE_TEST",
            "symbol": "XAUUSD", "direction": "LONG",
            "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
        })
        assert result["status"] == "REJECTED"
        assert "forbids real broker order submission" in result["reason"]
    finally:
        ee.destination_for_adapter = orig


# ---------------------------------------------------------------------------
# Gate coverage: all six order-path files call ensure_trading_allowed
# ---------------------------------------------------------------------------

ORDER_PATH_FILES = [
    "app/scalper/autonomous_scalper_daemon.py",
    "app/scalper/demo_scalper_engine.py",
    "app/scalper/ultra_tick_scalper.py",
    "app/scalper/gold_multi_scalper.py",
    "app/scalper/grid_martingale_bot.py",
    "scripts/run_demo_trader.py",
]


@pytest.mark.parametrize("relpath", ORDER_PATH_FILES)
def test_every_order_path_file_imports_and_calls_the_gate(relpath):
    """Each order-send file must import and invoke the gate (E-04 step 5)."""
    backend_root = inspect.stack()[0].filename.rsplit("tests", 1)[0]
    with open(backend_root + relpath, "r", encoding="utf-8") as f:
        src = f.read()
    assert "ensure_trading_allowed" in src, f"{relpath} does not import/call the gate"
    assert "ensure_trading_allowed(" in src, f"{relpath} never invokes the gate"


def test_gate_precedes_every_direct_order_send():
    """Each direct mt5.order_send site must be preceded by a gate call in its function."""
    import re
    backend_root = inspect.stack()[0].filename.rsplit("tests", 1)[0]
    files = [
        "app/scalper/autonomous_scalper_daemon.py",
        "app/scalper/demo_scalper_engine.py",
        "app/scalper/ultra_tick_scalper.py",
        "app/scalper/gold_multi_scalper.py",
        "app/scalper/grid_martingale_bot.py",
        "scripts/run_demo_trader.py",
    ]
    for relpath in files:
        with open(backend_root + relpath, "r", encoding="utf-8") as f:
            src = f.read()
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "mt5.order_send(" in line:
                window = "\n".join(lines[max(0, i - 45):i + 1])
                assert "ensure_trading_allowed(" in window, (
                    f"{relpath}: order_send at line {i + 1} has no gate call immediately before it"
                )
