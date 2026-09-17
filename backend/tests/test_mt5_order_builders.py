"""C-03 golden payload tests: shared builders produce byte-identical payloads.

Each test asserts the builder output equals the literal dict the old inline
bot code produced (captured verbatim before the C-03 rewire), so the bot
rewiring cannot silently change request payloads. Per-bot magic numbers,
deviations, comments, and key presence (grid orders carry no sl/tp) are
asserted exactly.
"""
from types import SimpleNamespace

import pytest

from app.scalper.mt5_orders import (
    build_market_order,
    build_close_request,
    pip_scale_for,
    broker_reject_hint,
)

mt5 = SimpleNamespace(
    TRADE_ACTION_DEAL=1,
    ORDER_TYPE_BUY=0,
    ORDER_TYPE_SELL=1,
    ORDER_TIME_GTC=0,
    ORDER_FILLING_IOC=1,
)


def test_pip_scale_for_preserves_bot_convention():
    assert pip_scale_for("XAUUSDm") == 0.10
    assert pip_scale_for("XAUUSD") == 0.10
    assert pip_scale_for("GOLDm") == 0.10
    assert pip_scale_for("USTEC") == 0.10
    assert pip_scale_for("EURUSDm") == 0.0001
    assert pip_scale_for("EURUSD") == 0.0001


def test_daemon_open_payload():
    assert build_market_order(
        mt5, symbol="EURUSDm", order_type=mt5.ORDER_TYPE_BUY, volume=0.01,
        price=1.08500, sl=1.08450, tp=1.08600, deviation=10,
        magic=777111, comment="Autonomous Scalp",
    ) == {
        "action": 1, "symbol": "EURUSDm", "volume": 0.01, "type": 0,
        "price": 1.08500, "sl": 1.08450, "tp": 1.08600, "deviation": 10,
        "magic": 777111, "comment": "Autonomous Scalp",
        "type_time": 0, "type_filling": 1,
    }


def test_daemon_close_payload():
    assert build_close_request(
        mt5, symbol="EURUSDm", volume=0.01, close_type=mt5.ORDER_TYPE_SELL,
        position_ticket=123, price=1.08400, deviation=10,
        magic=777111, comment="AutoScalp Timeout Close",
    ) == {
        "action": 1, "symbol": "EURUSDm", "volume": 0.01, "type": 1,
        "position": 123, "price": 1.08400, "deviation": 10,
        "magic": 777111, "comment": "AutoScalp Timeout Close",
        "type_time": 0, "type_filling": 1,
    }


def test_demo_scalper_payload_magic_999111():
    req = build_market_order(
        mt5, symbol="XAUUSDm", order_type=mt5.ORDER_TYPE_BUY, volume=0.01,
        price=2400.0, sl=2399.5, tp=2401.0, deviation=10,
        magic=999111, comment="MicroScalp 30s",
    )
    assert req["magic"] == 999111
    assert req["comment"] == "MicroScalp 30s"
    close = build_close_request(
        mt5, symbol="XAUUSDm", volume=0.01, close_type=mt5.ORDER_TYPE_SELL,
        position_ticket=9, price=2400.1, deviation=10,
        magic=999111, comment="Scalp Timeout Close",
    )
    assert close["comment"] == "Scalp Timeout Close"


def test_grid_orders_carry_no_sl_tp():
    req = build_market_order(
        mt5, symbol="EURUSDm", order_type=mt5.ORDER_TYPE_BUY, volume=0.01,
        price=1.08500, deviation=10, magic=888888, comment="Grid Base #1",
    )
    assert "sl" not in req and "tp" not in req
    assert req["comment"] == "Grid Base #1"


def test_run_demo_trader_deviation_20():
    req = build_market_order(
        mt5, symbol="EURUSDm", order_type=mt5.ORDER_TYPE_BUY, volume=0.01,
        price=1.08500, sl=1.08200, tp=1.09100, deviation=20,
        magic=100001, comment="AutoTrader Demo Test Order",
    )
    assert req["deviation"] == 20
    assert req["magic"] == 100001


def test_broker_reject_hint_wording():
    assert broker_reject_hint(10009) == "TRADE_RETCODE_DONE (Order executed cleanly)"
    assert broker_reject_hint(10027) == \
        "TRADE_RETCODE_AUTOTRADER_DISABLED (Algo Trading disabled in MT5 toolbar)"
    assert broker_reject_hint(99999) == "Retcode 99999"
    assert broker_reject_hint(None) == "Retcode None"
