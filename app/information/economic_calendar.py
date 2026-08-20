from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.information.providers import EconomicCalendarProvider, DataAvailabilityState, ProviderMetadata

class EconomicEventType(str, Enum):
    CPI = "CPI"
    NFP = "NFP"
    FOMC = "FOMC"
    RATE_DECISION = "RATE_DECISION"
    GDP = "GDP"
    UNEMPLOYMENT = "UNEMPLOYMENT"
    PCE = "PCE"
    CENTRAL_BANK = "CENTRAL_BANK"

class EventImpact(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

@dataclass
class EconomicEventRecord:
    event_id: str
    event_type: EconomicEventType
    event_name: str
    country: str
    currency: str
    impact: EventImpact
    scheduled_time: datetime
    actual_release_time: datetime
    previous_value: Optional[float]
    forecast_value: Optional[float]
    actual_value: Optional[float]
    revision_timestamp: Optional[datetime] = None
    revised_value: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "event_name": self.event_name,
            "country": self.country,
            "currency": self.currency,
            "impact": self.impact.value,
            "scheduled_time": self.scheduled_time.isoformat(),
            "actual_release_time": self.actual_release_time.isoformat(),
            "previous_value": self.previous_value,
            "forecast_value": self.forecast_value,
            "actual_value": self.actual_value,
            "revision_timestamp": self.revision_timestamp.isoformat() if self.revision_timestamp else None,
            "revised_value": self.revised_value
        }

    def get_point_in_time_view(self, as_of_time: datetime) -> Dict[str, Any]:
        """Returns point-in-time view strictly preventing lookahead / revision leakage."""
        if as_of_time.tzinfo is None:
            as_of_time = as_of_time.replace(tzinfo=timezone.utc)
        
        rel_time = self.actual_release_time
        if rel_time.tzinfo is None:
            rel_time = rel_time.replace(tzinfo=timezone.utc)

        is_released = as_of_time >= rel_time

        view = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "event_name": self.event_name,
            "currency": self.currency,
            "impact": self.impact.value,
            "scheduled_time": self.scheduled_time.isoformat(),
            "is_released": is_released,
            "previous_value": self.previous_value,
            "forecast_value": self.forecast_value,
            "actual_value": self.actual_value if is_released else None,
            "lookahead_safe": True
        }
        return view

class MockEconomicCalendarProvider(EconomicCalendarProvider):
    """Point-in-time Macroeconomic Calendar Provider preventing future lookahead leakage."""

    def __init__(self, events: Optional[List[EconomicEventRecord]] = None):
        self.events: List[EconomicEventRecord] = events or []

    def get_provider_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            source_name="Institutional Economic Feed",
            provider_type="ECONOMIC_CALENDAR",
            availability_state=DataAvailabilityState.AVAILABLE,
            timestamp_resolution="1_SECOND",
            historical_depth="10_YEARS",
            realtime_capable=True,
            typical_latency_ms=250.0,
            licensing="COMMERCIAL_FEED",
            limitations=["Occasional unannounced schedule alterations", "Post-release revisions occur at subsequent periods"]
        )

    def get_scheduled_events(self, start_time: datetime, end_time: datetime) -> Tuple[DataAvailabilityState, List[Dict[str, Any]]]:
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        filtered = [
            e.to_dict() for e in self.events 
            if start_time <= (e.scheduled_time.replace(tzinfo=timezone.utc) if e.scheduled_time.tzinfo is None else e.scheduled_time) <= end_time
        ]
        return DataAvailabilityState.AVAILABLE, filtered

    def get_released_event(self, event_id: str, as_of_time: datetime) -> Tuple[DataAvailabilityState, Optional[Dict[str, Any]]]:
        for e in self.events:
            if e.event_id == event_id:
                return DataAvailabilityState.AVAILABLE, e.get_point_in_time_view(as_of_time)
        return DataAvailabilityState.UNAVAILABLE, None
