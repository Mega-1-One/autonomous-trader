"""H-1 per-bot safety-gate control-flow tests (fake mt5 on the live path).

Unlike the textual gate-placement audit, these tests drive each bot's real
run/close methods with a stubbed ``MetaTrader5`` module and assert on actual
``order_send`` calls: entries send nothing while the sentinel is active,
while close/reduce sends still go through (de-risking is never trapped).
"""
import io
import sys
import time
from types import SimpleNamespace

import pytest

import app.core.config as config_module
from app.core.config import ExecutionMode, Settings
from app.core import stop_state


class FakeRates(dict):
    """copy_rates_from_pos stand-in: dict access + trade-like length."""
    def __len__(self):
        return 30


class FakeMT5:
    """Stub MetaTrader5 module: records sends, serves scripted market data."""

    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TIMEFRAME_M1 = 1
    COPY_TICKS_ALL = 0

    def __init__(self):
        self.sent = []
        self.trade_mode = 0
        self.bid = 1.0850
        self.ask = 1.0851
        self._positions = []
        self.ticket_calls = 0
        self.next_ticket = 5000
        self.order_retcode = self.TRADE_RETCODE_DONE
        self.closes = {"close": [float(i) for i in range(30)]}

    # -- market data -----------------------------------------------------
    def account_info(self):
        return SimpleNamespace(
            login=42, server="Fake", balance=10000.0, equity=10000.0,
            margin_free=9000.0, margin=100.0, trade_mode=self.trade_mode,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=self.bid, ask=self.ask)

    def copy_rates_from_pos(self, *args, **kwargs):
        return FakeRates(self.closes)

    def copy_ticks_range(self, *args, **kwargs):
        return []

    # -- positions --------------------------------------------------------
    def positions_get(self, *args, **kwargs):
        if callable(self._positions):
            return self._positions(*args, **kwargs)
        return self._positions

    # -- sends -------------------------------------------------------------
    def order_send(self, req):
        self.sent.append(req)
        self.next_ticket += 1
        return SimpleNamespace(
            retcode=self.order_retcode, order=self.next_ticket,
            price=req.get("price"), comment="done",
        )


@pytest.fixture
def fake_mt5(monkeypatch):
    fake = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    return fake


@pytest.fixture
def demo_mode():
    """DEMO execution so REAL-destination sends are gate-legal; restored after."""
    original = config_module.settings
    s = Settings()
    object.__setattr__(s, "EXECUTION_MODE", ExecutionMode.DEMO)
    config_module.settings = s
    yield s
    config_module.settings = original


@pytest.fixture
def sentinel():
    stop_state.trigger("control-flow test")
    yield
    stop_state.reset()


def close_requests(fake):
    return [r for r in fake.sent if "position" in r]


def entry_requests(fake):
    return [r for r in fake.sent if "position" not in r]


# ---------------------------------------------------------------------------
# Grid bot
# ---------------------------------------------------------------------------

def test_grid_entry_refused_under_sentinel(fake_mt5, demo_mode, sentinel):
    from app.scalper.grid_martingale_bot import MT5GridMartingaleScalper
    bot = MT5GridMartingaleScalper()
    res = bot.run_grid_cycle(direction="BUY", max_cycle_sec=0)
    assert res["status"] == "REJECTED_BY_SAFETY_GATE"
    assert fake_mt5.sent == []


def test_grid_close_allowed_under_sentinel(fake_mt5, demo_mode, sentinel):
    from app.scalper.grid_martingale_bot import MT5GridMartingaleScalper
    bot = MT5GridMartingaleScalper()
    pos = SimpleNamespace(ticket=11, magic=888999, type=0, volume=0.01,
                          price_open=1.0850, profit=0.0, swap=0.0)
    fake_mt5._positions = [pos]
    bot._close_all_grid_positions([11])
    assert len(close_requests(fake_mt5)) == 1
    assert entry_requests(fake_mt5) == []


def test_grid_close_continues_past_refused_ticket(fake_mt5, demo_mode):
    """N2-M7: a refused close must not abandon the rest of the basket."""
    from app.scalper.grid_martingale_bot import MT5GridMartingaleScalper
    bot = MT5GridMartingaleScalper()
    # PAPER mode refuses REAL closes by mode rule (not sentinel): both tickets
    # must still be attempted, none sent.
    object.__setattr__(config_module.settings, "EXECUTION_MODE", ExecutionMode.PAPER)
    try:
        positions = [
            SimpleNamespace(ticket=11, magic=888999, type=0, volume=0.01,
                            price_open=1.0850, profit=0.0, swap=0.0),
            SimpleNamespace(ticket=12, magic=888999, type=0, volume=0.01,
                            price_open=1.0850, profit=0.0, swap=0.0),
        ]
        fake_mt5._positions = positions
        bot._close_all_grid_positions([11, 12])  # must not raise
        assert fake_mt5.sent == []
    finally:
        object.__setattr__(config_module.settings, "EXECUTION_MODE", ExecutionMode.DEMO)


def test_grid_orders_carry_protective_sl(fake_mt5, demo_mode):
    from app.scalper.grid_martingale_bot import MT5GridMartingaleScalper
    bot = MT5GridMartingaleScalper()
    fake_mt5._positions = []
    bot.run_grid_cycle(direction="BUY", max_cycle_sec=0)
    entries = entry_requests(fake_mt5)
    assert len(entries) == 1
    assert entries[0]["sl"] is not None
    assert entries[0]["sl"] < entries[0]["price"]  # BUY disaster stop below entry


