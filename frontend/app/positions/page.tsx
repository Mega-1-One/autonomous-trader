"use client";

import React, { useEffect, useState } from "react";

export default function PositionsPage() {
  const [positionsData, setPositionsData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  async function fetchPositions() {
    try {
      const res = await fetch("http://localhost:8000/api/execution/positions");
      if (res.ok) {
        const json = await res.json();
        setPositionsData(json);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 3000);
    return () => clearInterval(interval);
  }, []);

  async function closePosition(posId: string) {
    await fetch(`http://localhost:8000/api/execution/positions/${posId}/close`, { method: "POST" });
    fetchPositions();
  }

  async function closeAll() {
    await fetch("http://localhost:8000/api/execution/close-all", { method: "POST" });
    fetchPositions();
  }

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between p-6 bg-surface rounded-xl border border-border">
        <div>
          <h2 className="text-2xl font-bold">Live Positions Panel</h2>
          <p className="text-sm text-textSecondary mt-1">
            Real-time Position Monitoring, Floating P&L, Break-Even & Risk Tracking
          </p>
        </div>
        {positionsData?.open_positions?.length > 0 && (
          <button
            onClick={closeAll}
            className="px-4 py-2 bg-danger text-white rounded-lg text-xs font-bold hover:bg-danger/80 transition-colors"
          >
            CLOSE ALL POSITIONS
          </button>
        )}
      </div>

      {loading ? (
        <div className="p-8 text-center text-textSecondary">Loading open positions...</div>
      ) : (
        <div className="space-y-6">
          <div className="p-6 bg-surface border border-border rounded-xl">
            <h3 className="text-lg font-bold mb-4">Open Positions ({positionsData?.open_positions?.length || 0})</h3>
            
            {positionsData?.open_positions?.length === 0 ? (
              <p className="text-sm text-textSecondary py-4">No active open positions currently in market.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-border text-textSecondary uppercase text-xs">
                    <tr>
                      <th className="py-3 px-4">Symbol</th>
                      <th className="py-3 px-4">Direction</th>
                      <th className="py-3 px-4">Volume</th>
                      <th className="py-3 px-4">Entry Price</th>
                      <th className="py-3 px-4">Current Price</th>
                      <th className="py-3 px-4">Stop Loss</th>
                      <th className="py-3 px-4">Take Profit</th>
                      <th className="py-3 px-4">Floating PnL</th>
                      <th className="py-3 px-4">R-Multiple</th>
                      <th className="py-3 px-4">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {positionsData?.open_positions?.map((pos: any) => (
                      <tr key={pos.position_id} className="hover:bg-background/50">
                        <td className="py-3 px-4 font-bold">{pos.symbol}</td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                            pos.direction === "LONG" ? "bg-success/20 text-success" : "bg-danger/20 text-danger"
                          }`}>
                            {pos.direction}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-mono">{pos.volume} lots</td>
                        <td className="py-3 px-4 font-mono">{pos.entry_price}</td>
                        <td className="py-3 px-4 font-mono">{pos.current_price}</td>
                        <td className="py-3 px-4 font-mono text-danger">{pos.stop_loss}</td>
                        <td className="py-3 px-4 font-mono text-success">{pos.take_profit}</td>
                        <td className={`py-3 px-4 font-bold font-mono ${pos.floating_pnl >= 0 ? "text-success" : "text-danger"}`}>
                          ${pos.floating_pnl}
                        </td>
                        <td className="py-3 px-4 font-mono font-bold">{pos.r_multiple}R</td>
                        <td className="py-3 px-4">
                          <button
                            onClick={() => closePosition(pos.position_id)}
                            className="px-3 py-1 bg-surface border border-border text-textSecondary hover:text-white hover:bg-danger rounded text-xs font-semibold transition-colors"
                          >
                            Close
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
