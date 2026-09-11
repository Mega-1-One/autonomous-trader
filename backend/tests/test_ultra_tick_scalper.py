import pytest
from app.scalper.ultra_tick_scalper import UltraTickScalperEngine

def test_ultra_scalper_init():
    scalper = UltraTickScalperEngine(symbol="EURUSDm", volume=0.01, sl_pips=3.0, tp_pips=5.0)
    assert scalper.symbol == "EURUSDm"
    assert scalper.volume == 0.01
    assert scalper.sl_pips == 3.0
    assert scalper.tp_pips == 5.0
