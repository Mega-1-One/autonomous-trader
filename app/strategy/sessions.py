from datetime import datetime, time, timezone
from typing import Any, Dict, Optional
from app.core.config import settings

class SessionFilter:
    """Timezone-aware Trading Session Filter (UTC)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = settings.strategy_config.get("sessions", {})

        self.sessions_enabled = config.get("enabled", True)
        self.london_enabled = config.get("london", {}).get("enabled", True)
        self.london_start = time.fromisoformat(config.get("london", {}).get("start_utc", "07:00"))
        self.london_end = time.fromisoformat(config.get("london", {}).get("end_utc", "16:00"))

        self.ny_enabled = config.get("new_york", {}).get("enabled", True)
        self.ny_start = time.fromisoformat(config.get("new_york", {}).get("start_utc", "12:00"))
        self.ny_end = time.fromisoformat(config.get("new_york", {}).get("end_utc", "21:00"))

    def is_in_active_session(self, timestamp: Optional[str] = None) -> tuple[bool, str]:
        """Determines if given UTC timestamp falls inside an enabled trading session."""
        if not self.sessions_enabled or (not self.london_enabled and not self.ny_enabled):
            return True, "Always On (Scalp)"

        if timestamp:
            dt = datetime.fromisoformat(timestamp)
        else:
            dt = datetime.now(timezone.utc)

        current_time = dt.time()

        if self.london_enabled and (self.london_start <= current_time <= self.london_end):
            return True, "London Session"

        if self.ny_enabled and (self.ny_start <= current_time <= self.ny_end):
            return True, "New York Session"

        return False, "Outside Configured Trading Sessions"
