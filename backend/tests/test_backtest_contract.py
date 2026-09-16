"""D-02: /api/backtest/run contract test (P-03 fix must not change /run JSON)."""
import json
import os

import pytest

BASELINE_RUN_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "baseline", "api_post_api_backtest_run.json"
)


@pytest.mark.asyncio
async def test_backtest_run_contract_preserved(async_client):
    """/api/backtest/run JSON keeps the baseline shape/keys (P-03 fix changes nothing here)."""
    res = await async_client.post("/api/backtest/run", json={
        "symbol": "XAUUSD", "timeframe": "M5", "candle_count": 200, "initial_balance": 10000,
    })
    assert res.status_code == 200
    data = res.json()
    with open(BASELINE_RUN_FILE, encoding="utf-8") as f:
        baseline = json.load(f)["result"]["json"]
    assert set(data.keys()) == set(baseline.keys())
    assert set(data["report"].keys()) == set(baseline["report"].keys())
    # Metric values are deterministic on mock data across runs (candle
    # timestamps are wall-clock; compare everything but timestamps).
    res2 = await async_client.post("/api/backtest/run", json={
        "symbol": "XAUUSD", "timeframe": "M5", "candle_count": 200, "initial_balance": 10000,
    })
    data2 = res2.json()
    assert data2["symbol"] == data["symbol"] == "XAUUSD"
    rep1 = {k: v for k, v in data["report"].items() if k != "equity_curve"}
    rep2 = {k: v for k, v in data2["report"].items() if k != "equity_curve"}
    assert rep1 == rep2
    eq1 = [(e["equity"], e["drawdown_percent"]) for e in data["report"]["equity_curve"]]
    eq2 = [(e["equity"], e["drawdown_percent"]) for e in data2["report"]["equity_curve"]]
    assert eq1 == eq2
