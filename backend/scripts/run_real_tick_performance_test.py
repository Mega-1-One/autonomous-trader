import sys
import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

# Suppress verbose logger during bulk tick backtest
logging.getLogger("autotrader").setLevel(logging.ERROR)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter
from app.backtest.tick_backtest import TickBacktestEngine
from app.backtest.tick_metrics import TickMetricsCalculator
from app.backtest.walk_forward import WalkForwardValidator, TickMonteCarloSimulator

def fetch_real_exness_ticks(symbol_map: dict, max_ticks_per_sym: int = 15000) -> dict:
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("Failed to initialize MT5 adapter")
        return {}

    import MetaTrader5 as mt5

    dataset = {}
    utc_from = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
    utc_to = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)

    for canonical, broker_symbol in symbol_map.items():
        print(f"Fetching real historical ticks for {canonical} ({broker_symbol})...")
        raw_ticks = mt5.copy_ticks_range(broker_symbol, utc_from, utc_to, mt5.COPY_TICKS_ALL)
        if raw_ticks is not None and len(raw_ticks) > 0:
            # Subsample if dataset exceeds max_ticks_per_sym to keep loop fast
            step = max(1, len(raw_ticks) // max_ticks_per_sym)
            sampled = raw_ticks[::step]
            parsed = []
            for t in sampled:
                parsed.append({
                    "symbol": canonical,
                    "bid": float(t[1]),
                    "ask": float(t[2]),
                    "last": float(t[3]) if len(t) > 3 and t[3] > 0 else float(t[1]),
                    "timestamp": float(t[0]),
                    "volume": int(t[4]) if len(t) > 4 else 1
                })
            dataset[canonical] = parsed
            print(f"  -> {canonical}: Loaded {len(parsed)} real Exness ticks (from {len(raw_ticks)} raw ticks).")
        else:
            print(f"  -> {canonical}: Copy ticks returned 0 ticks.")

    adapter.disconnect()
    return dataset

def run_performance_suite():
    symbol_map = {
        "XAUUSD": "XAUUSDm",
        "EURUSD": "EURUSDm",
        "GBPUSD": "GBPUSDm",
        "NAS100": "USTECm"
    }

    raw_data = fetch_real_exness_ticks(symbol_map)
    if not raw_data:
        print("No real tick data retrieved.")
        return

    specs = {
        "XAUUSD": {"point_size": 0.001, "digits": 3},
        "EURUSD": {"point_size": 0.00001, "digits": 5},
        "GBPUSD": {"point_size": 0.00001, "digits": 5},
        "NAS100": {"point_size": 0.01, "digits": 2}
    }

    results = {}

    for sym, ticks in raw_data.items():
        print(f"\nEvaluating Real Tick Performance: {sym} ({len(ticks)} ticks)...")
        spec = specs.get(sym, {"point_size": 0.001, "digits": 3})

        # BASE CASE (50ms latency, normal spread)
        engine_base = TickBacktestEngine(
            symbol=sym,
            initial_balance=10000.0,
            latency_ms=50.0,
            base_slippage_pips=0.1,
            commission_per_lot=7.0,
            point_size=spec["point_size"],
            digits=spec["digits"]
        )

        base_metrics = engine_base.run_backtest(ticks)

        # WORST CASE (100ms latency)
        engine_worst = TickBacktestEngine(
            symbol=sym,
            initial_balance=10000.0,
            latency_ms=100.0,
            base_slippage_pips=0.2,
            commission_per_lot=7.0,
            point_size=spec["point_size"],
            digits=spec["digits"]
        )
        worst_metrics = engine_worst.run_backtest(ticks)

        # STRESS CASE (200ms latency)
        engine_stress = TickBacktestEngine(
            symbol=sym,
            initial_balance=10000.0,
            latency_ms=200.0,
            base_slippage_pips=0.4,
            commission_per_lot=7.0,
            point_size=spec["point_size"],
            digits=spec["digits"]
        )
        stress_metrics = engine_stress.run_backtest(ticks)

        # Walk-Forward Validation
        wf_validator = WalkForwardValidator(engine=engine_base)
        wf_report = wf_validator.run_walk_forward(ticks)

        # Monte Carlo Simulation
        mc_sim = TickMonteCarloSimulator()
        mc_results = mc_sim.run_monte_carlo(
            trades=[{"realized_pnl": base_metrics.net_profit / max(1, base_metrics.total_trades)}] * base_metrics.total_trades if base_metrics.total_trades > 0 else [],
            iterations=500
        )

        results[sym] = {
            "total_ticks_processed": len(ticks),
            "base_case_50ms": base_metrics.to_dict(),
            "worst_case_100ms": worst_metrics.to_dict(),
            "stress_case_200ms": stress_metrics.to_dict(),
            "walk_forward": wf_report.to_dict(),
            "monte_carlo_500_iter": mc_results
        }

    out_path = Path(__file__).resolve().parent / "real_tick_performance_report.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n[SUCCESS] Performance report generated and saved to {out_path}")

if __name__ == "__main__":
    run_performance_suite()
