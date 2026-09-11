"use client";

import React, { useEffect, useState } from "react";

interface HealthState {
  status: string;
  app_name: string;
  execution_mode: string;
  enable_live_trading: boolean;
  live_trading_confirmation: boolean;
  database_connected: boolean;
  mt5_connected: boolean;
  timestamp: string;
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchHealth() {
      try {
        const res = await fetch("http://localhost:8000/api/health");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setHealth(data);
        setError(null);
      } catch (err: any) {
        setError(err.message || "Failed to reach backend API");
      } finally {
        setLoading(false);
      }
    }
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Banner / System Mode */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between p-6 bg-surface rounded-xl border border-border gap-4">
        <div>
          <h2 className="text-2xl font-bold">System Status Overview</h2>
          <p className="text-sm text-textSecondary mt-1">
            Deterministic ICT/SMC Algorithmic Execution Core
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <span className="text-xs uppercase font-semibold tracking-wider text-textSecondary">Execution Mode:</span>
          <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
            health?.execution_mode === "LIVE" ? "bg-danger text-white" : "bg-primary/20 text-primary border border-primary/30"
          }`}>
            {health?.execution_mode || "PAPER (SHADOW)"}
          </span>
        </div>
      </div>

      {/* Safety Warning Banner */}
      {health?.enable_live_trading ? (
        <div className="p-4 bg-danger/10 border border-danger/40 rounded-lg text-danger text-sm font-semibold flex items-center gap-2">
          <span>⚠️ WARNING: Live trading is ENABLED. Real market orders will be submitted.</span>
        </div>
      ) : (
        <div className="p-4 bg-surface border border-border rounded-lg text-textSecondary text-sm flex items-center justify-between">
          <span>🔒 Safety Lock Active: Live trading flag is disabled. System is operating safely in PAPER mode.</span>
          <span className="text-xs text-success font-medium">PASSIVE / SAFE</span>
        </div>
      )}

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-5 bg-surface border border-border rounded-xl">
          <span className="text-xs font-medium text-textSecondary uppercase tracking-wider">Backend Service</span>
          <div className="mt-2 text-xl font-bold text-textPrimary flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${error ? 'bg-danger' : 'bg-success'}`} />
            {loading ? "Checking..." : error ? "Disconnected" : "Healthy"}
          </div>
        </div>

        <div className="p-5 bg-surface border border-border rounded-xl">
          <span className="text-xs font-medium text-textSecondary uppercase tracking-wider">PostgreSQL DB</span>
          <div className="mt-2 text-xl font-bold text-textPrimary flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${health?.database_connected ? 'bg-success' : 'bg-danger'}`} />
            {health?.database_connected ? "Connected" : "Offline"}
          </div>
        </div>

        <div className="p-5 bg-surface border border-border rounded-xl">
          <span className="text-xs font-medium text-textSecondary uppercase tracking-wider">MT5 Broker Adapter</span>
          <div className="mt-2 text-xl font-bold text-textPrimary flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${health?.mt5_connected ? 'bg-success' : 'bg-warning'}`} />
            {health?.mt5_connected ? "Mock Active" : "Disconnected"}
          </div>
        </div>

        <div className="p-5 bg-surface border border-border rounded-xl">
          <span className="text-xs font-medium text-textSecondary uppercase tracking-wider">Active Strategy</span>
          <div className="mt-2 text-xl font-bold text-textPrimary">
            ICT / SMC V1
          </div>
        </div>
      </div>

      {/* Development Status Notice */}
      <div className="p-6 bg-surface border border-border rounded-xl space-y-3">
        <h3 className="text-lg font-semibold">Phase 1 Infrastructure Complete</h3>
        <p className="text-sm text-textSecondary">
          Monorepo structure, FastAPI server, Pydantic configuration with safety validation, SQLAlchemy domain models, Mock MT5 adapter, and Pytest test framework have been verified.
        </p>
      </div>
    </div>
  );
}
