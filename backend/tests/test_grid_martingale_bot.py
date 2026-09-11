import pytest
from app.scalper.grid_martingale_bot import MT5GridMartingaleScalper

def test_grid_bot_init():
    bot = MT5GridMartingaleScalper(symbol="EURUSDm", base_volume=0.01, grid_step_pips=5.0, basket_profit_target_usd=0.20)
    assert bot.symbol == "EURUSDm"
    assert bot.base_volume == 0.01
    assert bot.grid_step_pips == 5.0
    assert bot.basket_profit_target_usd == 0.20
