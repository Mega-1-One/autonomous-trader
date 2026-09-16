"""D-02: emergency-stop propagation (P-01 in-process).

POST /api/system/emergency-stop must block POST /api/execution/orders
(the shared in-process RiskEngine). Cross-process propagation is covered
via the file sentinel in test_stop_sentinel_cross_process.py (documented
in ADR-8): no test can drive a real bot process against real MT5 in CI,
so cross-process behavior is tested through the sentinel mechanism, not
by spawning MT5.
"""
import pytest


@pytest.mark.asyncio
async def test_api_emergency_stop_blocks_order_submission(async_client):
    """API emergency stop must block the API order path (same shared engine)."""
    res = await async_client.post("/api/system/emergency-stop", json={"reason": "propagation test"})
    assert res.status_code == 200
    assert res.json()["emergency_stop_active"] is True

    res_order = await async_client.post("/api/execution/orders", json={
        "symbol": "XAUUSD", "direction": "LONG",
        "entry_price": 2400.0, "stop_loss": 2390.0, "take_profit": 2420.0,
    })
    assert res_order.status_code == 400
    assert "EMERGENCY STOP" in res_order.json()["detail"].upper()

    # Reset to restore clean state for other tests
    res_reset = await async_client.post("/api/system/reset-emergency-stop")
    assert res_reset.status_code == 200


@pytest.mark.asyncio
async def test_stop_blocks_risk_evaluation_path(async_client):
    """The stop also surfaces on the risk-evaluate path (same shared engine)."""
    await async_client.post("/api/system/emergency-stop", json={"reason": "propagation test 2"})
    res = await async_client.post("/api/risk/evaluate", json={
        "symbol": "XAUUSD", "entry_price": 2400.0,
        "stop_loss": 2390.0, "take_profit": 2420.0,
    })
    assert res.status_code == 200
    assert res.json()["decision"]["approved"] is False
    assert "EMERGENCY STOP" in res.json()["decision"]["rejection_reason"].upper()
    await async_client.post("/api/system/reset-emergency-stop")
