import pytest
from app.scalper.autonomous_scalper_daemon import AutonomousScalperDaemon

def test_autonomous_scalper_init():
    daemon = AutonomousScalperDaemon(symbol="EURUSDm", max_holding_seconds=45.0, cooldown_seconds=10)
    assert daemon.symbol == "EURUSDm"
    assert daemon.max_holding_seconds == 45.0
    assert daemon.cooldown_seconds == 10
