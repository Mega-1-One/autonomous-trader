"use client";

import React, { useState } from "react";

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("XAUUSD");
  const [timeframe, setTimeframe] = useState("M5");
  const [candleCount, setCandleCount] = useState(500);
  const [report, setReport] = useState<any>(null);
  const [mcResult, setMcResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  async function runBacktest() {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          timeframe,
          candle_count: candleCount,
          initial_balance: 10000.0,
          spread_pips: 1.0,
          slippage_pips: 0.5,
          commission_per_lot: 7.0
        })
      });
      if (res.ok) {
        const json = await res.json();
        setReport(json.report);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function runMonteCarlo() {
    try {
      const res = await fetch("http://localhost:8000/api/backtest/monte-carlo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          timeframe,
          candle_count: candleCount,
          initial_balance: 10000.0,
          iterations: 200
        })
      });
      if (res.ok) {
        const json = await res.json();
        setMcResult(json.simulation);
      }
    } catch (err) {
      console.error(err);
    }
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between p-6 bg-surface rounded-xl border border-border gap-4">
        <div>
          <h2 className="text-2xl font-bold">Backtest & Monte Carlo Engine</h2>
          <p className="text-sm text-textSecondary mt-1">
            Zero-Lookahead Strategy Validation, Risk Performance & Randomization Stress Test
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="bg-background border border-border rounded-lg px-3 py-2 text-sm font-semibold text-textPrimary"
          >
            <option value="XAUUSD">XAUUSD (Gold)</option>
            <option value="EURUSD">EURUSD</option>
            <option value="GBPUSD">GBPUSD</option>
            <option value="NAS100">NAS100</option>
          </select>

          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="bg-background border border-border rounded-lg px-3 py-2 text-sm font-semibold text-textPrimary"
          >
            <option value="M1">M1</option>
            <option value="M5">M5</option>
            <option value="M15">M15</option>
            <option value="H1">H1</option>
          </select>

          <button
            onClick={runBacktest}
            disabled={loading}
            className="px-5 py-2 bg-primary text-white font-bold rounded-lg text-sm hover:bg-primary/80 transition-colors disabled:opacity-50"
          >
            {loading ? "Simulating..." : "RUN BACKTEST"}
          </button>
        </div>
      </div>

      {report && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-5 bg-surface border border-border rounded-xl">
              <span className="text-xs text-textSecondary uppercase">Net Profit</span>
              <p className={`text-xl font-bold mt-1 ${report.net_profit >= 0 ? "text-success" : "text-danger"}`}>
                ${report.net_profit}
              </p>
            </div>
            <div className="p-5 bg-surface border border-border rounded-xl">
              <span className="text-xs text-textSecondary uppercase">Win Rate</span>
              <p className="text-xl font-bold mt-1 text-textPrimary">{report.win_rate}%</p>
            </div>
            <div className="p-5 bg-surface border border-border rounded-xl">
              <span className="text-xs text-textSecondary uppercase">Profit Factor</span>
              <p className="text-xl font-bold mt-1 text-textPrimary">{report.profit_factor}</p>
            </div>
            <div className="p-5 bg-surface border border-border rounded-xl">
              <span className="text-xs text-textSecondary uppercase">Max Drawdown</span>
              <p className="text-xl font-bold mt-1 text-danger">{report.max_drawdown_percent}%</p>
            </div>
          </div>

          <div className="p-6 bg-surface border border-border rounded-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold">Performance Breakdown</h3>
              <button
                onClick={runMonteCarlo}
                className="px-4 py-2 bg-surface border border-border text-xs font-bold rounded-lg hover:border-primary text-textPrimary"
              >
                RUN MONTE CARLO (200 RUNS)
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div className="p-3 bg-background rounded-lg border border-border">
                <span className="text-textSecondary">Total Trades</span>
                <p className="font-bold text-sm text-textPrimary">{report.total_trades}</p>
              </div>
              <div className="p-3 bg-background rounded-lg border border-border">
                <span className="text-textSecondary">Expectancy</span>
                <p className="font-bold text-sm text-textPrimary">${report.expectancy} / trade</p>
              </div>
              <div className="p-3 bg-background rounded-lg border border-border">
                <span className="text-textSecondary">Sharpe Ratio</span>
                <p className="font-bold text-sm text-textPrimary">{report.sharpe_ratio}</p>
              </div>
              <div className="p-3 bg-background rounded-lg border border-border">
                <span className="text-textSecondary">Sortino Ratio</span>
                <p className="font-bold text-sm text-textPrimary">{report.sortino_ratio}</p>
              </div>
            </div>

            {mcResult && (
              <div className="mt-4 p-4 bg-background border border-border rounded-lg space-y-2">
                <h4 className="text-sm font-bold text-primary">Monte Carlo Simulation Stress Test (200 Iterations)</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs mt-2">
                  <div>
                    <span className="text-textSecondary">Prob of Ruin (&gt;50% DD)</span>
                    <p className="font-bold text-sm text-danger">{mcResult.probability_of_ruin_percent}%</p>
                  </div>
                  <div>
                    <span className="text-textSecondary">Median Profit</span>
                    <p className="font-bold text-sm text-textPrimary">${mcResult.median_net_profit}</p>
                  </div>
                  <div>
                    <span className="text-textSecondary">Median Max DD</span>
                    <p className="font-bold text-sm text-warning">{mcResult.median_max_drawdown_percent}%</p>
                  </div>
                  <div>
                    <span className="text-textSecondary">Expected Losing Streak</span>
                    <p className="font-bold text-sm text-textPrimary">{mcResult.expected_losing_streak} trades</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
