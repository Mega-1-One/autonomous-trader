import sys
import json
import logging
from pathlib import Path

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scalper.instrument import InstrumentSpecification
from app.scalper.tick_engine import TickEngine
from app.scalper.features import FeatureEngine
from app.context.timeframe_engine import TimeframeEngine
from app.context.bias_engine import BiasEngine
from app.context.setup_engine import SetupEngine
from app.intelligence.cost_analyzer import CostFilter
from app.scalper.adaptive_exit_v2 import AdaptiveExitEngineV2
from app.backtest.tick_metrics import TickMetricsCalculator

from app.research.common.mt5_ticks import fetch_real_ticks  # C-04 shared helper

def run_adaptive_exit_backtest(
    ticks: list,
    spec: InstrumentSpecification,
    target_multiple: float = 1.5,
    stop_multiple: float = 1.0,
    max_cost_ratio: float = 30.0
) -> dict:
    tick_engine = TickEngine(max_stale_seconds=float('inf'))
    feat_engine = FeatureEngine()
    tf_engine = TimeframeEngine()
    bias_engine = BiasEngine()
    setup_engine = SetupEngine()
    cost_filter = CostFilter(commission_per_lot=7.0, base_slippage_pips=0.1)
    exit_v2 = AdaptiveExitEngineV2()

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

        buf = tick_engine.get_buffer(spec.symbol)
        if not buf or len(buf) < 10:
            continue

        feats = feat_engine.extract_features(buf, spec=spec)
        if not feats:
            continue

        tf_candles = {tf: tf_engine.get_candles(tf) for tf in ["4h", "1h", "15m", "5m"]}
        bias_res = bias_engine.evaluate_bias(tf_candles)
        setup_res = setup_engine.evaluate_setup(bias_res, feats, spec)

        if setup_res.direction != "NONE":
            candidate_count += 1

        levels = exit_v2.calculate_exit_levels(
            feats, spec, direction=setup_res.direction if setup_res.direction != "NONE" else "BUY",
            atr_multiple_target=target_multiple, atr_multiple_stop=stop_multiple
        )

        cost_res = cost_filter.evaluate_cost(feats, spec, target_distance_pips=levels.target_distance_pips, volume=0.05)

        if setup_res.approved and cost_res.passed and levels.cost_ratio_percent <= max_cost_ratio:
            future_ticks = ticks[tick_idx+1:tick_idx+300]
            is_buy = (setup_res.direction == "BUY")
            entry_p = levels.entry_price
            pip_unit = spec.pip_size

            tp_pips = levels.target_distance_pips
            sl_pips = levels.stop_distance_pips

            trade_pnl = -(cost_res.total_transaction_cost_dollars)
            realized_r = -1.0
            holding_sec = 30.0

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
                "regime": "PHASE_21_ADAPTIVE"
            })

    metrics = TickMetricsCalculator.calculate_metrics(executed_trades)
    res_dict = metrics.to_dict()
    res_dict["candidate_setups_count"] = candidate_count
    return res_dict

def run_phase21_benchmark():
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

    print("\n==================================================")
    print(" PHASE 21 ADAPTIVE TARGET & COST-EFFICIENCY BENCHMARK")
    print("==================================================")

    for sym, ticks in raw_data.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        print(f"\nEvaluating Adaptive Target Matrix for {sym} ({len(ticks):,} ticks)...")

        # 1. Baseline System C (1.5x ATR Target, 1.0x ATR Stop)
        base_c = run_adaptive_exit_backtest(ticks, spec, target_multiple=1.5, stop_multiple=1.0, max_cost_ratio=50.0)

        # 2. Experiment 1: System C + Adaptive Target Expansion (2.5x ATR Target)
        exp1 = run_adaptive_exit_backtest(ticks, spec, target_multiple=2.5, stop_multiple=1.0, max_cost_ratio=30.0)

        # 3. Experiment 2: System C + Adaptive Target + Adaptive Stop (3.0x ATR Target, 1.5x ATR Stop)
        exp2 = run_adaptive_exit_backtest(ticks, spec, target_multiple=3.0, stop_multiple=1.5, max_cost_ratio=20.0)

        # 4. Experiment 3: Full Adaptive Exit Engine v2 (Cost Ratio < 15%)
        exp3 = run_adaptive_exit_backtest(ticks, spec, target_multiple=4.0, stop_multiple=1.5, max_cost_ratio=15.0)

        benchmark_report[sym] = {
            "baseline_system_c": base_c,
            "exp1_adaptive_targets": exp1,
            "exp2_adaptive_stops": exp2,
            "exp3_full_adaptive_v2": exp3
        }

        print(f"  [BASELINE SYSTEM C] Trades: {base_c['total_trades']} | Win Rate: {base_c['win_rate']}% | Profit Factor: {base_c['profit_factor']} | Net Profit: ${base_c['net_profit']} | Expectancy: {base_c['expectancy_r']} R")
        print(f"  [EXP 1 ADAPTIVE TARGET] Trades: {exp1['total_trades']} | Win Rate: {exp1['win_rate']}% | Profit Factor: {exp1['profit_factor']} | Net Profit: ${exp1['net_profit']} | Expectancy: {exp1['expectancy_r']} R")
        print(f"  [EXP 2 ADAPTIVE STOPS] Trades: {exp2['total_trades']} | Win Rate: {exp2['win_rate']}% | Profit Factor: {exp2['profit_factor']} | Net Profit: ${exp2['net_profit']} | Expectancy: {exp2['expectancy_r']} R")
        print(f"  [EXP 3 FULL ADAPTIVE V2] Trades: {exp3['total_trades']} | Win Rate: {exp3['win_rate']}% | Profit Factor: {exp3['profit_factor']} | Net Profit: ${exp3['net_profit']} | Expectancy: {exp3['expectancy_r']} R")

    out_path = Path(__file__).resolve().parent / "phase21_benchmark_report.json"
    with open(out_path, "w") as f:
        json.dump(benchmark_report, f, indent=2)

    print(f"\n[SUCCESS] Phase 21 Benchmark Report saved to {out_path}")

if __name__ == "__main__":
    run_phase21_benchmark()
