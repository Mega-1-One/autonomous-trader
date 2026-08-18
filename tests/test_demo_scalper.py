import pytest
from app.scalper.demo_scalper_engine import MT5DemoMicroScalper

def test_scalper_engine_init():
    scalper = MT5DemoMicroScalper(target_symbol="EURUSDm", volume=0.01)
    assert scalper.symbol == "EURUSDm"
    assert scalper.volume == 0.01
