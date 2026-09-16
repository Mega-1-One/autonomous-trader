import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402  (backend root + venv site-packages on sys.path)
backend_dir = _bootstrap.ensure_backend_on_path()

import logging
logging.getLogger("autotrader").setLevel(logging.ERROR)

from app.scalper.autonomous_scalper_daemon import AutonomousScalperDaemon

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSDm"
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    daemon = AutonomousScalperDaemon(
        symbol=symbol,
        max_holding_seconds=45.0,
        risk_percent=1.0,
        cooldown_seconds=10,
        max_drawdown_pct=15.0
    )

    if daemon.initialize():
        daemon.run_autonomous_loop(duration_seconds=duration)

if __name__ == "__main__":
    main()
