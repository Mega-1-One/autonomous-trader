import pytest
from pathlib import Path
from app.scalper.instrument import InstrumentSpecification
from app.research.data_pipeline.data_validator import DataValidator
from app.research.data_pipeline.candle_builder import DeterministicCandleBuilder
from app.research.data_pipeline.dataset_splitter import DatasetSplitter
from app.research.data_pipeline.dataset_manifest import DatasetManifestGenerator

def test_phase27_data_pipeline_full():
    spec = InstrumentSpecification.get_default_spec("XAUUSD")

    # Generate synthetic raw tick stream
    ticks = []
    for i in range(100):
        ticks.append({
            "symbol": "XAUUSD", "timestamp": 1000.0 + i*10,
            "bid": 2400.0 + i*0.1, "ask": 2400.2 + i*0.1, "last": 2400.0 + i*0.1
        })
    # Add duplicate & out of order ticks
    ticks.append(ticks[50])

    # 1. Tick Validation, Duplicates, Bid/Ask, Spread
    validator = DataValidator()
    valid_ticks, metrics = validator.validate_ticks(ticks, spec)
    assert metrics.duplicates >= 1
    assert len(valid_ticks) == 100
    assert metrics.median_spread_pips >= 0.1

    # 2. Deterministic Candle Reconstruction
    builder = DeterministicCandleBuilder()
    c1m_a = builder.build_candles("XAUUSD", "1m", valid_ticks)
    c1m_b = builder.build_candles("XAUUSD", "1m", valid_ticks)
    assert len(c1m_a) == len(c1m_b)
    assert c1m_a[0].close == c1m_b[0].close

    # 3. Chronological Train/Val/OOS Split & Leakage Protection
    splitter = DatasetSplitter()
    train_t, val_t, oos_t, split_manifest = splitter.split_dataset(valid_ticks)
    assert len(train_t) == 60
    assert len(val_t) == 20
    assert len(oos_t) == 20
    assert split_manifest.is_chronological is True
    assert split_manifest.data_leakage_detected is False

    # 4. Manifest Generation
    gen = DatasetManifestGenerator()
    manifest_path = Path(__file__).resolve().parent / "scratch_manifest.json"
    manifest = gen.generate_manifest(
        symbol_metrics={"XAUUSD": metrics},
        symbol_splits={"XAUUSD": split_manifest},
        candle_counts={"XAUUSD": {"1m": len(c1m_a)}},
        output_path=manifest_path
    )
    assert manifest["global_status"] in ["RESEARCH_READY", "PARTIALLY_READY"]
    if manifest_path.exists():
        manifest_path.unlink()

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
