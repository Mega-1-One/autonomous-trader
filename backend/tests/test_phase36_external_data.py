import pytest
import json
from pathlib import Path
from app.research.phase36_external_engine import Phase36ExternalEngine

def test_phase36_external_data_full():
    engine = Phase36ExternalEngine()

    # 1. Existing Dataset Hash Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. CME Futures Audit & Quality Gates
    cme_res = engine.audit_cme_futures()
    assert cme_res["quality_gates"]["schema_validation"] == "PASS"
    assert cme_res["quality_gates"]["timestamp_validation"] == "PASS"

    # 3. Macro Events Audit & Information Availability Timestamp
    macro_res = engine.audit_macro_events()
    assert macro_res["lookahead_audit"]["information_available_time"] == "Strict publication timestamp enforced"

    # 4. Level-2 Audit
    l2_res = engine.audit_l2_depth()
    assert l2_res["status"] == "UNAVAILABLE"

    # 5. Readiness Score Calculation
    scores = {
        "data_authenticity": 90.0,
        "historical_depth": 85.0,
        "timestamp_quality": 95.0,
        "information_novelty": 90.0,
        "synchronization_quality": 80.0,
        "field_completeness": 75.0,
        "reproducibility": 85.0,
        "cost_accessibility": 70.0,
        "research_suitability": 90.0
    }
    readiness = engine.calculate_readiness_score("CME Gold Futures", scores)
    assert readiness.total_score >= 75.0
    assert readiness.confidence_level == "HIGH"

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
