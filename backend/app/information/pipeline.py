from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.information.providers import (
    DataAvailabilityState,
    MarketDataProvider,
    FuturesVolumeProvider,
    EconomicCalendarProvider,
    OrderBookProvider,
    CrossAssetDataProvider
)

@dataclass
class InformationLayerState:
    timestamp: str
    symbol: str
    price_state: DataAvailabilityState
    futures_state: DataAvailabilityState
    macro_state: DataAvailabilityState
    l2_state: DataAvailabilityState
    cross_asset_state: DataAvailabilityState
    information_novelty_available: bool
    context_data: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "price_state": self.price_state.value,
            "futures_state": self.futures_state.value,
            "macro_state": self.macro_state.value,
            "l2_state": self.l2_state.value,
            "cross_asset_state": self.cross_asset_state.value,
            "information_novelty_available": self.information_novelty_available,
            "context_data": self.context_data
        }

class InformationPipeline:
    """Modular Information Ingestion & Routing Layer: Market Data -> Information Layer -> Market State -> Signal -> Risk -> Execution."""

    def __init__(
        self,
        market_data_provider: Optional[MarketDataProvider] = None,
        futures_provider: Optional[FuturesVolumeProvider] = None,
        economic_provider: Optional[EconomicCalendarProvider] = None,
        order_book_provider: Optional[OrderBookProvider] = None,
        cross_asset_provider: Optional[CrossAssetDataProvider] = None
    ):
        self.market_data_provider = market_data_provider
        self.futures_provider = futures_provider
        self.economic_provider = economic_provider
        self.order_book_provider = order_book_provider
        self.cross_asset_provider = cross_asset_provider

    def collect_information_state(self, symbol: str, as_of_time: Optional[datetime] = None) -> InformationLayerState:
        now = as_of_time or datetime.now(timezone.utc)
        now_str = now.isoformat()

        # 1. Price Data
        p_state = DataAvailabilityState.UNAVAILABLE
        p_data = None
        if self.market_data_provider:
            p_state, p_data = self.market_data_provider.fetch_latest_tick(symbol)

        # 2. Futures Volume
        f_state = DataAvailabilityState.UNAVAILABLE
        f_data = None
        if self.futures_provider:
            f_state, f_data = self.futures_provider.fetch_futures_volume(symbol, now)

        # 3. Macroeconomic Events
        m_state = DataAvailabilityState.UNAVAILABLE
        m_data = None
        if self.economic_provider:
            m_state, m_data = self.economic_provider.get_scheduled_events(now, now)

        # 4. L2 Order Book
        l2_state = DataAvailabilityState.UNAVAILABLE
        l2_data = None
        if self.order_book_provider:
            l2_state, l2_data = self.order_book_provider.get_l2_depth(symbol)

        # 5. Cross-Asset Benchmark
        ca_state = DataAvailabilityState.UNAVAILABLE
        ca_data = None
        if self.cross_asset_provider:
            ca_state, ca_data = self.cross_asset_provider.get_cross_asset_quotes(["DX", "US10Y", "SPX"])

        has_novelty = (
            f_state == DataAvailabilityState.AVAILABLE or 
            m_state == DataAvailabilityState.AVAILABLE or 
            l2_state == DataAvailabilityState.AVAILABLE
        )

        return InformationLayerState(
            timestamp=now_str,
            symbol=symbol,
            price_state=p_state,
            futures_state=f_state,
            macro_state=m_state,
            l2_state=l2_state,
            cross_asset_state=ca_state,
            information_novelty_available=has_novelty,
            context_data={
                "price": p_data,
                "futures": f_data,
                "macro": m_data,
                "l2": l2_data,
                "cross_asset": ca_data
            }
        )
