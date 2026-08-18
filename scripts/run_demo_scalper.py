import sys
import logging
from pathlib import Path

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scalper.demo_scalper_engine import MT5DemoMicroScalper

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSDm"
    direction = sys.argv[2].upper() if len(sys.argv) > 2 else "BUY"

    scalper = MT5DemoMicroScalper(target_symbol=symbol, volume=0.01)
    if scalper.initialize():
        scalper.execute_micro_scalp(direction=direction, sl_pips=5.0, tp_pips=10.0, max_hold_sec=30.0)

if __name__ == "__main__":
    main()
