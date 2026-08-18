import sys
import logging
from pathlib import Path

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scalper.grid_martingale_bot import MT5GridMartingaleScalper

def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSDm"
    direction = sys.argv[2].upper() if len(sys.argv) > 2 else "BUY"

    bot = MT5GridMartingaleScalper(
        symbol=symbol,
        base_volume=0.01,
        grid_step_pips=5.0,
        lot_multiplier=1.5,
        max_grid_orders=3,
        basket_profit_target_usd=0.20,
        max_drawdown_pct=20.0
    )

    if bot.initialize():
        bot.run_grid_cycle(direction=direction, max_cycle_sec=45)

if __name__ == "__main__":
    main()
