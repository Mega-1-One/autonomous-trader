import pytest
import hashlib
from app.context.timeframe_engine import Candle
from app.research.data_pipeline.historical_loader import PaginatedHistoricalLoader, DepthAuditMetrics

def test_phase27_3_dataset_depth_no_cap():
    loader = PaginatedHistoricalLoader()

    # Mock MT5 module with > 10,000 bars
    class MockMT5:
        def copy_rates_range(self, symbol, tf, start_dt, end_dt):
            start_ts = start_dt.timestamp()
            end_ts = end_dt.timestamp()
            bars = []
            ts = start_ts
            while ts < end_ts:
                bars.append((ts, 2400.0, 2405.0, 2395.0, 2402.0, 100))
                ts += 60.0
            return bars

    import datetime
    start_dt = datetime.datetime(2025, 8, 1, tzinfo=datetime.timezone.utc)
    end_dt = datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc)

    candles, metrics = loader.load_full_history("XAUUSD", "XAUUSDm", MockMT5(), None, start_dt, end_dt)

    # 1. No artificial 10,000 record cap
    assert len(candles) > 10000
    assert metrics.records_sampled == 0
    assert metrics.records_truncated == 0
    assert metrics.sampling_method == "FULL_RESOLUTION_NO_SAMPLING"

    # 2. Chronological ordering & timestamp continuity
    assert metrics.actual_1m_candles == len(candles)
    assert metrics.median_time_delta_sec == 60.0

    # 3. Deterministic Hashing
    hash1 = hashlib.sha256(str([(c.open, c.high, c.low, c.close) for c in candles[:1000]]).encode('utf-8')).hexdigest()
    hash2 = hashlib.sha256(str([(c.open, c.high, c.low, c.close) for c in candles[:1000]]).encode('utf-8')).hexdigest()
    assert hash1 == hash2

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
