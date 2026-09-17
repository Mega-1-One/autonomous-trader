"""B-05 tests: cross-process emergency-stop sentinel (ADR-8)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import stop_state
from app.core.config import Settings
import app.core.config as config_module
from app.risk.engine import RiskEngine


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOTRADER_STATE_DIR", str(tmp_path / "state"))
    original = config_module.settings
    yield tmp_path / "state"
    config_module.settings = original


def _fresh_settings():
    """Reload settings so STATE_DIR picks up the overridden env var."""
    config_module.settings = Settings()
    return config_module.settings


def test_trigger_writes_sentinel(state_dir):
    s = _fresh_settings()
    assert s.STATE_DIR == state_dir
    assert stop_state.is_active() is None
    assert stop_state.trigger("test stop") is True
    assert stop_state.is_active() == "test stop"
    assert (state_dir / "EMERGENCY_STOP.json").exists()


def test_empty_sentinel_is_active(state_dir):
    """N2-M6: an empty (malformed) sentinel fails closed, not open."""
    _fresh_settings()
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "EMERGENCY_STOP.json").write_text("", encoding="utf-8")
    assert stop_state.is_active() == "Emergency stop sentinel present (unreadable)"


def test_inaccessible_sentinel_is_active(state_dir, monkeypatch):
    """N2-M6: stat failure (not absence) fails closed via explicit os.stat."""
    _fresh_settings()
    real_stat = os.stat

    def _denied(path):
        raise PermissionError("denied")

    monkeypatch.setattr(os, "stat", _denied)
    try:
        assert stop_state.is_active() == "Emergency stop sentinel present (inaccessible)"
    finally:
        monkeypatch.setattr(os, "stat", real_stat)


def test_trigger_returns_false_when_unwritable(state_dir, monkeypatch):
    """L-2: persistence failures are reported, not silently swallowed."""
    _fresh_settings()
    monkeypatch.setattr(os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    assert stop_state.trigger("x") is False
    assert stop_state.reset() is True


def test_reset_removes_sentinel(state_dir):
    _fresh_settings()
    stop_state.trigger("test stop")
    stop_state.reset()
    assert stop_state.is_active() is None
    assert not (state_dir / "EMERGENCY_STOP.json").exists()


def test_sentinel_persists_across_restart(state_dir):
    _fresh_settings()
    stop_state.trigger("restart-safe stop")
    # Simulate a process restart: re-read state through a new settings/stop_state
    # cycle in this interpreter (file on disk is the cross-process truth).
    assert stop_state.is_active() == "restart-safe stop"


def test_fresh_risk_engine_in_new_interpreter_sees_sentinel(state_dir):
    """Cross-process simulation: a brand-new Python process observes the sentinel."""
    _fresh_settings()
    stop_state.trigger("cross process")
    code = (
        "import sys; sys.path.insert(0, r'{backend}');"
        "from app.core import stop_state;"
        "print(stop_state.is_active())"
    ).format(backend=str(Path(__file__).resolve().parent.parent))
    full_env = dict(os.environ)
    full_env["AUTOTRADER_STATE_DIR"] = str(state_dir)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, env=full_env, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "cross process" in result.stdout


def test_fresh_risk_engine_refuses_when_sentinel_present(state_dir):
    """A fresh RiskEngine in a 'new process' refuses entries due to the sentinel."""
    _fresh_settings()
    stop_state.trigger("other process stop")
    fresh_engine = RiskEngine()
    decision = fresh_engine.evaluate_trade_risk(
        signal={"entry_price": 2400.0, "stop_loss": 2399.7, "take_profit": 2400.5},
        account_info={"equity": 10000.0},
        symbol_info={"tick_size": 0.01, "tick_value": 1.0},
    )
    assert not decision.approved
    assert "Emergency Stop" in decision.rejection_reason
    stop_state.reset()
    decision = fresh_engine.evaluate_trade_risk(
        signal={"entry_price": 2400.0, "stop_loss": 2399.7, "take_profit": 2400.5},
        account_info={"equity": 10000.0},
        symbol_info={"tick_size": 0.01, "tick_value": 1.0},
    )
    assert decision.approved


def test_missing_malformed_and_unreadable_sentinel(state_dir):
    """Failure behavior is safe for missing/malformed sentinels."""
    _fresh_settings()
    # Missing -> not active
    assert stop_state.is_active() is None
    # Malformed -> treated as active (fail safe)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "EMERGENCY_STOP.json").write_text("not json{{{", encoding="utf-8")
    assert stop_state.is_active() is not None
    # Empty JSON object -> active with generic reason
    (state_dir / "EMERGENCY_STOP.json").write_text("{}", encoding="utf-8")
    reason = stop_state.is_active()
    assert reason == "Emergency stop sentinel present"


def test_trigger_creates_missing_state_dir(tmp_path, monkeypatch):
    import app.core.config as config_module
    original = config_module.settings
    monkeypatch.setenv("AUTOTRADER_STATE_DIR", str(tmp_path / "deep" / "state"))
    _fresh_settings()
    try:
        stop_state.trigger("dir creation")
        assert (tmp_path / "deep" / "state" / "EMERGENCY_STOP.json").exists()
    finally:
        # Restore the canonical settings object so this test's STATE_DIR (and
        # its sentinel) cannot leak into later tests.
        config_module.settings = original
