from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple
import numpy as np

from app.scalper.instrument import InstrumentSpecification

@dataclass
class ValidationMetrics:
    total_ticks: int
    valid_ticks: int
    rejected_ticks: int
    duplicates: int
    out_of_order: int
    min_spread_pips: float
    median_spread_pips: float
    mean_spread_pips: float
    p90_spread_pips: float
    p95_spread_pips: float
    p99_spread_pips: float
    max_spread_pips: float
    rejection_reasons: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class DataValidator:
    """Validates raw historical tick data for chronological integrity, price sanity, and spread distribution."""

    def validate_ticks(self, ticks: List[dict], spec: InstrumentSpecification) -> Tuple[List[dict], ValidationMetrics]:
        valid_ticks = []
        rejected_count = 0
        duplicates = 0
        out_of_order = 0
        rejection_reasons = {}

        last_ts = -1.0
        seen_signatures = set()
        spreads_pips = []

        pip_unit = spec.pip_size

        for t in ticks:
            ts = float(t.get("timestamp", 0.0))
            bid = float(t.get("bid", 0.0))
            ask = float(t.get("ask", 0.0))

            # 1. Price Sanity Check
            if bid <= 0 or ask <= 0 or ask < bid:
                rejected_count += 1
                rejection_reasons["invalid_price"] = rejection_reasons.get("invalid_price", 0) + 1
                continue

            # 2. Duplicate Detection
            sig = (round(ts, 3), round(bid, spec.digits), round(ask, spec.digits))
            if sig in seen_signatures:
                duplicates += 1
                rejected_count += 1
                rejection_reasons["duplicate"] = rejection_reasons.get("duplicate", 0) + 1
                continue
            seen_signatures.add(sig)

            # 3. Chronological Ordering Check
            if ts < last_ts:
                out_of_order += 1
                rejected_count += 1
                rejection_reasons["out_of_order"] = rejection_reasons.get("out_of_order", 0) + 1
                continue
            last_ts = ts

            # 4. Spread Calculation
            spread_pips = (ask - bid) / pip_unit if pip_unit > 0 else (ask - bid)
            spreads_pips.append(spread_pips)
            valid_ticks.append(t)

        arr = np.array(spreads_pips) if len(spreads_pips) > 0 else np.array([0.0])

        metrics = ValidationMetrics(
            total_ticks=len(ticks),
            valid_ticks=len(valid_ticks),
            rejected_ticks=rejected_count,
            duplicates=duplicates,
            out_of_order=out_of_order,
            min_spread_pips=round(float(np.min(arr)), 2),
            median_spread_pips=round(float(np.median(arr)), 2),
            mean_spread_pips=round(float(np.mean(arr)), 2),
            p90_spread_pips=round(float(np.percentile(arr, 90)), 2),
            p95_spread_pips=round(float(np.percentile(arr, 95)), 2),
            p99_spread_pips=round(float(np.percentile(arr, 99)), 2),
            max_spread_pips=round(float(np.max(arr)), 2),
            rejection_reasons=rejection_reasons
        )

        return valid_ticks, metrics
