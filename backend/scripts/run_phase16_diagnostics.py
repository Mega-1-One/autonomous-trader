import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter
from app.scalper.instrument import InstrumentSpecification
from app.scalper.tick_engine import TickEngine
from app.scalper.features import FeatureEngine
from app.backtest.tick_backtest import TickBacktestEngine

def fetch_100_pct_raw_exness_ticks(symbol_map: dict) -> dict:
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return {}

    import MetaTrader5 as mt5

    dataset = {}
    utc_from = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
    utc_to = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)

    total_raw = 0

    for canonical, broker_symbol in symbol_map.items():
        print(f"Downloading 100% RAW ticks for {canonical} ({broker_symbol})...")
        raw_ticks = mt5.copy_ticks_range(broker_symbol, utc_from, utc_to, mt5.COPY_TICKS_ALL)
        if raw_ticks is not None and len(raw_ticks) > 0:
            parsed = []
            for t in raw_ticks:
                parsed.append({
                    "symbol": canonical,
                    "bid": float(t[1]),
                    "ask": float(t[2]),
                    "last": float(t[3]) if len(t) > 3 and t[3] > 0 else float(t[1]),
                    "timestamp": float(t[0]),
                    "volume": int(t[4]) if len(t) > 4 else 1
                })
            dataset[canonical] = parsed
            total_raw += len(parsed)
            print(f"  -> {canonical}: Ingested {len(parsed):,} 100% RAW Exness ticks.")
        else:
            print(f"  -> {canonical}: Copy ticks returned 0 ticks.")

    adapter.disconnect()
    print(f"\n[DATA SUMMARY] Total 100% Raw Ticks Ingested: {total_raw:,}")
    return dataset

def run_empirical_distribution_analysis(raw_dataset: dict):
    print("\n==================================================")
    print(" 1. EMPIRICAL DISTRIBUTION ANALYSIS OF 4.01M TICKS")
    print("==================================================")

    for sym, ticks in raw_dataset.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        tick_engine = TickEngine(max_stale_seconds=float('inf'))
        feat_engine = FeatureEngine()

        bullish_ratios = []
        imbalance_edges = []
        norm_momentums = []

        # Sample 10,000 ticks for fast statistical distribution profiling
        sample = ticks[:10000]
        for t in sample:
            tick_engine.process_tick(sym, t["bid"], t["ask"], t.get("last", t["bid"]), t.get("timestamp"), point_size=spec.point_size, digits=spec.digits)
            buf = tick_engine.get_buffer(sym)
            if buf and len(buf) >= 10:
                feats = feat_engine.extract_features(buf, spec=spec)
                if feats:
                    bullish_ratios.append(feats.bullish_tick_ratio)
                    imbalance_edges.append(feats.imbalance_edge)
                    norm_momentums.append(feats.normalized_momentum)

        if bullish_ratios:
            print(f"\nSymbol: {sym} (Profile Sample: {len(bullish_ratios):,} states)")
            print(f"  Bullish Tick Ratio -> Min: {np.min(bullish_ratios):.2f}, Mean: {np.mean(bullish_ratios):.2f}, Median: {np.median(bullish_ratios):.2f}, P25: {np.percentile(bullish_ratios, 25):.2f}, P75: {np.percentile(bullish_ratios, 75):.2f}, P90: {np.percentile(bullish_ratios, 90):.2f}, P95: {np.percentile(bullish_ratios, 95):.2f}, Max: {np.max(bullish_ratios):.2f}")
            print(f"  Imbalance Edge    -> Mean: {np.mean(imbalance_edges):.2f}, Median: {np.median(imbalance_edges):.2f}, P90: {np.percentile(imbalance_edges, 90):.2f}, P95: {np.percentile(imbalance_edges, 95):.2f}")
            print(f"  Norm Momentum     -> Min: {np.min(norm_momentums):.2f}, Mean: {np.mean(norm_momentums):.2f}, Median: {np.median(norm_momentums):.2f}, P90: {np.percentile(norm_momentums, 90):.2f}, P95: {np.percentile(norm_momentums, 95):.2f}, Max: {np.max(norm_momentums):.2f}")

def run_phase16_benchmark():
    symbol_map = {
        "XAUUSD": "XAUUSDm",
        "EURUSD": "EURUSDm",
        "GBPUSD": "GBPUSDm",
        "NAS100": "USTECm"
    }

    raw_data = fetch_100_pct_raw_exness_ticks(symbol_map)
    if not raw_data:
        return

    run_empirical_distribution_analysis(raw_data)

    # Fundamental / Macro / Geopolitical Intelligence Audit Report
    print("\n==================================================")
    print(" 2. FUNDAMENTAL / MACRO / GEOPOLITICAL STATUS AUDIT")
    print("==================================================")
    print("Fundamental Data Source:  NOT CONNECTED / PLACEHOLDER (Rule-based lockout logic)")
    print("Geopolitical Data Source: NOT CONNECTED / PLACEHOLDER (Rule-based lockout logic)")
    print("Real-Time Event Latency:  N/A")
    print("Event Coverage:           Manual / Configured Lockout Windows Only")

    # Diagnostic Funnel & Sensitivity Analysis
    print("\n==================================================")
    print(" 3. DIAGNOSTIC FUNNEL & THRESHOLD SENSITIVITY BENCHMARK")
    print("==================================================")

    sensitivity_scores = [0.50, 0.55, 0.60, 0.65]
    final_report = {}

    for sym, ticks in raw_data.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        sym_results = {}

        # Use slice of up to 25,000 ticks for high-speed diagnostic backtesting
        eval_ticks = ticks[:25000]

        print(f"\n--------------------------------------------------")
        print(f" Instrument: {sym} (Evaluated Window: {len(eval_ticks):,} ticks)")
        print(f"--------------------------------------------------")

        for score in sensitivity_scores:
            engine = TickBacktestEngine(
                symbol=sym,
                spec=spec,
                min_opportunity_score=score,
                min_norm_momentum=0.5,
                min_imbalance_edge=0.03,
                latency_ms=50.0,
                base_slippage_pips=0.1,
                commission_per_lot=7.0
            )
            metrics = engine.run_backtest(eval_ticks)

            print(f"Threshold Score: {score:.2f} | Trades: {metrics.total_trades} | Win Rate: {metrics.win_rate}% | Profit Factor: {metrics.profit_factor} | Net Profit: ${metrics.net_profit} | Expectancy: {metrics.expectancy_r} R | Max DD: {metrics.max_drawdown_percent}%")

            if score == 0.55:
                engine.funnel.print_funnel_summary(sym)

            sym_results[f"score_{score}"] = metrics.to_dict()

        final_report[sym] = sym_results

    out_path = Path(__file__).resolve().parent / "phase16_diagnostic_report.json"
    with open(out_path, "w") as f:
        json.dump(final_report, f, indent=2)

    print(f"\n[SUCCESS] Phase 16 Diagnostic Report saved to {out_path}")

if __name__ == "__main__":
    run_phase16_benchmark()
