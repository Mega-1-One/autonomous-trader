import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, List

from app.research.data_pipeline.data_validator import ValidationMetrics
from app.research.data_pipeline.dataset_splitter import DatasetSplitManifest

class DatasetManifestGenerator:
    """Generates machine-readable dataset_manifest.json with deterministic SHA256 dataset hash."""

    def generate_manifest(
        self,
        symbol_metrics: Dict[str, ValidationMetrics],
        symbol_splits: Dict[str, DatasetSplitManifest],
        candle_counts: Dict[str, Dict[str, int]],
        output_path: Path
    ) -> Dict[str, Any]:
        manifest_data = {
            "version": "2.0.0",
            "global_status": "READY_FOR_PHASE_28",
            "symbols": {}
        }

        all_ready = True

        for sym, val_m in symbol_metrics.items():
            split_m = symbol_splits.get(sym)
            c_cnts = candle_counts.get(sym, {})

            duration_days = round((split_m.oos_end_ts - split_m.train_start_ts) / 86400.0, 1) if split_m else 0.0
            quality_score = round(val_m.valid_ticks / max(1, val_m.total_ticks), 4)

            is_ready = (quality_score >= 0.95 and not split_m.data_leakage_detected and duration_days >= 300.0) if split_m else False
            if not is_ready:
                all_ready = False

            # Generate deterministic SHA256 dataset hash for symbol
            raw_hash_str = f"{sym}_{val_m.total_ticks}_{val_m.valid_ticks}_{split_m.train_start_ts}_{split_m.oos_end_ts}"
            sym_hash = hashlib.sha256(raw_hash_str.encode('utf-8')).hexdigest()

            manifest_data["symbols"][sym] = {
                "total_ticks": val_m.total_ticks,
                "valid_ticks": val_m.valid_ticks,
                "rejected_ticks": val_m.rejected_ticks,
                "rejection_reasons": val_m.rejection_reasons,
                "duplicates": val_m.duplicates,
                "duration_days": duration_days,
                "candles": c_cnts,
                "spread_statistics": {
                    "min_pips": val_m.min_spread_pips,
                    "median_pips": val_m.median_spread_pips,
                    "mean_pips": val_m.mean_spread_pips,
                    "p90_pips": val_m.p90_spread_pips,
                    "p95_pips": val_m.p95_spread_pips,
                    "p99_pips": val_m.p99_spread_pips,
                    "max_pips": val_m.max_spread_pips
                },
                "data_quality_score": quality_score,
                "chronological_split": split_m.to_dict() if split_m else {},
                "leakage_status": "PASSED" if not split_m.data_leakage_detected else "FAILED",
                "dataset_hash": sym_hash,
                "validation_status": "PASS" if is_ready else "FAIL"
            }

        global_str = json.dumps(manifest_data["symbols"], sort_keys=True)
        manifest_data["global_dataset_hash"] = hashlib.sha256(global_str.encode('utf-8')).hexdigest()
        manifest_data["global_status"] = "READY_FOR_PHASE_28" if all_ready else "PARTIALLY_READY"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(manifest_data, f, indent=2)

        return manifest_data
