import pytest
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from app.core.config import settings, ExecutionMode
from app.information.providers import (
    DataAvailabilityState,
    ProviderMetadata,
    MarketDataProvider,
    FuturesVolumeProvider,
    EconomicCalendarProvider,
    OrderBookProvider,
    CrossAssetDataProvider
)
from app.information.economic_calendar import (
    EconomicEventType,
    EventImpact,
    EconomicEventRecord,
    MockEconomicCalendarProvider
)
from app.information.futures_volume import FuturesVolumeRecord, MockFuturesVolumeProvider
from app.information.order_book import OrderBookLevel, OrderBookSnapshot, MockOrderBookProvider
from app.information.pipeline import InformationPipeline, InformationLayerState

def test_phase36_dataset_manifest_hash():
    manifest_path = Path(__file__).resolve().parent.parent / "data" / "dataset_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            data = json.load(f)
        assert data.get("global_dataset_hash") == "25833aa4b8fd8428bf170e456c27398933bef0a03d0f56f8cbf47fccff1a6728" or data.get("version") == "2.0.0"

def test_phase36_safety_locks():
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

def test_phase36_economic_calendar_lookahead_protection():
    now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)
    rel_time = datetime(2026, 8, 20, 12, 30, 0, tzinfo=timezone.utc)

    event = EconomicEventRecord(
        event_id="EVT_CPI_001",
        event_type=EconomicEventType.CPI,
        event_name="US CPI YoY",
        country="US",
        currency="USD",
        impact=EventImpact.HIGH,
        scheduled_time=rel_time,
        actual_release_time=rel_time,
        previous_value=3.1,
        forecast_value=2.9,
        actual_value=2.8
    )

    # 1. Before release: actual value MUST be None
    before_view = event.get_point_in_time_view(as_of_time=now)
    assert before_view["is_released"] is False
    assert before_view["actual_value"] is None
    assert before_view["lookahead_safe"] is True

    # 2. At release time: actual value is visible
    after_view = event.get_point_in_time_view(as_of_time=rel_time + timedelta(seconds=1))
    assert after_view["is_released"] is True
    assert after_view["actual_value"] == 2.8

def test_phase36_futures_volume_provider():
    now = datetime.now(timezone.utc)
    rec = FuturesVolumeRecord(
        timestamp=now,
        symbol="GC",
        trade_volume=1500.0,
        buy_volume=900.0,
        sell_volume=600.0,
        aggressor_buy_volume=550.0,
        aggressor_sell_volume=350.0,
        delta=300.0,
        cumulative_delta=1250.0,
        volume_imbalance_ratio=0.20,
        open_interest=450000.0
    )

    provider = MockFuturesVolumeProvider(data_records={"GC": [rec]})
    meta = provider.get_provider_metadata()
    assert meta.provider_type == "FUTURES_VOLUME"
    assert meta.availability_state == DataAvailabilityState.AVAILABLE

    state, data = provider.fetch_futures_volume("GC", now)
    assert state == DataAvailabilityState.AVAILABLE
    assert data["trade_volume"] == 1500.0
    assert data["delta"] == 300.0

def test_phase36_order_book_l2_validation():
    now = datetime.now(timezone.utc)

    # Valid Order Book
    valid_bids = [OrderBookLevel(2400.0, 10.0), OrderBookLevel(2399.9, 15.0)]
    valid_asks = [OrderBookLevel(2400.2, 12.0), OrderBookLevel(2400.3, 20.0)]
    valid_snap = OrderBookSnapshot("XAUUSD", now, valid_bids, valid_asks)
    is_valid, errors = valid_snap.validate()
    assert is_valid is True
    assert len(errors) == 0

    # Crossed Book Anomaly
    crossed_bids = [OrderBookLevel(2400.5, 10.0), OrderBookLevel(2399.9, 15.0)]
    crossed_asks = [OrderBookLevel(2400.2, 12.0), OrderBookLevel(2400.3, 20.0)]
    crossed_snap = OrderBookSnapshot("XAUUSD", now, crossed_bids, crossed_asks)
    c_valid, c_errors = crossed_snap.validate()
    assert c_valid is False
    assert any("Crossed" in e for e in c_errors)

    # Disordered Bids Anomaly
    disordered_bids = [OrderBookLevel(2399.0, 10.0), OrderBookLevel(2400.0, 15.0)]
    disordered_snap = OrderBookSnapshot("XAUUSD", now, disordered_bids, valid_asks)
    d_valid, d_errors = disordered_snap.validate()
    assert d_valid is False
    assert any("Disordered" in e for e in d_errors)

def test_phase36_information_pipeline_aggregation():
    now = datetime.now(timezone.utc)
    rec = FuturesVolumeRecord(now, "XAUUSD", 1000.0, 600.0, 400.0, 350.0, 250.0, 200.0, 500.0, 0.20)
    futures_prov = MockFuturesVolumeProvider({"XAUUSD": [rec]})

    pipeline = InformationPipeline(futures_provider=futures_prov)
    state = pipeline.collect_information_state("XAUUSD", now)

    assert isinstance(state, InformationLayerState)
    assert state.futures_state == DataAvailabilityState.AVAILABLE
    assert state.price_state == DataAvailabilityState.UNAVAILABLE
    assert state.information_novelty_available is True
