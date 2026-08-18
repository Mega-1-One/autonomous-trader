from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple

@dataclass
class DatasetSplitManifest:
    train_start_ts: float
    train_end_ts: float
    train_count: int
    val_start_ts: float
    val_end_ts: float
    val_count: int
    oos_start_ts: float
    oos_end_ts: float
    oos_count: int
    is_chronological: bool
    data_leakage_detected: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class DatasetSplitter:
    """Performs strict chronological Train (60%) -> Validation (20%) -> OOS (20%) dataset splitting with zero lookahead."""

    def split_dataset(self, ticks: List[dict]) -> Tuple[List[dict], List[dict], List[dict], DatasetSplitManifest]:
        if not ticks:
            manifest = DatasetSplitManifest(0,0,0, 0,0,0, 0,0,0, True, False)
            return [], [], [], manifest

        n = len(ticks)
        idx_train = int(n * 0.60)
        idx_val = int(n * 0.80)

        train_ticks = ticks[:idx_train]
        val_ticks = ticks[idx_train:idx_val]
        oos_ticks = ticks[idx_val:]

        train_end = float(train_ticks[-1]["timestamp"]) if train_ticks else 0.0
        val_start = float(val_ticks[0]["timestamp"]) if val_ticks else 0.0
        val_end = float(val_ticks[-1]["timestamp"]) if val_ticks else 0.0
        oos_start = float(oos_ticks[0]["timestamp"]) if oos_ticks else 0.0
        oos_end = float(oos_ticks[-1]["timestamp"]) if oos_ticks else 0.0

        is_chrono = (train_end <= val_start) and (val_end <= oos_start)
        data_leakage = not is_chrono

        manifest = DatasetSplitManifest(
            train_start_ts=float(train_ticks[0]["timestamp"]) if train_ticks else 0.0,
            train_end_ts=train_end,
            train_count=len(train_ticks),
            val_start_ts=val_start,
            val_end_ts=val_end,
            val_count=len(val_ticks),
            oos_start_ts=oos_start,
            oos_end_ts=oos_end,
            oos_count=len(oos_ticks),
            is_chronological=is_chrono,
            data_leakage_detected=data_leakage
        )

        return train_ticks, val_ticks, oos_ticks, manifest
