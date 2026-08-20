import sys
import os
import json
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
venv_site = backend_dir / "venv" / "Lib" / "site-packages"
if venv_site.exists() and str(venv_site) not in sys.path:
    sys.path.insert(0, str(venv_site))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

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
