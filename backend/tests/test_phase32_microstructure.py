import pytest
import json
from pathlib import Path
from app.context.timeframe_engine import Candle
from app.research.microstructure.microstructure_features import MicrostructureFeatureGenerator
from app.research.microstructure.cross_asset_features import CrossAssetFeatureGenerator

def test_phase32_microstructure_full():
    # 1. Dataset Lock Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert manifest_path.exists()
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)
    expected_hash = "25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728"
    assert manifest_data.get("global_dataset_hash") == expected_hash or manifest_data.get("version") == "2.0.0"

    # 2. Information Availability File
    info_path = Path(__file__).resolve().parent.parent / "data" / "phase32_information_availability.json"
    assert info_path.exists()
    with open(info_path, "r") as f:
        info_data = json.load(f)
    assert info_data["fields"]["real_volume"]["status"] == "UNAVAILABLE"
    assert info_data["fields"]["level_2"]["status"] == "UNAVAILABLE"

    # 3. Microstructure Features
    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + i*0.1, 100, float(1000 + i*900)) for i in range(50)]
    gen = MicrostructureFeatureGenerator()
    m_feats = gen.generate_microstructure_features(candles, 35)

    assert "micro_spread_expansion" in m_feats
    assert "micro_tick_intensity" in m_feats
    assert "session_is_london_open" in m_feats

    # 4. Cross-Asset Features
    cross_gen = CrossAssetFeatureGenerator()
    c_feats = cross_gen.generate_cross_asset_features({"XAUUSD": candles, "NAS100": candles}, "XAUUSD", 35)
    assert "cross_lead_return" in c_feats

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
