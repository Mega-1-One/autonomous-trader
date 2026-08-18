import pytest
from app.backtest.metrics import (
    BacktestTradeRecord,
    EquityPoint,
    BacktestMetricsCalculator,
)
from app.backtest.engine import BacktestEngine
from app.backtest.monte_carlo import MonteCarloSimulator

def test_metrics_calculator():
    trades = [
        BacktestTradeRecord("T1", "XAUUSD", "LONG", 2400.0, 2420.0, 2390.0, 2420.0, 0.05, 100.0, 2.0, "2026-08-17T10:00:00Z", "2026-08-17T11:00:00Z", "TAKE_PROFIT"),
        BacktestTradeRecord("T2", "XAUUSD", "SHORT", 2420.0, 2430.0, 2430.0, 2400.0, 0.05, -50.0, -1.0, "2026-08-17T12:00:00Z", "2026-08-17T13:00:00Z", "STOP_LOSS"),
    ]
    eq_curve = [
        EquityPoint("2026-08-17T10:00:00Z", 10000.0, 0.0),
        EquityPoint("2026-08-17T11:00:00Z", 10100.0, 0.0),
        EquityPoint("2026-08-17T13:00:00Z", 10050.0, 0.49),
    ]

    report = BacktestMetricsCalculator.calculate(10000.0, trades, eq_curve)
    assert report.total_trades == 2
    assert report.winning_trades == 1
    assert report.losing_trades == 1
    assert report.win_rate == 50.0
    assert report.gross_profit == 100.0
    assert report.gross_loss == 50.0
    assert report.net_profit == 50.0
    assert report.profit_factor == 2.0

def test_monte_carlo_simulator():
    trades = [
        BacktestTradeRecord("T1", "XAUUSD", "LONG", 2400.0, 2420.0, 2390.0, 2420.0, 0.05, 100.0, 2.0, "2026-08-17T10:00:00Z", "2026-08-17T11:00:00Z", "TAKE_PROFIT"),
        BacktestTradeRecord("T2", "XAUUSD", "SHORT", 2420.0, 2430.0, 2430.0, 2400.0, 0.05, -50.0, -1.0, "2026-08-17T12:00:00Z", "2026-08-17T13:00:00Z", "STOP_LOSS"),
    ]

    sim = MonteCarloSimulator(iterations=50)
    res = sim.run_simulation(10000.0, trades)
    assert res.iterations == 50
    assert "probability_of_ruin_percent" in res.to_dict()

@pytest.mark.asyncio
async def test_api_run_backtest(async_client):
    res = await async_client.post(
        "/api/backtest/run",
        json={"symbol": "XAUUSD", "timeframe": "M5", "candle_count": 100, "initial_balance": 10000.0}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "XAUUSD"
    assert "report" in data

@pytest.mark.asyncio
async def test_api_run_monte_carlo(async_client):
    res = await async_client.post(
        "/api/backtest/monte-carlo",
        json={"symbol": "XAUUSD", "timeframe": "M5", "candle_count": 100, "iterations": 50}
    )
    assert res.status_code == 200
    data = res.json()
    assert "simulation" in data
