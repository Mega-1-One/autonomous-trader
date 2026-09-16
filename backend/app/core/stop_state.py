"""Cross-process emergency-stop sentinel (ADR-8).

State that must cross process boundaries lives in the filesystem, not in memory:
a sentinel file under STATE_DIR is written on trigger and removed on reset.
Every process (API, runner.py, bot scripts) can therefore observe the stop
state. Guarantees and limits are documented in docs/REFACTORING_ARCHITECTURE.md
(ADR-8): the sentinel blocks *new* gated order submissions in all processes and
persists across restarts; it does NOT close already-open positions and does not
stop bot event loops.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

from app.core import config
from app.core.logging import logger

SENTINEL_FILENAME = "EMERGENCY_STOP.json"


def _sentinel_path():
    return config.settings.STATE_DIR / SENTINEL_FILENAME


def trigger(reason: str) -> None:
    """Write the stop sentinel so every process can see the stop."""
    path = _sentinel_path()
    payload = {
        "reason": reason,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        os.makedirs(config.settings.STATE_DIR, exist_ok=True)
        # Write to a temp file then rename for an atomic-enough replace on all
        # platforms; failure to write is logged loudly but does not crash the
        # calling engine (the in-memory flag is still set by the caller).
        fd, tmp_path = tempfile.mkstemp(dir=str(config.settings.STATE_DIR), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except Exception as exc:
        logger.error(f"Failed to write emergency-stop sentinel at {path}: {exc}")


def reset() -> None:
    """Remove the stop sentinel (cross-process reset)."""
    path = _sentinel_path()
    try:
        if path.exists():
            os.unlink(path)
    except Exception as exc:
        logger.error(f"Failed to remove emergency-stop sentinel at {path}: {exc}")


def is_active() -> Optional[str]:
    """Return the stop reason if the sentinel file exists, else None.

    Missing, malformed, or unreadable sentinel content is handled safely: a
    missing file means no stop; a malformed file is treated as active (fail
    safe) unless it is empty.
    """
    path = _sentinel_path()
    try:
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            reason = data.get("reason")
            return reason if reason else "Emergency stop sentinel present"
        except (ValueError, OSError):
            # File exists but is malformed/unreadable — treat as active.
            return "Emergency stop sentinel present (unreadable)"
    except OSError as exc:
        logger.error(f"Failed to stat emergency-stop sentinel at {path}: {exc}")
        # If we cannot even stat the file, fail safe (treat as active) only if
        # the error is not a simple absence, which is handled above.
        return "Emergency stop sentinel present (inaccessible)"
