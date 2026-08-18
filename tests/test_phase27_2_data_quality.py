import pytest
import hashlib
from pathlib import Path
from app.scalper.instrument import InstrumentSpecification
from app.research.data_pipeline.data_validator import DataValidator
from app.research.data_pipeline.candle_builder import DeterministicCandleBuilder
from app.research.data_pipeline.dataset_splitter import DatasetSplitter
from app.research.data_pipeline.dataset_manifest import DatasetManifestGenerator

def test_phase27_2_full_quality_gate():
    spec = InstrumentSpecification.get_default_spec("XAUUSD")

    # Generate synthetic full tick stream
    ticks = []
    for i in range(200):
        ticks.append({
            "symbol": "XAUUSD", "timestamp": 100000.0 + i*10,
            "bid": 2400.0 + i*0.1, "ask": 2400.2 + i*0.1, "last": 2400.0 + i*0.1
        })
    # Add duplicate tick
    ticks.append(ticks[50])

    # 1. Historical Date Coverage & Duplicate / Invalid Bid/Ask Detection
    validator = DataValidator()
    valid_ticks, metrics = validator.validate_ticks(ticks, spec)
    assert metrics.duplicates >= 1
    assert len(valid_ticks) == 200
    assert metrics.median_spread_pips >= 0.1

    # 2. Deterministic Candle Reconstruction & Hash Determinism
    builder = DeterministicCandleBuilder()
    c1m_run1 = builder.build_candles("XAUUSD", "1m", valid_ticks)
    c1m_run2 = builder.build_candles("XAUUSD", "1m", valid_ticks)
    assert len(c1m_run1) == len(c1m_run2)

    hash1 = hashlib.sha256(str([(c.open, c.high, c.low, c.close) for c in c1m_run1]).encode('utf-8')).hexdigest()
    hash2 = hashlib.sha256(str([(c.open, c.high, c.low, c.close) for c in c1m_run2]).encode('utf-8')).hexdigest()
    assert hash1 == hash2

    # 3. Chronological Train/Val/OOS Split Isolation & Zero Lookahead
    splitter = DatasetSplitter()
    train_t, val_t, oos_t, split_manifest = splitter.split_dataset(valid_ticks)
    assert len(train_t) == 120
    assert len(val_t) == 40
    assert len(oos_t) == 40
    assert split_manifest.is_chronological is True
    assert split_manifest.data_leakage_detected is False

    # 4. Manifest Generation & Global Hash
    gen = DatasetManifestGenerator()
    manifest_path = Path(__file__).resolve().parent / "scratch_phase27_2_manifest.json"
    manifest = gen.generate_manifest(
        symbol_metrics={"XAUUSD": metrics},
        symbol_splits={"XAUUSD": split_manifest},
        candle_counts={"XAUUSD": {"1m": len(c1m_run1)}},
        output_path=manifest_path
    )
    assert "global_dataset_hash" in manifest
    assert manifest["global_status"] in ["READY_FOR_PHASE_28", "PARTIALLY_READY"]

    if manifest_path.exists():
        manifest_path.unlink()

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
