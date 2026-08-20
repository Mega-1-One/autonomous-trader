import pytest
from app.scalper.gold_multi_scalper import GoldMultiPositionProfitScalper

def test_gold_multi_scalper_init():
    scalper = GoldMultiPositionProfitScalper(symbol="XAUUSDm", volume=0.01, max_open_positions=5, min_profit_target_usd=0.20)
    assert scalper.symbol == "XAUUSDm"
    assert scalper.volume == 0.01
    assert scalper.max_open_positions == 5
    assert scalper.min_profit_target_usd == 0.20
