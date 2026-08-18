import pytest
import json
from pathlib import Path
from app.research.final_audit_engine import FinalResearchAuditEngine

def test_final_research_audit_full():
    engine = FinalResearchAuditEngine()

    # 1. Dataset Hash Lock
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. Power Analysis
    power_500 = engine.compute_statistical_power(500, effect_size=0.05)
    power_3000 = engine.compute_statistical_power(3000, effect_size=0.05)
    assert power_500 > 0.20
    assert power_3000 > 0.70

    # 3. Research Ledger & Audit Execution
    ledger = engine.generate_research_ledger()
    assert len(ledger) >= 10

    audit_res = engine.execute_program_audit()
    assert "A =" in audit_res["final_verdict"] or "B =" in audit_res["final_verdict"]

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
