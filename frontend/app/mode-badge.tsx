"use client";

import React, { useEffect, useState } from "react";
import { apiGet, HealthResponse } from "../lib/api";

// Header badge reflecting the live backend execution mode (C-05).
export default function ModeBadge() {
  const [mode, setMode] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function fetchMode() {
      try {
        const health = await apiGet<HealthResponse>("/api/health");
        if (!cancelled) setMode(health.execution_mode);
      } catch {
        if (!cancelled) setMode(null);
      }
    }
    fetchMode();
    const interval = setInterval(fetchMode, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const label = mode ? `${mode} MODE` : "OFFLINE";
  const live = mode === "LIVE";
  return (
    <span
      className={`px-3 py-1 bg-surface border border-border rounded-full text-xs font-semibold ${
        live ? "text-danger border-danger/50" : mode ? "text-textSecondary" : "text-warning"
      }`}
    >
      {label}
    </span>
  );
}
