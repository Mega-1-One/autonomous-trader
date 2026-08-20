import pytest
from app.core.config import settings, ExecutionMode
from app.research.phase39_forward_engine import Phase39ForwardEngine, ForwardTradeResult

def test_phase39_safety_isolation():
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False

def test_phase39_configuration_hash_freeze():
    engine = Phase39ForwardEngine()
    h1 = engine.configuration_hash
    h2 = engine.generate_configuration_hash()
    assert h1 == h2
    assert len(h1) == 64

def test_phase39_forward_simulation_and_metrics():
    engine = Phase39ForwardEngine()

    # Simulate 10 winning trades and 10 losing trades
    for i in range(10):
        engine.simulate_forward_trade(
            trade_id=f"FWD_WIN_{i}",
            instrument="XAUUSD",
            direction="LONG",
            session="LONDON",
            regime="TRENDING",
            entry_price=2400.0 + i,
            sl_pips=5.0,
            tp_pips=2.0,
            volume=0.05,
            win=True
        )

    for i in range(10):
        engine.simulate_forward_trade(
            trade_id=f"FWD_LOSS_{i}",
            instrument="XAUUSD",
            direction="LONG",
            session="LONDON",
            regime="TRENDING",
            entry_price=2400.0 + i,
            sl_pips=5.0,
            tp_pips=2.0,
            volume=0.05,
            win=False
        )

    stats = engine.compute_summary_statistics()
    assert stats["total_trades"] == 20
    assert stats["wins"] == 10
    assert stats["losses"] == 10
    assert stats["win_rate"] == 50.0
    assert stats["gross_profit_usd"] > 0
    assert stats["gross_loss_usd"] > 0
    assert stats["expectancy_r"] < 0 # Sizing 2 pip TP vs 5 pip SL + friction produces negative net R
