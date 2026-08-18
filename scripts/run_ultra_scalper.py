import sys
import logging
from pathlib import Path

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scalper.ultra_tick_scalper import UltraTickScalperEngine

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSDm"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    scalper = UltraTickScalperEngine(symbol=symbol, volume=0.01, sl_pips=3.0, tp_pips=5.0)
    if scalper.initialize():
        scalper.run_ultra_scalping_session(total_scalps_to_execute=count)

if __name__ == "__main__":
    main()
