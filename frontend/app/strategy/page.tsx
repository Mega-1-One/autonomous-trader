"use client";

import React, { useEffect, useState } from "react";
import { apiGet, ApiError, PatternResponse } from "../../lib/api";

export default function StrategyMonitorPage() {
  const [data, setData] = useState<PatternResponse | null>(null);
  const [symbol, setSymbol] = useState("XAUUSD");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPatterns() {
      try {
        const json = await apiGet<PatternResponse>(
          `/api/strategy/patterns?symbol=${symbol}&timeframe=M5&count=200`
        );
        setData(json);
        setError(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to reach backend API");
      } finally {
        setLoading(false);
      }
    }
    fetchPatterns();
  }, [symbol]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between p-6 bg-surface rounded-xl border border-border">
        <div>
          <h2 className="text-2xl font-bold">Strategy Pattern Monitor</h2>
          <p className="text-sm text-textSecondary mt-1">
            Real-time ICT/SMC Market Structure, Liquidity Sweeps, FVGs & Order Blocks
          </p>
        </div>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="bg-background border border-border rounded-lg px-4 py-2 text-sm font-semibold text-textPrimary focus:outline-none focus:border-primary"
        >
          <option value="XAUUSD">XAUUSD (Gold)</option>
          <option value="EURUSD">EURUSD</option>
          <option value="GBPUSD">GBPUSD</option>
          <option value="NAS100">NAS100</option>
        </select>
      </div>

      {error && (
        <div className="p-4 bg-danger/10 border border-danger/40 rounded-lg text-danger text-sm font-semibold">
          {error}
        </div>
      )}

      {loading ? (
        <div className="p-8 text-center text-textSecondary">Loading market patterns...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Trend & Regime Card */}
          <div className="p-6 bg-surface border border-border rounded-xl space-y-4">
            <h3 className="text-lg font-bold">Market Structure Context</h3>
            <div className="flex items-center justify-between p-4 bg-background rounded-lg border border-border">
              <span className="text-sm text-textSecondary">Market Trend Regime</span>
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                data?.trend === "BULLISH" ? "bg-success/20 text-success border border-success/30" :
                data?.trend === "BEARISH" ? "bg-danger/20 text-danger border border-danger/30" : "bg-warning/20 text-warning"
              }`}>
                {data?.trend || "RANGING"}
              </span>
            </div>
            <div className="p-4 bg-background rounded-lg border border-border text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-textSecondary">Displacement Candles</span>
                <span className="font-bold text-textPrimary">{data?.displacements?.length || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Active FVGs</span>
                <span className="font-bold text-textPrimary">{data?.fair_value_gaps?.length || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Liquidity Sweeps</span>
                <span className="font-bold text-textPrimary">{data?.liquidity_sweeps?.length || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Order Blocks</span>
                <span className="font-bold text-textPrimary">{data?.order_blocks?.length || 0}</span>
              </div>
            </div>
          </div>

          {/* Detected FVGs List */}
          <div className="p-6 bg-surface border border-border rounded-xl space-y-4">
            <h3 className="text-lg font-bold">Fair Value Gaps (FVG)</h3>
            <div className="space-y-2 max-h-64 overflow-y-auto pr-2">
              {data?.fair_value_gaps?.length === 0 ? (
                <p className="text-sm text-textSecondary">No active FVGs detected in recent candles.</p>
              ) : (
                data?.fair_value_gaps?.map((fvg, idx: number) => (
                  <div key={idx} className="p-3 bg-background rounded-lg border border-border flex items-center justify-between text-xs">
                    <div>
                      <span className={`font-bold ${
                        fvg.fvg_type === "BULLISH" ? "text-success" :
                        fvg.fvg_type === "BEARISH" ? "text-danger" : "text-textSecondary"
                      }`}>
                        {fvg.fvg_type ?? "Pattern"} FVG
                      </span>
                      <p className="text-textSecondary mt-0.5">{fvg.lower_boundary ?? "?"} - {fvg.upper_boundary ?? "?"}</p>
                    </div>
                    <span className="px-2 py-1 bg-surface border border-border rounded text-textSecondary font-mono">
                      {fvg.mitigation_status ?? "n/a"} ({fvg.fill_percentage ?? 0}%)
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
