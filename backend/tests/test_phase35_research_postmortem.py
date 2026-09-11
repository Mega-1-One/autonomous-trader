import pytest
import json
from pathlib import Path
from app.research.phase35_engine import Phase35PostMortemEngine

def test_phase35_postmortem_full():
    engine = Phase35PostMortemEngine()

    # 1. Dataset Hash Lock Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. Research Coverage Matrix
    rows = engine.generate_coverage_matrix()
    assert len(rows) >= 6
    assert all(r.is_exhausted for r in rows)

    # 3. Information Gap Audit
    gap_res = engine.execute_information_gap_audit()
    assert "available_information" in gap_res
    assert "real_volume" in gap_res["unavailable_information_evaluation"]

    # 4. Power Analysis
    power_res = engine.compute_power_analysis()
    assert "effect_0.05R" in power_res
    assert power_res["effect_0.05R"]["required_sample_size_80pct_power"] > 1000

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
