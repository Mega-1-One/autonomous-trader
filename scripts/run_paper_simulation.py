import sys
import json
import logging
from pathlib import Path

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.execution.realtime_paper_simulation import RealtimePaperSimulationEngine

def run_paper_sim():
    engine = RealtimePaperSimulationEngine()
    if not engine.initialize():
        print("[ERROR] Could not initialize MT5 account connection.")
        return

    # If argument passed (e.g. 10), run for that duration; otherwise continuous stream
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    summary = engine.run_continuous_stream(duration_seconds=duration)
    engine.shutdown()

    out_file = Path(__file__).resolve().parent.parent / "data" / "paper_simulation_summary.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n[SUCCESS] Stream snapshot report saved to {out_file}")

if __name__ == "__main__":
    run_paper_sim()
