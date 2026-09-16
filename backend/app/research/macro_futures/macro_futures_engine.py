import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple
import numpy as np

from app.context.timeframe_engine import Candle

@dataclass
class MacroFuturesMetrics:
    feature_name: str
    symbol: str
    horizon: str
    sample_size: int
    pearson_r: float
    raw_p_value: float
    fdr_adjusted_p: float
    is_fdr_significant: bool
    train_ic: float
    val_ic: float
    oos_ic: float
    oos_net_expectancy: float
    classification: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class MacroEventEngine:
    """Evaluates macroeconomic news shock timestamps (CPI, NFP, FOMC) and publication lag."""

    EVENTS = ["CPI_RELEASE", "NFP_RELEASE", "FOMC_DECISION", "PCE_RELEASE"]

    def generate_macro_features(self, candles: List[Candle], idx: int) -> Dict[str, float]:
        if idx < 30:
            return {}

        c_curr = candles[idx]
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(c_curr.timestamp, tz=timezone.utc)

        # Macro shock proxy (First Friday of month at 13:30 UTC for NFP, 12th-15th for CPI)
        is_nfp_window = 1.0 if (dt.weekday() == 4 and dt.day <= 7 and dt.hour == 13) else 0.0
        is_cpi_window = 1.0 if (12 <= dt.day <= 15 and dt.hour == 13) else 0.0
        is_fomc_window = 1.0 if (dt.weekday() == 2 and 14 <= dt.day <= 21 and dt.hour == 18) else 0.0

        return {
            "macro_nfp_window": is_nfp_window,
            "macro_cpi_window": is_cpi_window,
            "macro_fomc_window": is_fomc_window
        }

class FuturesVolumeEngine:
    """Evaluates CME COMEX Gold Futures volume surge and open interest changes."""

    def generate_futures_volume_features(self, candles: List[Candle], idx: int) -> Dict[str, float]:
        if idx < 30:
            return {}

        c_curr = candles[idx]
        past_vols = [c.volume for c in candles[idx-30:idx+1]]

        vol_avg = float(np.mean(past_vols[-14:]))
        vol_surge = float(c_curr.volume) / (vol_avg + 1e-6)
        vol_accel = vol_surge - (past_vols[-2] / (vol_avg + 1e-6))

        return {
            "cme_vol_surge": vol_surge,
            "cme_vol_accel": vol_accel
        }

class Phase37MacroFuturesEngine:
    """Executes Phase 37 Macro Shock & CME Futures Volume Edge Discovery."""

    TARGET_DATASET_HASH = "25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728"

    def verify_dataset_hash(self, manifest_path: Path) -> bool:
        from app.research.common.dataset_hash import verify_dataset_hash
        return verify_dataset_hash(manifest_path, self.TARGET_DATASET_HASH)

    def compute_fdr_correction(self, raw_p_values: List[float], alpha: float = 0.05) -> Tuple[List[float], List[bool]]:
        """Benjamini-Hochberg FDR procedure (shared impl)."""
        from app.research.common.statistical_tests import compute_fdr_correction
        return compute_fdr_correction(raw_p_values, alpha=alpha)
