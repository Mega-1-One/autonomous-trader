from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple

from app.information.providers import OrderBookProvider, DataAvailabilityState, ProviderMetadata

@dataclass
class OrderBookLevel:
    price: float
    quantity: float
    order_count: Optional[int] = None

@dataclass
class OrderBookSnapshot:
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]

    def validate(self, max_stale_seconds: float = 5.0, as_of_time: Optional[datetime] = None) -> Tuple[bool, List[str]]:
        """Performs rigorous Level-2 order book sanity checks."""
        errors: List[str] = []

        if not self.bids or not self.asks:
            errors.append("Empty order book sides detected")
            return False, errors

        # 1. Negative or zero prices/quantities check
        for i, b in enumerate(self.bids):
            if b.price <= 0 or b.quantity <= 0:
                errors.append(f"Invalid negative/zero bid at level {i}: price={b.price}, qty={b.quantity}")
        for i, a in enumerate(self.asks):
            if a.price <= 0 or a.quantity <= 0:
                errors.append(f"Invalid negative/zero ask at level {i}: price={a.price}, qty={a.quantity}")

        best_bid = self.bids[0].price
        best_ask = self.asks[0].price

        # 2. Crossed Book Check
        if best_bid >= best_ask:
            errors.append(f"Crossed order book: best_bid ({best_bid}) >= best_ask ({best_ask})")

        # 3. Disordered levels check
        for i in range(len(self.bids) - 1):
            if self.bids[i].price <= self.bids[i+1].price:
                errors.append(f"Disordered bids: bid[{i}] ({self.bids[i].price}) <= bid[{i+1}] ({self.bids[i+1].price})")
        for i in range(len(self.asks) - 1):
            if self.asks[i].price >= self.asks[i+1].price:
                errors.append(f"Disordered asks: ask[{i}] ({self.asks[i].price}) >= ask[{i+1}] ({self.asks[i+1].price})")

        # 4. Duplicate price levels check
        bid_prices = [b.price for b in self.bids]
        if len(bid_prices) != len(set(bid_prices)):
            errors.append("Duplicate price levels detected in bids")
        ask_prices = [a.price for a in self.asks]
        if len(ask_prices) != len(set(ask_prices)):
            errors.append("Duplicate price levels detected in asks")

        # 5. Staleness check
        if as_of_time:
            if as_of_time.tzinfo is None:
                as_of_time = as_of_time.replace(tzinfo=timezone.utc)
            snap_ts = self.timestamp.replace(tzinfo=timezone.utc) if self.timestamp.tzinfo is None else self.timestamp
            diff = (as_of_time - snap_ts).total_seconds()
            if diff > max_stale_seconds:
                errors.append(f"Stale order book snapshot ({diff:.2f}s > {max_stale_seconds}s)")

        return len(errors) == 0, errors

    def compute_imbalance_ratio(self, depth_levels: int = 5) -> float:
        """Computes Order Book Imbalance (OBI) across top N depth levels: (Bid_Vol - Ask_Vol)/(Bid_Vol + Ask_Vol)"""
        bid_vol = sum(b.quantity for b in self.bids[:depth_levels])
        ask_vol = sum(a.quantity for a in self.asks[:depth_levels])
        total = bid_vol + ask_vol
        if total <= 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    def to_dict(self) -> Dict[str, Any]:
        best_bid = self.bids[0].price if self.bids else 0.0
        best_ask = self.asks[0].price if self.asks else 0.0
        spread = round(best_ask - best_bid, 5) if (self.bids and self.asks) else 0.0
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "order_book_imbalance_top5": round(self.compute_imbalance_ratio(5), 4),
            "bids": [{"price": b.price, "quantity": b.quantity} for b in self.bids[:10]],
            "asks": [{"price": a.price, "quantity": a.quantity} for a in self.asks[:10]]
        }

class MockOrderBookProvider(OrderBookProvider):
    """Level-2 Market Depth Feed."""

    def __init__(self, snapshots: Optional[Dict[str, OrderBookSnapshot]] = None):
        self.snapshots: Dict[str, OrderBookSnapshot] = snapshots or {}

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            source_name="Institutional L2 Depth Feed",
            provider_type="ORDER_BOOK_L2",
            availability_state=DataAvailabilityState.AVAILABLE,
            timestamp_resolution="MILLISECOND",
            historical_depth="1_YEAR",
            realtime_capable=True,
            typical_latency_ms=10.0,
            licensing="DIRECT_FEED_LICENSED",
            limitations=[
                "High network bandwidth requirement for full 10-level DOM streaming",
                "Non-displayed iceberg orders are invisible in top-of-book DOM",
                "Crossed-book anomalies must be filtered prior to state calculation"
            ]
        )

    def get_l2_depth(self, symbol: str) -> Tuple[DataAvailabilityState, Optional[Dict[str, Any]]]:
        if symbol not in self.snapshots:
            return DataAvailabilityState.UNAVAILABLE, None

        snap = self.snapshots[symbol]
        valid, errors = snap.validate()
        if not valid:
            return DataAvailabilityState.INVALID, {"errors": errors, "raw": snap.to_dict()}

        return DataAvailabilityState.AVAILABLE, snap.to_dict()