# ---------------------------------------------------------------------------
# Ultra tick scalper
# ---------------------------------------------------------------------------

def test_ultra_entry_refused_under_sentinel(fake_mt5, demo_mode, sentinel):
    from app.scalper.ultra_tick_scalper import UltraTickScalperEngine
    bot = UltraTickScalperEngine()
    bot.run_ultra_scalping_session(total_scalps_to_execute=1)
    assert fake_mt5.sent == []


def test_ultra_close_allowed_under_sentinel(fake_mt5, demo_mode):
    """Entry succeeds, the stop fires mid-session, the timeout close must
    still go through on the live path (no sentinel fixture: the stop is
    triggered by the entry send itself)."""
    from app.scalper.ultra_tick_scalper import UltraTickScalperEngine
    bot = UltraTickScalperEngine()
    pos = SimpleNamespace(ticket=21, magic=999333, type=0, volume=0.01,
                          price_open=1.0850, profit=0.0, swap=0.0)
    calls = {"n": 0}

    def positions(ticket=None, **kwargs):
        # loop-check + monitor see nothing (fast path); autoclose sees the position
        if ticket is None:
            return []
        calls["n"] += 1
        return [] if calls["n"] == 1 else [pos]

    fake_mt5._positions = positions
    orig_send = fake_mt5.order_send

    def send_and_stop(req):
        res = orig_send(req)
        if "position" not in req:
            stop_state.trigger("mid ultra session")
        return res

    fake_mt5.order_send = send_and_stop
    try:
        bot.run_ultra_scalping_session(total_scalps_to_execute=1)
    finally:
        stop_state.reset()
    assert len(entry_requests(fake_mt5)) == 1
    assert len(close_requests(fake_mt5)) == 1


# ---------------------------------------------------------------------------
# Autonomous daemon
# ---------------------------------------------------------------------------

def test_daemon_entry_refused_under_sentinel(fake_mt5, demo_mode, sentinel):
    from app.scalper.autonomous_scalper_daemon import AutonomousScalperDaemon
    bot = AutonomousScalperDaemon(max_holding_seconds=45.0)
    fake_mt5._positions = []
    bot.run_autonomous_loop(duration_seconds=0.05)
    assert fake_mt5.sent == []


def test_daemon_close_allowed_under_sentinel(fake_mt5, demo_mode, sentinel):
    from app.scalper.autonomous_scalper_daemon import AutonomousScalperDaemon
    bot = AutonomousScalperDaemon(max_holding_seconds=5.0)
    pos = SimpleNamespace(ticket=31, magic=777111, type=0, volume=0.01,
                          price_open=1.0850, profit=0.5, swap=0.0,
                          time=time.time() - 60.0)
    fake_mt5._positions = [pos]
    bot.run_autonomous_loop(duration_seconds=0.05)
    assert entry_requests(fake_mt5) == []
    assert len(close_requests(fake_mt5)) == 1


# ---------------------------------------------------------------------------
# Demo scalper
# ---------------------------------------------------------------------------

def test_demo_entry_refused_under_sentinel(fake_mt5, demo_mode, sentinel):
    from app.scalper.demo_scalper_engine import MT5DemoMicroScalper
    bot = MT5DemoMicroScalper()
    bot.execute_micro_scalp(direction="BUY", max_hold_sec=0.0)
    assert fake_mt5.sent == []


def test_demo_close_sent_without_sentinel(fake_mt5, demo_mode):
    """Close block wiring (intent=close); sentinel-bypass proven at gate level
    and by the grid/ultra/daemon tests above sharing the same gate call."""
    from app.scalper.demo_scalper_engine import MT5DemoMicroScalper
    bot = MT5DemoMicroScalper()
    pos = SimpleNamespace(ticket=41, magic=999111, type=0, volume=0.01,
                          price_open=2400.0, profit=0.0, swap=0.0)
    fake_mt5._positions = [pos]
    bot.execute_micro_scalp(direction="BUY", max_hold_sec=0.0)
    assert len(entry_requests(fake_mt5)) == 1
    assert len(close_requests(fake_mt5)) == 1


# ---------------------------------------------------------------------------
# Gold multi scalper
# ---------------------------------------------------------------------------

def test_gold_entry_refused_under_sentinel(fake_mt5, demo_mode, sentinel, monkeypatch):
    from app.scalper.gold_multi_scalper import GoldMultiPositionProfitScalper
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    bot = GoldMultiPositionProfitScalper(max_holding_seconds=0.0)
    fake_mt5._positions = []
    try:
        bot.run_multi_scalper_loop(duration_seconds=0.05)
    finally:
        bot.is_running = False
    assert fake_mt5.sent == []


def test_gold_close_allowed_under_sentinel(fake_mt5, demo_mode, sentinel, monkeypatch):
    from app.scalper.gold_multi_scalper import GoldMultiPositionProfitScalper
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    bot = GoldMultiPositionProfitScalper(max_holding_seconds=0.0)
    pos = SimpleNamespace(ticket=55, magic=888777, type=0, volume=0.01,
                          price_open=2400.0, profit=1.0, swap=0.0,
                          sl=2399.0, tp=2401.0, time=time.time() - 300.0,
                          symbol="XAUUSDm")
    fake_mt5._positions = [pos]
    fake_mt5.bid, fake_mt5.ask = 2400.0, 2400.1
    try:
        bot.run_multi_scalper_loop(duration_seconds=0.05)
    finally:
        bot.is_running = False
    assert entry_requests(fake_mt5) == []
    assert len(close_requests(fake_mt5)) >= 1
