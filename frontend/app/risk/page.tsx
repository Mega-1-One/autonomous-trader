"use client";

import React, { useEffect, useState } from "react";

export default function RiskPage() {
  const [riskData, setRiskData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  async function fetchRisk() {
    try {
      const res = await fetch("http://localhost:8000/api/risk/status");
      if (res.ok) {
        const json = await res.json();
        setRiskData(json);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchRisk();
  }, []);

  async function toggleEmergencyStop() {
    const endpoint = riskData?.emergency_stop_active
      ? "http://localhost:8000/api/system/reset-emergency-stop"
      : "http://localhost:8000/api/system/emergency-stop";

    await fetch(endpoint, { method: "POST" });
    fetchRisk();
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between p-6 bg-surface rounded-xl border border-border">
        <div>
          <h2 className="text-2xl font-bold">Risk Management Panel</h2>
          <p className="text-sm text-textSecondary mt-1">
            Capital Protection, Position Sizing Rules & Emergency Controls
          </p>
        </div>

        <button
          onClick={toggleEmergencyStop}
          className={`px-5 py-2.5 rounded-lg text-sm font-bold tracking-wide transition-all shadow-lg ${
            riskData?.emergency_stop_active
              ? "bg-success text-white hover:bg-success/80"
              : "bg-danger text-white hover:bg-danger/80"
          }`}
        >
          {riskData?.emergency_stop_active ? "RESET EMERGENCY STOP" : "TRIGGER EMERGENCY STOP"}
        </button>
      </div>

      {loading ? (
        <div className="p-8 text-center text-textSecondary">Loading risk status...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 bg-surface border border-border rounded-xl space-y-4">
            <h3 className="text-lg font-bold">Risk Parameters</h3>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-textSecondary">Risk Per Trade</span>
                <span className="font-bold text-textPrimary">{riskData?.risk_parameters?.risk_per_trade_percent}%</span>
              </div>
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-textSecondary">Max Daily Loss</span>
                <span className="font-bold text-textPrimary">
                  {riskData?.risk_parameters?.maximum_daily_loss_percent > 0
                    ? `${riskData?.risk_parameters?.maximum_daily_loss_percent}%`
                    : "Unlimited (Scalp Mode)"}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-textSecondary">Max Trades Per Day</span>
                <span className="font-bold text-textPrimary">
                  {riskData?.risk_parameters?.maximum_trades_per_day > 0
                    ? riskData?.risk_parameters?.maximum_trades_per_day
                    : "Unlimited (Scalp Mode)"}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-textSecondary">Max Open Positions</span>
                <span className="font-bold text-textPrimary">
                  {riskData?.risk_parameters?.maximum_open_positions > 0
                    ? riskData?.risk_parameters?.maximum_open_positions
                    : "Unlimited"}
                </span>
              </div>
              <div className="flex justify-between py-2 border-b border-border">
                <span className="text-textSecondary">Max Spread Threshold</span>
                <span className="font-bold text-textPrimary">
                  {riskData?.risk_parameters?.maximum_spread_pips > 0
                    ? `${riskData?.risk_parameters?.maximum_spread_pips} pips`
                    : "Dynamic / Disabled"}
                </span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-textSecondary">Minimum R:R Ratio</span>
                <span className="font-bold text-textPrimary">
                  {riskData?.risk_parameters?.minimum_rr > 0
                    ? `${riskData?.risk_parameters?.minimum_rr}R`
                    : "Fast Scalp (Dynamic)"}
                </span>
              </div>
            </div>
          </div>

          <div className="p-6 bg-surface border border-border rounded-xl space-y-4 md:col-span-2">
            <h3 className="text-lg font-bold">Daily Safety Lock Status</h3>
            <div className="p-4 bg-background border border-border rounded-lg space-y-3 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-textSecondary">Daily Loss Lock</span>
                <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                  riskData?.daily_lock_active ? "bg-danger text-white" : "bg-success/20 text-success border border-success/30"
                }`}>
                  {riskData?.daily_lock_active ? "LOCKED" : "UNLOCKED / ACTIVE"}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-textSecondary">Today Realized PnL</span>
                <span className="font-bold text-textPrimary">${riskData?.today_realized_pnl || 0.0}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-textSecondary">Today Trades Executed</span>
                <span className="font-bold text-textPrimary">
                  {riskData?.today_trade_count || 0} {riskData?.risk_parameters?.maximum_trades_per_day > 0 ? `/ ${riskData?.risk_parameters?.maximum_trades_per_day}` : "(Unlimited)"}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
