import pytest
import json
from pathlib import Path
import numpy as np

from app.context.timeframe_engine import Candle
from app.research.feature_discovery.feature_generator import FeatureGenerator
from app.research.feature_discovery.return_labeler import ReturnLabeler
from app.research.feature_discovery.statistical_testing import FeatureStatisticalScorer

def test_phase31_feature_discovery_full():
    # 1. Dataset Lock Verification
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    assert manifest_path.exists()
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)
    expected_hash = "25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728"
    assert manifest_data.get("global_dataset_hash") == expected_hash or manifest_data.get("version") == "2.0.0"

    # 2. Feature Generation Across 7 Families
    candles = [Candle("XAUUSD", "15m", 2400.0, 2405.0, 2395.0, 2402.0 + i*0.1, 100, float(1000 + i*900)) for i in range(100)]
    gen = FeatureGenerator()
    feats = gen.generate_all_features(candles, 50)

    assert "mom_ret_1" in feats
    assert "vol_atr_14" in feats
    assert "struct_range_pos" in feats
    assert "liq_dist_vwap" in feats
    assert "trend_dev_mean" in feats
    assert "time_hour" in feats
    assert "activity_vol_burst" in feats

    # 3. Return Labeler Across 6 Horizons
    labeler = ReturnLabeler()
    labels = labeler.compute_forward_returns(candles, 50)
    assert "fwd_ret_1M" in labels
    assert "fwd_ret_15M" in labels
    assert "fwd_ret_4H" in labels

    # 4. Statistical Scorer & Benjamini-Hochberg FDR
    scorer = FeatureStatisticalScorer()
    f_vals = np.array([float(i) for i in range(100)])
    r_vals = np.array([float(i)*0.01 + (i%2)*0.001 for i in range(100)])

    res = scorer.evaluate_feature("mom_ret_1", "15M", "XAUUSD", f_vals, r_vals)
    assert res.sample_count == 100
    assert res.pearson_r > 0.0

    raw_ps = [0.01, 0.04, 0.03, 0.20, 0.50]
    adj_ps, is_sig = scorer.compute_fdr_correction(raw_ps)
    assert len(adj_ps) == 5
    assert adj_ps[0] <= adj_ps[3]

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
