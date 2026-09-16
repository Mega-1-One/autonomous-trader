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
from app.context.timeframe_engine import TimeframeEngine
from app.swing.swing_engine import SwingEngine
from app.intelligence.cost_analyzer import CostFilter
from app.backtest.tick_metrics import TickMetricsCalculator

from app.research.common.mt5_ticks import fetch_real_ticks  # C-04 shared helper

def run_swing_backtest(
    ticks: list,
    spec: InstrumentSpecification,
    setup_filter: str = "TREND_PULLBACK",
    rr_ratio: float = 2.0
) -> dict:
    tick_engine = TickEngine(max_stale_seconds=float('inf'))
    feat_engine = FeatureEngine()
    tf_engine = TimeframeEngine()
    swing_engine = SwingEngine()
    cost_filter = CostFilter(commission_per_lot=7.0, base_slippage_pips=0.1)

    executed_trades = []
    candidate_count = 0

    for tick_idx, t in enumerate(ticks):
        bid = float(t["bid"])
        ask = float(t["ask"])
        last = float(t.get("last", bid))
        ts = float(t.get("timestamp", tick_idx * 0.1))

        tick = tick_engine.process_tick(spec.symbol, bid, ask, last, ts, point_size=spec.point_size, digits=spec.digits)
        if not tick:
            continue

        tf_engine.process_tick(spec.symbol, last, ts)

        c4h = tf_engine.get_candles("4h")
        c1h = tf_engine.get_candles("1h")
        c15m = tf_engine.get_candles("15m")

        swing_res = swing_engine.evaluate_swing_setup(c4h, c1h, c15m, spec, current_price=last, target_setup_filter=setup_filter, rr_target_ratio=rr_ratio)

        if swing_res.setup_type != "NO_SETUP":
            candidate_count += 1

        buf = tick_engine.get_buffer(spec.symbol)
        if not buf or len(buf) < 10:
            continue

        feats = feat_engine.extract_features(buf, spec=spec)
        if not feats:
            continue

        cost_res = cost_filter.evaluate_cost(feats, spec, target_distance_pips=swing_res.target_pips, volume=0.05)

        if swing_res.approved and cost_res.passed:
            future_ticks = ticks[tick_idx+1:tick_idx+500]
            is_buy = (swing_res.direction == "BUY")
            entry_p = swing_res.entry_price
            pip_unit = spec.pip_size

            tp_pips = swing_res.target_pips
            sl_pips = swing_res.stop_pips

            trade_pnl = -(cost_res.total_transaction_cost_dollars)
            realized_r = -1.0
            holding_sec = 60.0

            for ft_idx, ft in enumerate(future_ticks):
                curr_p = float(ft["bid"]) if is_buy else float(ft["ask"])
                fav_pips = (curr_p - entry_p) / pip_unit if is_buy else (entry_p - curr_p) / pip_unit
                adv_pips = (entry_p - curr_p) / pip_unit if is_buy else (curr_p - entry_p) / pip_unit

                if fav_pips >= tp_pips:
                    gross_pnl = tp_pips * pip_unit * 100.0 * 0.05
                    trade_pnl = gross_pnl - cost_res.total_transaction_cost_dollars
                    realized_r = round(tp_pips / max(0.1, sl_pips), 2)
                    holding_sec = float(ft.get("timestamp", ts)) - ts
                    break
                elif adv_pips >= sl_pips:
                    loss_pnl = -(sl_pips * pip_unit * 100.0 * 0.05)
                    trade_pnl = loss_pnl - cost_res.total_transaction_cost_dollars
                    realized_r = -1.0
                    holding_sec = float(ft.get("timestamp", ts)) - ts
                    break

            executed_trades.append({
                "realized_pnl": round(trade_pnl, 2),
                "volume": 0.05,
                "r_multiple": realized_r,
                "holding_time_seconds": max(0.1, holding_sec),
                "slippage_cost": 0.5,
                "spread_cost": cost_res.total_transaction_cost_dollars,
                "regime": setup_filter
            })

    metrics = TickMetricsCalculator.calculate_metrics(executed_trades)
    res_dict = metrics.to_dict()
    res_dict["candidate_setups_count"] = candidate_count

    # Out-of-Sample Metrics (Last 20% of trades)
    oos_trades = executed_trades[int(len(executed_trades)*0.8):] if len(executed_trades) >= 5 else []
    oos_metrics = TickMetricsCalculator.calculate_metrics(oos_trades) if oos_trades else metrics
    res_dict["oos_profit_factor"] = oos_metrics.profit_factor
    res_dict["oos_expectancy_r"] = oos_metrics.expectancy_r

    return res_dict

