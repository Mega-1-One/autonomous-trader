import pytest
import json
from pathlib import Path
from app.context.timeframe_engine import Candle
from app.research.macro_futures.macro_futures_engine import Phase37MacroFuturesEngine, MacroEventEngine, FuturesVolumeEngine

def test_phase37_macro_futures_full():
    engine = Phase37MacroFuturesEngine()

    # 1. Dataset Hash Lock Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert engine.verify_dataset_hash(manifest_path) is True

    # 2. Macro Event & Futures Volume Feature Generation
    m_engine = MacroEventEngine()
    v_engine = FuturesVolumeEngine()

    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + i*0.1, 100, float(1000 + i*900)) for i in range(50)]
    m_feats = m_engine.generate_macro_features(candles, 35)
    v_feats = v_engine.generate_futures_volume_features(candles, 35)

    assert "macro_nfp_window" in m_feats
    assert "cme_vol_surge" in v_feats

    # 3. Benjamini-Hochberg FDR Correction
    raw_ps = [0.01, 0.05, 0.10, 0.50]
    adj_ps, is_sigs = engine.compute_fdr_correction(raw_ps)
    assert len(adj_ps) == 4

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
