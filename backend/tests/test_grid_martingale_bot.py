import pytest
from app.scalper.grid_martingale_bot import MT5GridMartingaleScalper

def test_grid_bot_init():
    bot = MT5GridMartingaleScalper(symbol="EURUSDm", base_volume=0.01, grid_step_pips=5.0, basket_profit_target_usd=0.20)
    assert bot.symbol == "EURUSDm"
    assert bot.base_volume == 0.01
    assert bot.grid_step_pips == 5.0
    assert bot.basket_profit_target_usd == 0.20

def test_grid_bot_has_basket_loss_cap():
    # Profitability fix: the basket must have a stop-loss so losses cannot
    # dwarf the capped basket wins, and closes must be commission-aware.
    bot = MT5GridMartingaleScalper(symbol="EURUSDm", base_volume=0.01)
    assert bot.max_basket_loss_usd > 0
    assert bot.max_basket_loss_usd <= bot.basket_profit_target_usd
    assert bot.commission_per_lot > 0