def run_phase25_benchmark():
    symbol_map = {
        "XAUUSD": "XAUUSDm",
        "EURUSD": "EURUSDm",
        "GBPUSD": "GBPUSDm",
        "NAS100": "USTECm"
    }

    raw_data = fetch_real_ticks(symbol_map)
    if not raw_data:
        return

    benchmark_report = {}
    positive_edge_candidates = []

    print("\n==================================================")
    print(" PHASE 25 MULTI-TIMEFRAME SWING BENCHMARK")
    print("==================================================")

    for sym, ticks in raw_data.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        print(f"\nEvaluating Swing Architecture for {sym} ({len(ticks):,} ticks)...")

        # 1. Setup: TREND_PULLBACK (1:2.0 RR)
        tp_res = run_swing_backtest(ticks, spec, setup_filter="TREND_PULLBACK", rr_ratio=2.0)

        # 2. Setup: BREAKOUT_RETEST (1:2.5 RR)
        br_res = run_swing_backtest(ticks, spec, setup_filter="BREAKOUT_RETEST", rr_ratio=2.5)

        # 3. Setup: BOS_RETRACEMENT (1:3.0 RR)
        bos_res = run_swing_backtest(ticks, spec, setup_filter="BOS_RETRACEMENT", rr_ratio=3.0)

        benchmark_report[sym] = {
            "trend_pullback": tp_res,
            "breakout_retest": br_res,
            "bos_retracement": bos_res
        }

        for st_name, r in [("TREND_PULLBACK", tp_res), ("BREAKOUT_RETEST", br_res), ("BOS_RETRACEMENT", bos_res)]:
            print(f"  [{st_name}] Trades: {r['total_trades']} | Win Rate: {r['win_rate']}% | Profit Factor: {r['profit_factor']} | Net Profit: ${r['net_profit']} | Expectancy: {r['expectancy_r']} R | OOS PF: {r['oos_profit_factor']}")

            if r['total_trades'] >= 10 and r['oos_expectancy_r'] > 0 and r['oos_profit_factor'] > 1.0:
                positive_edge_candidates.append({
                    "symbol": sym, "setup": st_name, "oos_pf": r['oos_profit_factor'], "oos_r": r['oos_expectancy_r']
                })

    verdict = "A = Robust positive OOS edge discovered" if positive_edge_candidates else "D = Higher-timeframe hypothesis also fails (Entry edge still negative after costs)"

    report_output = {
        "benchmark_results": benchmark_report,
        "positive_edge_candidates": positive_edge_candidates,
        "final_verdict": verdict
    }

    out_path = Path(__file__).resolve().parent / "phase25_swing_benchmark_report.json"
    with open(out_path, "w") as f:
        json.dump(report_output, f, indent=2)

    print(f"\n==================================================")
    print(f" PHASE 25 SWING BENCHMARK SUMMARY")
    print(f"==================================================")
    print(f"Positive OOS Edge Candidates Discovered: {len(positive_edge_candidates)}")
    print(f"Final Verdict:                           {verdict}")
    print(f"[SUCCESS] Phase 25 Report saved to {out_path}")

if __name__ == "__main__":
    run_phase25_benchmark()
