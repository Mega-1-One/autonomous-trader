"""C-07 tests: RealMT5Adapter honors caller magic/comment (P-16)."""
from types import SimpleNamespace

import pytest

import app.data.mt5_real as mt5_real
from app.data.mt5_real import RealMT5Adapter


@pytest.fixture
def stub_mt5(monkeypatch):
    """Stubs the mt5 module boundary inside mt5_real (no terminal needed)."""
    sent = {}

    def _order_send(request):
        sent["request"] = request
        return SimpleNamespace(
            retcode=10009, comment="done", order=111, deal=222,
            volume=request["volume"], price=request["price"],
        )

    stub = SimpleNamespace(
        TRADE_ACTION_DEAL=1,
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        ORDER_TIME_GTC=0,
        ORDER_FILLING_IOC=1,
        terminal_info=lambda: SimpleNamespace(connected=True),
        symbols_get=lambda: [SimpleNamespace(name="XAUUSD")],
        order_send=_order_send,
    )
    monkeypatch.setattr(mt5_real, "mt5", stub)
    monkeypatch.setattr(mt5_real, "MT5_AVAILABLE", True)
    return sent


def test_send_order_passes_magic_and_comment(stub_mt5):
    adapter = RealMT5Adapter()
    adapter._connected = True
    adapter.send_order({
        "symbol": "XAUUSD", "type": "BUY", "volume": 0.05, "price": 2400.0,
        "stop_loss": 2399.0, "take_profit": 2401.0,
        "magic": 888888, "comment": "Strategy X",
    })
    req = stub_mt5["request"]
    assert req["magic"] == 888888
    assert req["comment"] == "Strategy X"


def test_send_order_defaults_preserved(stub_mt5):
    adapter = RealMT5Adapter()
    adapter._connected = True
    adapter.send_order({"symbol": "XAUUSD", "type": "BUY", "volume": 0.01, "price": 2400.0})
    req = stub_mt5["request"]
    assert req["magic"] == 100001
    assert req["comment"] == "Autonomous Trader Order"
