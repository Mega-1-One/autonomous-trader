"use client";

import React, { useEffect, useState } from "react";
import { apiGet, HealthResponse } from "../lib/api";

// Header badge reflecting the live backend execution mode (C-05).
// Shows SIMULATED when a DEMO/LIVE mode runs on the mock adapter (NEW-01).
export default function ModeBadge() {
  const [mode, setMode] = useState<string | null>(null);
  const [simulated, setSimulated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function fetchMode() {
      try {
        const health = await apiGet<HealthResponse>("/api/health");
        if (!cancelled) {
          setMode(health.execution_mode);
          setSimulated(health.simulated_execution === true);
        }
      } catch {
        if (!cancelled) {
          setMode(null);
          setSimulated(false);
        }
      }
    }
    fetchMode();
    const interval = setInterval(fetchMode, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const label = mode ? `${mode} MODE${simulated ? " · SIMULATED" : ""}` : "OFFLINE";
  const live = mode === "LIVE";
  return (
    <span
      className={`px-3 py-1 bg-surface border border-border rounded-full text-xs font-semibold ${
        live
          ? "text-danger border-danger/50"
          : simulated
            ? "text-warning border-warning/50"
            : mode
              ? "text-textSecondary"
              : "text-warning"
      }`}
    >
      {label}
    </span>
  );
}
