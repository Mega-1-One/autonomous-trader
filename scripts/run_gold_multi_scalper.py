import sys
import logging
from pathlib import Path

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scalper.gold_multi_scalper import GoldMultiPositionProfitScalper

def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    scalper = GoldMultiPositionProfitScalper(
        symbol="XAUUSDm",
        volume=0.01,
        max_open_positions=5,
        min_profit_target_usd=0.20
    )

    if scalper.initialize():
        scalper.run_multi_scalper_loop(duration_seconds=duration)

if __name__ == "__main__":
    main()
