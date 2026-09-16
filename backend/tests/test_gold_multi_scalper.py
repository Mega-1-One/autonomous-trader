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

def test_gold_multi_scalper_loss_cap_covers_win():
    # Profitability fix: a single loss must not need many wins to cover it,
    # and the profit target must clear a round-trip cost (~$0.24 on 0.01 lot gold).
    scalper = GoldMultiPositionProfitScalper(symbol="XAUUSDm", volume=0.01)
    assert scalper.max_loss_usd <= scalper.min_profit_target_usd
    assert scalper.min_profit_target_usd >= 0.50

def test_gold_multi_scalper_net_profit_deducts_commission():
    # Close decisions must be net of commission, not gross profit+swap.
    from types import SimpleNamespace
    scalper = GoldMultiPositionProfitScalper(symbol="XAUUSDm", volume=0.01)
    pos = SimpleNamespace(profit=0.20, swap=0.0, volume=0.01)
    assert scalper._net_profit(pos) == pytest.approx(0.20 - 0.01 * 7.0)
