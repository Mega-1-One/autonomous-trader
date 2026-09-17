"""D-02: position price update (N-06/C-01); N2-M8 side-aware marking."""
import pytest

from app.data.mt5_mock import MockMT5Adapter
from app.services.market_data import MarketDataService


class _BidAskAdapter(MockMT5Adapter):
    """Mock adapter exposing live bid/ask on symbol info."""

    def get_symbol_info(self, symbol):
        info = dict(super().get_symbol_info(symbol) or {})
        base = {"XAUUSD": (2400.0, 2400.5), "EURUSD": (1.0850, 1.0851)}.get(symbol.upper(), (1.0, 1.1))
        info["bid"], info["ask"] = base
        return info


def test_get_latest_price_side_preference():
    svc = MarketDataService(adapter=_BidAskAdapter())
    assert svc.get_latest_price("XAUUSD", side="LONG") == 2400.0
    assert svc.get_latest_price("XAUUSD", side="SHORT") == 2400.5
    assert svc.get_latest_price("XAUUSD") == 2400.0  # default LONG


@pytest.mark.asyncio
async def test_positions_endpoint_marks_each_side(async_client):
    """N2-M8: LONG marked at bid, SHORT at ask (per symbol side)."""
    from app.main import app
    from app.api import deps
    from app.execution.engine import ExecutionEngine
    from app.risk.engine import RiskEngine

    adapter = _BidAskAdapter()
    adapter.connect()
    svc = MarketDataService(adapter=adapter)
    eng = ExecutionEngine(adapter=adapter, risk_engine=RiskEngine())
    app.dependency_overrides[deps.get_market_service] = lambda: svc
    app.dependency_overrides[deps.get_execution_engine] = lambda: eng
    try:
        r_long = await async_client.post("/api/execution/orders", json={
            "client_signal_id": "SIG_SIDE_LONG",
            "symbol": "XAUUSD", "direction": "LONG",
            "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
        })
        assert r_long.status_code == 200
        r_short = await async_client.post("/api/execution/orders", json={
            "client_signal_id": "SIG_SIDE_SHORT",
            "symbol": "EURUSD", "direction": "SHORT",
            "entry_price": 1.0850, "stop_loss": 1.0860, "take_profit": 1.0750,
        })
        assert r_short.status_code == 200
        res = await async_client.get("/api/execution/positions")
        assert res.status_code == 200
        by_id = {p["position_id"]: p for p in res.json()["open_positions"]}
        assert by_id[r_long.json()["position"]["position_id"]]["current_price"] == 2400.0
        assert by_id[r_short.json()["position"]["position_id"]]["current_price"] == 1.0851
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_position_endpoint_uses_real_prices_for_eurusd(async_client):
    """Positions endpoint must not mark EURUSD at the hard-coded 2400.0 (N-06)."""
    from app.main import app
    from app.api import deps
    deps.init_app_state(app)

    res = await async_client.post("/api/execution/orders", json={
        "client_signal_id": "SIG_PRICE_001",
        "symbol": "EURUSD", "direction": "LONG",
        "entry_price": 1.08500, "stop_loss": 1.08400, "take_profit": 1.09500,
    })
    assert res.status_code == 200
    pos_id = res.json()["position"]["position_id"]

    res_pos = await async_client.get("/api/execution/positions")
    assert res_pos.status_code == 200
    data = res_pos.json()
    # The mock's sine-wave candle closes may TP/SL the position; it must be
    # present somewhere and marked at a real (non-constant) price either way.
    mine = [p for p in data["open_positions"] + data["closed_positions"]
            if p["position_id"] == pos_id]
    assert mine, "position missing from endpoint"
    assert mine[0]["current_price"] != 2400.0
    # Mock has no bid/ask on the spec -> falls back to a candle close
    assert abs(mine[0]["current_price"] - 1.0850) < 5.0


def test_get_latest_price_prefers_candle_close_over_constant():
    svc = MarketDataService()
    price = svc.get_latest_price("EURUSD")
    assert price is not None
    assert price != 2400.0
    assert abs(price - 1.0850) < 5.0  # mock candle close range
