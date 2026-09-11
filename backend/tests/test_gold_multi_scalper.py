import pytest
from app.scalper.gold_multi_scalper import GoldMultiPositionProfitScalper

def test_gold_multi_scalper_init():
    scalper = GoldMultiPositionProfitScalper(symbol="XAUUSDm", volume=0.01, max_open_positions=5, min_profit_target_usd=0.20)
    assert scalper.symbol == "XAUUSDm"
    assert scalper.volume == 0.01
    assert scalper.max_open_positions == 5
    assert scalper.min_profit_target_usd == 0.20

def test_gold_multi_scalper_has_loss_caps():
    # Phase 1 exit-math fix: the scalper must carry a protective SL, loss cap, and max hold
    scalper = GoldMultiPositionProfitScalper(symbol="XAUUSDm", volume=0.01, max_open_positions=5, min_profit_target_usd=0.20)
    assert scalper.stop_loss_pips > 0
    assert scalper.max_loss_usd > 0
    assert scalper.max_holding_seconds > 0
