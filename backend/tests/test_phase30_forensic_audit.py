import pytest
from pathlib import Path
from app.context.timeframe_engine import Candle
from app.scalper.instrument import InstrumentSpecification
from app.research.phase30_forensic_engine import Phase30ForensicEngine

def test_phase30_forensic_audit_full():
    engine = Phase30ForensicEngine()

    # 1. Dataset Hash Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. Synthetic Path Tests (Win-Rate Sanity)
    syn_results = engine.run_synthetic_path_test()
    assert syn_results["Case_A_Immediate_TP"] == "WIN"
    assert syn_results["Case_B_Immediate_SL"] == "LOSS"
    assert syn_results["Case_C_TP_Before_SL"] == "WIN"
    assert syn_results["Case_D_SL_Before_TP"] == "LOSS"
    assert syn_results["Case_E_Ambiguous"] == "AMBIGUOUS"

    # 3. Trade Forensics & Manual P&L Reconciliation
    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + i*0.1, 100, float(1000 + i*900)) for i in range(150)]
    records, summary = engine.perform_trade_forensics("XAUUSD", candles, spec)

    assert len(records) > 0
    assert summary["reconciliation_passed"] is True
    assert summary["geometry_all_valid"] is True

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
