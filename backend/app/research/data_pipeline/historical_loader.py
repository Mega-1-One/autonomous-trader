from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone, timedelta
import numpy as np

from app.context.timeframe_engine import Candle
from app.scalper.instrument import InstrumentSpecification

@dataclass
class DepthAuditMetrics:
    symbol: str
    broker_symbol: str
    start_timestamp: float
    end_timestamp: float
    calendar_days: float
    trading_days: int
    raw_records_retrieved: int
    raw_records_valid: int
    raw_records_rejected: int
    records_sampled: int
    records_truncated: int
    sampling_method: str
    expected_1m_candles: int
    actual_1m_candles: int
    expected_5m_candles: int
    actual_5m_candles: int
    expected_15m_candles: int
    actual_15m_candles: int
    expected_1h_candles: int
    actual_1h_candles: int
    expected_4h_candles: int
    actual_4h_candles: int
    median_time_delta_sec: float
    p95_time_delta_sec: float
    max_time_delta_sec: float
    legitimate_weekend_gaps: int
    unexplained_missing_gaps: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class PaginatedHistoricalLoader:
    """Historical Loader providing full-resolution batch pagination without artificial caps."""

    def load_full_history(
        self,
        symbol: str,
        broker_symbol: str,
        mt5_module: Any,
        timeframe_mt5: Any,
        start_dt: datetime,
        end_dt: datetime
    ) -> Tuple[List[Candle], DepthAuditMetrics]:
        # Batch pagination by month to avoid MT5 memory timeouts
        all_bars = []
        curr_start = start_dt

        while curr_start < end_dt:
            curr_end = min(end_dt, curr_start + timedelta(days=60))
            rates = mt5_module.copy_rates_range(broker_symbol, timeframe_mt5, curr_start, curr_end)
            if rates is not None and len(rates) > 0:
                all_bars.extend(rates)
            curr_start = curr_end

        if not all_bars:
            metrics = DepthAuditMetrics(
                symbol=symbol, broker_symbol=broker_symbol, start_timestamp=0.0, end_timestamp=0.0,
                calendar_days=0.0, trading_days=0, raw_records_retrieved=0, raw_records_valid=0,
                raw_records_rejected=0, records_sampled=0, records_truncated=0, sampling_method="NONE",
                expected_1m_candles=0, actual_1m_candles=0, expected_5m_candles=0, actual_5m_candles=0,
                expected_15m_candles=0, actual_15m_candles=0, expected_1h_candles=0, actual_1h_candles=0,
                expected_4h_candles=0, actual_4h_candles=0, median_time_delta_sec=0.0, p95_time_delta_sec=0.0,
                max_time_delta_sec=0.0, legitimate_weekend_gaps=0, unexplained_missing_gaps=0
            )
            return [], metrics

        # Sort and deduplicate bars
        unique_bars_dict = {}
        for b in all_bars:
            ts = float(b[0])
            unique_bars_dict[ts] = b

        sorted_ts = sorted(unique_bars_dict.keys())
        valid_bars = [unique_bars_dict[ts] for ts in sorted_ts]

        start_ts = sorted_ts[0]
        end_ts = sorted_ts[-1]
        calendar_days = round((end_ts - start_ts) / 86400.0, 1)

        # Reconstruct candles
        candles = [
            Candle(
                symbol=symbol, timeframe="1m", open=float(b[1]), high=float(b[2]),
                low=float(b[3]), close=float(b[4]), volume=int(b[5]), timestamp=float(b[0])
            ) for b in valid_bars
        ]

        # Calculate continuity statistics
        deltas = np.diff(sorted_ts) if len(sorted_ts) > 1 else np.array([60.0])
        median_delta = float(np.median(deltas)) if len(deltas) > 0 else 60.0
        p95_delta = float(np.percentile(deltas, 95)) if len(deltas) > 0 else 60.0
        max_delta = float(np.max(deltas)) if len(deltas) > 0 else 60.0

        # Gap classification: gaps > 48h (172800s) are weekend/session closures
        weekend_gaps = int(np.sum((deltas >= 170000.0) & (deltas <= 260000.0)))
        unexplained_gaps = int(np.sum(deltas > 260000.0))

        trading_days = max(1, int(calendar_days * (5.0 / 7.0)))

        metrics = DepthAuditMetrics(
            symbol=symbol,
            broker_symbol=broker_symbol,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            calendar_days=calendar_days,
            trading_days=trading_days,
            raw_records_retrieved=len(all_bars),
            raw_records_valid=len(valid_bars),
            raw_records_rejected=len(all_bars) - len(valid_bars),
            records_sampled=0,
            records_truncated=0,
            sampling_method="FULL_RESOLUTION_NO_SAMPLING",
            expected_1m_candles=trading_days * 1440,
            actual_1m_candles=len(valid_bars),
            expected_5m_candles=trading_days * 288,
            actual_5m_candles=len(valid_bars) // 5,
            expected_15m_candles=trading_days * 96,
            actual_15m_candles=len(valid_bars) // 15,
            expected_1h_candles=trading_days * 24,
            actual_1h_candles=len(valid_bars) // 60,
            expected_4h_candles=trading_days * 6,
            actual_4h_candles=len(valid_bars) // 240,
            median_time_delta_sec=round(median_delta, 1),
            p95_time_delta_sec=round(p95_delta, 1),
            max_time_delta_sec=round(max_delta, 1),
            legitimate_weekend_gaps=weekend_gaps,
            unexplained_missing_gaps=unexplained_gaps
        )

        return candles, metrics
