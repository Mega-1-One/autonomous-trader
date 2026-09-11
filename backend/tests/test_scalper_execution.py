import pytest
import time

from app.scalper.cooldown import CooldownManager
from app.scalper.position_manager import ScalpPositionManager, ScalpPosition
from app.scalper.execution import ScalpPaperExecutionEngine
from app.scalper.signal import ScalpSignal

def test_cooldown_manager_lockout():
    cd = CooldownManager(cooldown_seconds=10, max_consecutive_losses=3)
    now = time.time()

    cd.record_trade_result(-10.0, now)
    cd.record_trade_result(-5.0, now + 1)
    assert cd.locked is False

    cd.record_trade_result(-15.0, now + 2)
    assert cd.locked is True
    assert "Locked out after 3 consecutive losses" in cd.lock_reason

    cd.reset_lockout()
    assert cd.locked is False

def test_position_manager_tp_sl_exits():
    pm = ScalpPositionManager(max_holding_seconds=30.0)
    now = time.time()

    pos = ScalpPosition(
        position_id="POS_1", symbol="XAUUSD", direction="BUY", volume=0.1,
        entry_price=2400.0, current_price=2400.0, stop_loss=2395.0, take_profit=2410.0,
        entry_time=now, status="OPEN"
    )
    pm.add_position(pos)

    # Price hits Take Profit (2410.0)
    closed = pm.update_and_check_exits(current_bid=2410.5, current_ask=2410.5, now=now + 5)
    assert len(closed) == 1
    assert closed[0].exit_reason == "TAKE_PROFIT"
    assert closed[0].realized_pnl > 0

def test_paper_execution_latency():
    engine = ScalpPaperExecutionEngine()
    now = time.time()

    sig = ScalpSignal(
        signal_id="SIG_PAPER_1", timestamp=now, symbol="XAUUSD", direction="BUY",
        status="APPROVED", confidence_score=0.85, entry_reference=2400.0,
        stop_reference=2395.0, target_reference=2410.0, spread=0.5, momentum=0.5,
        velocity=2.0, volatility=0.1, reasons=["momentum"], expiry_time=now + 10
    )

    res = engine.execute_scalp_opportunity(sig, opportunity_score=0.85)
    assert res["status"] == "EXECUTED"
    assert res["mode"] == "PAPER"
    assert res["latency_ms"] >= 0.0
    assert "audit" in res
