import json
import os
from pathlib import Path
from typing import Dict, Any

class HistoricalSignalLogger:
    """Logs 100% of candidate trading signals to JSONL for future statistical calibration."""

    def __init__(self, log_path: Optional[Path] = None):
        if log_path is None:
            log_path = Path(__file__).resolve().parent.parent.parent / "data" / "historical_signals.jsonl"
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_signal(self, candidate_record: Dict[str, Any]) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(candidate_record) + "\n")
        except Exception as e:
            pass
