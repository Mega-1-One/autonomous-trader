"use client";

import React, { useEffect, useState } from "react";
import { apiGet, ApiError, SignalResponse } from "../../lib/api";

export default function SignalLogPage() {
  const [signalData, setSignalData] = useState<SignalResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function fetchSignal() {
    try {
      const json = await apiGet<SignalResponse>("/api/strategy/signals?symbol=XAUUSD");
      setSignalData(json);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to reach backend API");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchSignal();
  }, []);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between p-6 bg-surface rounded-xl border border-border">
        <div>
          <h2 className="text-2xl font-bold">Trade Signal Log & Rejection Rationale</h2>
          <p className="text-sm text-textSecondary mt-1">
            Auditable trail of every detected setup, approval status, and explicit refusal reason
          </p>
        </div>
        <button
          onClick={fetchSignal}
          className="px-4 py-2 bg-surface border border-border rounded-lg text-xs font-semibold hover:border-primary text-textPrimary transition-colors"
        >
          Evaluate Signal Now
        </button>
      </div>

      {error && (
        <div className="p-4 bg-danger/10 border border-danger/40 rounded-lg text-danger text-sm font-semibold">
          {error}
        </div>
      )}

      {loading ? (
        <div className="p-8 text-center text-textSecondary">Evaluating strategy signal log...</div>
      ) : (
        <div className="p-6 bg-surface border border-border rounded-xl space-y-4">
          <h3 className="text-lg font-bold">Latest Signal Evaluation</h3>

          <div className="p-4 bg-background border border-border rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-textSecondary uppercase">Signal ID: {signalData?.signal?.client_signal_id}</span>
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                signalData?.signal?.status === "APPROVED"
                  ? "bg-success/20 text-success border border-success/30"
                  : "bg-warning/20 text-warning border border-warning/30"
              }`}>
                {signalData?.signal?.status}
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-textSecondary">Symbol</span>
                <p className="font-bold text-sm text-textPrimary">{signalData?.symbol}</p>
              </div>
              <div>
                <span className="text-textSecondary">Direction</span>
                <p className="font-bold text-sm text-textPrimary">{signalData?.signal?.direction}</p>
              </div>
              <div>
                <span className="text-textSecondary">Setup Type</span>
                <p className="font-bold text-sm text-textPrimary">{signalData?.signal?.setup_type}</p>
              </div>
              <div>
                <span className="text-textSecondary">Risk / Reward</span>
                <p className="font-bold text-sm text-textPrimary">{signalData?.signal?.risk_reward}R</p>
              </div>
            </div>

            <div className="p-3 bg-surface rounded border border-border text-xs space-y-1">
              <span className="font-bold text-textSecondary uppercase">Audit Log & Reasons:</span>
              <pre className="text-textPrimary font-mono overflow-x-auto whitespace-pre-wrap mt-1">
                {JSON.stringify(signalData?.signal?.reasons, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
