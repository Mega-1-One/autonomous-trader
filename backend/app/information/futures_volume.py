from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.information.providers import FuturesVolumeProvider, DataAvailabilityState, ProviderMetadata

@dataclass
class FuturesVolumeRecord:
    timestamp: datetime
    symbol: str
    trade_volume: float
    buy_volume: float
    sell_volume: float
    aggressor_buy_volume: float
    aggressor_sell_volume: float
    delta: float
    cumulative_delta: float
    volume_imbalance_ratio: float
    open_interest: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "trade_volume": self.trade_volume,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "aggressor_buy_volume": self.aggressor_buy_volume,
            "aggressor_sell_volume": self.aggressor_sell_volume,
            "delta": round(self.delta, 2),
            "cumulative_delta": round(self.cumulative_delta, 2),
            "volume_imbalance_ratio": round(self.volume_imbalance_ratio, 4),
            "open_interest": self.open_interest
        }

class MockFuturesVolumeProvider(FuturesVolumeProvider):
    """CME / COMEX Futures Real Trade Volume and Aggressor Order Flow Feed."""

    def __init__(self, data_records: Optional[Dict[str, List[FuturesVolumeRecord]]] = None):
        self.data_records: Dict[str, List[FuturesVolumeRecord]] = data_records or {}

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            source_name="CME Market Data Feed (MDP 3.0)",
            provider_type="FUTURES_VOLUME",
            availability_state=DataAvailabilityState.AVAILABLE,
            timestamp_resolution="MILLISECOND",
            historical_depth="5_YEARS",
            realtime_capable=True,
            typical_latency_ms=15.0,
            licensing="CME_EXCHANGE_LICENSED",
            limitations=[
                "Requires direct CME licensing for live distribution",
                "Contract rollovers require continuous series construction",
                "Strictly real exchange volume; no synthetic volume estimation allowed"
            ]
        )

    def fetch_futures_volume(self, symbol: str, timestamp: datetime) -> Tuple[DataAvailabilityState, Optional[Dict[str, Any]]]:
        if symbol not in self.data_records or not self.data_records[symbol]:
            return DataAvailabilityState.UNAVAILABLE, None

        records = self.data_records[symbol]
        # Find exact or most recent prior record
        closest = None
        for r in records:
            if r.timestamp <= timestamp:
                closest = r
            else:
                break

        if closest is None:
            return DataAvailabilityState.UNAVAILABLE, None

        # Check staleness (older than 60 seconds)
        diff_sec = (timestamp - closest.timestamp).total_seconds()
        if diff_sec > 60:
            return DataAvailabilityState.STALE, closest.to_dict()

        return DataAvailabilityState.AVAILABLE, closest.to_dict()
