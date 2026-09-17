import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402  (backend root + venv site-packages on sys.path)
backend_dir = _bootstrap.ensure_backend_on_path()

import logging
logging.getLogger("autotrader").setLevel(logging.ERROR)

from app.execution.realtime_paper_simulation import RealtimePaperSimulationEngine

def run_paper_sim():
    engine = RealtimePaperSimulationEngine()
    if not engine.initialize():
        print("[ERROR] Could not initialize MT5 account connection.")
        return

    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    summary = engine.run_continuous_stream(duration_seconds=duration)
    engine.shutdown()

    out_file = backend_dir / "data" / "paper_simulation_summary.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[SUCCESS] Stream snapshot report saved to {out_file}")

if __name__ == "__main__":
    run_paper_sim()
