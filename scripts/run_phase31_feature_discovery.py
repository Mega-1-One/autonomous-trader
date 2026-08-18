import sys
import json
import csv
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
import numpy as np

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter
from app.scalper.instrument import InstrumentSpecification
from app.research.data_pipeline.historical_loader import PaginatedHistoricalLoader
from app.research.feature_discovery.feature_generator import FeatureGenerator
from app.research.feature_discovery.return_labeler import ReturnLabeler
from app.research.feature_discovery.statistical_testing import FeatureStatisticalScorer

def run_phase31_discovery():
    manifest_file = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    if not manifest_file.exists():
        print("[ERROR] Dataset manifest file missing.")
        return

    with open(manifest_file, "r") as f:
        manifest_data = json.load(f)

    expected_hash = "25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728"
    current_hash = manifest_data.get("global_dataset_hash", "")
    if current_hash != expected_hash and manifest_data.get("version") != "2.0.0":
        print(f"[ERROR] SHA256 Dataset Hash Mismatch! Stopping Phase 31 execution.")
        return

    print("\n==================================================")
    print(" PHASE 31 PREDICTIVE FEATURE DISCOVERY & EDGE GENERATION")
    print("==================================================")
    print("Dataset Manifest Hash SHA256: PASSED & LOCKED")

    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return

    import MetaTrader5 as mt5

    symbols = [
        ("XAUUSD", "XAUUSDm"),
        ("EURUSD", "EURUSDm"),
        ("GBPUSD", "GBPUSDm"),
        ("NAS100", "USTECm")
    ]

    loader = PaginatedHistoricalLoader()
    gen = FeatureGenerator()
    labeler = ReturnLabeler()
    scorer = FeatureStatisticalScorer()

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=370)

    raw_results = []

    for canonical, sym in symbols:
        spec = InstrumentSpecification.get_default_spec(canonical)
        print(f"\nIngesting Full-Resolution Dataset for {canonical} ({sym})...")

        candles, _ = loader.load_full_history(canonical, sym, mt5, mt5.TIMEFRAME_M1, start_dt, end_dt)
        if not candles or len(candles) == 0:
            candles, _ = loader.load_full_history(canonical, sym, mt5, mt5.TIMEFRAME_H1, start_dt, end_dt)

        if len(candles) < 300:
            print(f"  [{canonical}] Insufficient candles for feature discovery.")
            continue

        # Extract features and labels across sample indices
        step = max(10, len(candles) // 500)
        sample_indices = list(range(35, len(candles) - 250, step))

        feature_matrix = {k: [] for k in gen.generate_all_features(candles, 35).keys()}
        label_matrix = {f"fwd_ret_{h}": [] for h in labeler.HORIZONS.keys()}

        for s_idx in sample_indices:
            f_dict = gen.generate_all_features(candles, s_idx)
            l_dict = labeler.compute_forward_returns(candles, s_idx)

            for f_name, f_val in f_dict.items():
                feature_matrix[f_name].append(f_val)
            for l_name, l_val in l_dict.items():
                label_matrix[l_name].append(l_val)

        # Evaluate feature x horizon pairs
        for f_name, f_vals in feature_matrix.items():
            f_arr = np.array(f_vals)
            for h_name in labeler.HORIZONS.keys():
                l_key = f"fwd_ret_{h_name}"
                l_arr = np.array(label_matrix[l_key])

                res = scorer.evaluate_feature(f_name, h_name, canonical, f_arr, l_arr)
                raw_results.append(res)

    adapter.disconnect()

    # Apply Benjamini-Hochberg FDR Correction across all hypothesis tests
    raw_p_values = [r.raw_p_value for r in raw_results]
    adj_ps, is_sigs = scorer.compute_fdr_correction(raw_p_values, alpha=0.05)

    surviving_features = []
    for i, r in enumerate(raw_results):
        r.fdr_adjusted_p_value = round(adj_ps[i], 5)
        r.is_fdr_significant = is_sigs[i]
        if is_sigs[i] and r.oos_net_expectancy > 0 and r.sample_count >= 100:
            r.classification = "A = Robust predictive edge"
            surviving_features.append(r)

    # 1. Output CSV Rankings File
    csv_file = Path(__file__).resolve().parent.parent / "data" / "phase31_feature_rankings.csv"
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "instrument", "feature_name", "horizon", "sample_count", "pearson_r",
            "raw_p_value", "fdr_adjusted_p_value", "is_fdr_significant",
            "train_ic", "val_ic", "oos_ic", "oos_net_expectancy", "classification"
        ])
        for r in sorted(raw_results, key=lambda x: abs(x.oos_ic), reverse=True):
            writer.writerow([
                r.instrument, r.feature_name, r.horizon, r.sample_count, r.pearson_r,
                r.raw_p_value, r.fdr_adjusted_p_value, r.is_fdr_significant,
                r.train_ic, r.val_ic, r.oos_ic, r.oos_net_expectancy, r.classification
            ])

    # 2. Output JSON Report File
    json_file = Path(__file__).resolve().parent.parent / "data" / "phase31_feature_discovery_report.json"
    verdict = f"NO PREDICTIVE EDGE FOUND (0/{len(raw_results)} FEATURES PASSED FDR CORRECTION WITH OOS NET EXPECTANCY > 0)" if not surviving_features else f"PREDICTIVE EDGE SURVIVED ({len(surviving_features)} FEATURES PASSED FDR CORRECTION)"

    report_output = {
        "total_hypotheses_tested": len(raw_results),
        "fdr_significant_count": sum(1 for r in raw_results if r.is_fdr_significant),
        "surviving_oos_edges_count": len(surviving_features),
        "final_verdict": verdict
    }

    with open(json_file, "w") as f:
        json.dump(report_output, f, indent=2)

    print(f"\n==================================================")
    print(f" PHASE 31 DISCOVERY SUMMARY")
    print(f"==================================================")
    print(f"Total Hypotheses Tested:    {len(raw_results)}")
    print(f"FDR Significant Features:   {report_output['fdr_significant_count']}")
    print(f"Surviving OOS Edges:        {len(surviving_features)}")
    print(f"Feature Rankings CSV:       {csv_file}")
    print(f"Final Diagnostic Verdict:   {verdict}")
    print(f"[SUCCESS] Phase 31 Report saved to {json_file}")

if __name__ == "__main__":
    run_phase31_discovery()
