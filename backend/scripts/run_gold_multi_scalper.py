import sys
import os
from pathlib import Path

# Automatically add venv site-packages to sys.path so scripts run standalone
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: E402  (backend root + venv site-packages on sys.path)
backend_dir = _bootstrap.ensure_backend_on_path()

import logging
logging.getLogger("autotrader").setLevel(logging.ERROR)

from app.scalper.gold_multi_scalper import GoldMultiPositionProfitScalper

def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    scalper = GoldMultiPositionProfitScalper(
        symbol="XAUUSDm",
        volume=0.01,
        take_profit_pips=15.0,
        min_profit_target_usd=0.60,
        stop_loss_pips=5.0,
        max_loss_usd=0.50,
        max_holding_seconds=120.0
    )

    if scalper.initialize():
        scalper.run_multi_scalper_loop(duration_seconds=duration)

if __name__ == "__main__":
    main()
