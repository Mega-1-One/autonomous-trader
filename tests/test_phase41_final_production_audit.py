import json
from pathlib import Path
import pytest

from app.core.config import settings, ExecutionMode
from app.information.pipeline import InformationPipeline
from app.information.futures_volume import MockFuturesVolumeProvider, FuturesVolumeRecord
from app.strategy.plugin import UnvalidatedResearchStrategy, SignalQualityGate
from app.risk.engine import RiskEngine
from app.execution.engine import ExecutionEngine
from app.data.mt5_mock import MockMT5Adapter

def test_phase41_safety_defaults_enforced():
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

def test_phase41_deliverables_integrity():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    required_files = [
        "phase36_information_availability.json",
        "phase36_architecture_report.md",
        "phase36_architecture_registry.json",
        "phase37_execution_audit.md",
        "phase37_execution_registry.json",
        "phase38_signal_engine_report.md",
        "phase38_signal_registry.json",
        "phase39_forward_test_report.md",
        "phase39_forward_results.csv",
        "phase39_forward_registry.json",
        "phase40_risk_certification.md",
        "phase40_failure_matrix.csv",
        "phase40_safety_registry.json",
        "phase41_final_audit.md",
        "phase41_final_audit.json",
        "phase41_system_health_report.json",
        "phase41_risk_certification.json"
    ]

    for fname in required_files:
        fpath = data_dir / fname
        assert fpath.exists(), f"Missing required Phase 36-41 deliverable: {fname}"

def test_phase41_final_audit_classification():
    data_dir = Path(__file__).resolve().parent.parent / "data"
    audit_json = data_dir / "phase41_final_audit.json"
    with open(audit_json, "r") as f:
        data = json.load(f)

    assert data["classification"] == "A"
    assert data["classification_description"] == "PRODUCTION-READY INFRASTRUCTURE"
    assert data["safety_configuration"]["execution_mode"] == "PAPER"

def test_phase41_end_to_end_autonomous_loop():
    adapter = MockMT5Adapter()
    adapter.connect()
    exec_engine = ExecutionEngine(adapter=adapter)
    risk_engine = RiskEngine(config={"risk_per_trade_percent": 0.1})
    strat = UnvalidatedResearchStrategy()
    gate = SignalQualityGate(risk_engine=risk_engine)

    candles = [{"close": 2400.0 + i*0.5} for i in range(25)]
    m_state = strat.evaluate_market("XAUUSD", {"candles": candles})
    sig = strat.generate_signal("XAUUSD", m_state)

    acc = adapter.get_account_info() or {"equity": 10000.0}
    sym_info = adapter.get_symbol_info("XAUUSD") or {"digits": 2, "point_size": 0.01, "tick_size": 0.01, "tick_value": 1.0, "min_volume": 0.01, "max_volume": 100.0, "volume_step": 0.01}

    approved, final_sig = gate.process_signal(
        signal=sig,
        data_quality_ok=True,
        market_state_ok=True,
        account_info=acc,
        symbol_info=sym_info
    )

    assert approved is True
    assert final_sig.approved is True

    # Execute paper order
    res = exec_engine.execute_signal(final_sig.to_dict(), current_spread_pips=1.0)
    assert res["status"] == "EXECUTED"
    assert "position" in res
