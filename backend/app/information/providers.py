from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

class DataAvailabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    INVALID = "INVALID"
    PARTIAL = "PARTIAL"

@dataclass
class ProviderMetadata:
    source_name: str
    provider_type: str
    availability_state: DataAvailabilityState
    timestamp_resolution: str
    historical_depth: str
    realtime_capable: bool
    typical_latency_ms: float
    licensing: str
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["availability_state"] = self.availability_state.value
        return d

class MarketDataProvider(ABC):
    """Abstract interface for ingestion of multi-asset pricing data."""

    @abstractmethod
    def get_provider_metadata(self) -> ProviderMetadata:
        pass

    @abstractmethod
    def fetch_latest_tick(self, symbol: str) -> Tuple[DataAvailabilityState, Optional[Dict[str, Any]]]:
        pass

    @abstractmethod
    def fetch_candles(self, symbol: str, timeframe: str, count: int) -> Tuple[DataAvailabilityState, List[Dict[str, Any]]]:
        pass

class FuturesVolumeProvider(ABC):
    """Abstract interface for exchange-traded futures volume and aggressor order flow."""

    @abstractmethod
    def get_provider_metadata(self) -> ProviderMetadata:
        pass

    @abstractmethod
    def fetch_futures_volume(self, symbol: str, timestamp: datetime) -> Tuple[DataAvailabilityState, Optional[Dict[str, Any]]]:
        pass

class EconomicCalendarProvider(ABC):
    """Abstract interface for point-in-time macroeconomic events."""

    @abstractmethod
    def get_provider_metadata(self) -> ProviderMetadata:
        pass

    @abstractmethod
    def get_scheduled_events(self, start_time: datetime, end_time: datetime) -> Tuple[DataAvailabilityState, List[Dict[str, Any]]]:
        pass

    @abstractmethod
    def get_released_event(self, event_id: str, as_of_time: datetime) -> Tuple[DataAvailabilityState, Optional[Dict[str, Any]]]:
        pass

class OrderBookProvider(ABC):
    """Abstract interface for Level-2 order book depth."""

    @abstractmethod
    def get_provider_metadata(self) -> ProviderMetadata:
        pass

    @abstractmethod
    def get_l2_depth(self, symbol: str) -> Tuple[DataAvailabilityState, Optional[Dict[str, Any]]]:
        pass

class CrossAssetDataProvider(ABC):
    """Abstract interface for cross-asset benchmark feeds."""

    @abstractmethod
    def get_provider_metadata(self) -> ProviderMetadata:
        pass

    @abstractmethod
    def get_cross_asset_quotes(self, symbols: List[str]) -> Tuple[DataAvailabilityState, Dict[str, Dict[str, Any]]]:
        pass
