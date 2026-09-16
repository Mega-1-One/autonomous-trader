"""D-02: position price update (N-06/C-01)."""
import pytest

from app.services.market_data import MarketDataService


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
