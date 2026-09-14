import sys
import os
from pathlib import Path

# Automatically add venv site-packages to sys.path so scripts run standalone
backend_dir = Path(__file__).resolve().parent.parent
venv_site = backend_dir / "venv" / "Lib" / "site-packages"
parent_venv = backend_dir.parent / "venv" / "Lib" / "site-packages"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
if venv_site.exists() and str(venv_site) not in sys.path:
    sys.path.append(str(venv_site))
if parent_venv.exists() and str(parent_venv) not in sys.path:
    sys.path.append(str(parent_venv))

import logging
logging.getLogger("autotrader").setLevel(logging.ERROR)

from app.scalper.gold_multi_scalper import GoldMultiPositionProfitScalper

def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    scalper = GoldMultiPositionProfitScalper(
        symbol="XAUUSDm",
        volume=0.01,
        max_open_positions=10,
        min_profit_target_usd=0.15,
        stop_loss_pips=5.0,
        max_loss_usd=2.0,
        max_holding_seconds=0
    )

    if scalper.initialize():
        scalper.run_multi_scalper_loop(duration_seconds=duration)

if __name__ == "__main__":
    main()
