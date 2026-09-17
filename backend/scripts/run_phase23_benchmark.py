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
from app.context.price_location import PriceLocationEngine
from app.research.sweep_confluence import SweepConfluenceEngine, SweepConfluenceConfig
from app.scalper.adaptive_exit_v2 import AdaptiveExitEngineV2
from app.intelligence.cost_analyzer import CostFilter
from app.backtest.tick_metrics import TickMetricsCalculator

from app.research.common.mt5_ticks import fetch_real_ticks  # C-04 shared helper

def run_sweep_confluence_backtest(
    ticks: list,
    spec: InstrumentSpecification,
    config: SweepConfluenceConfig
) -> dict:
    tick_engine = TickEngine(max_stale_seconds=float('inf'))
    feat_engine = FeatureEngine()
    tf_engine = TimeframeEngine()
    bias_engine = BiasEngine()
    loc_engine = PriceLocationEngine()
    sweep_engine = SweepConfluenceEngine()
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
        c15m = tf_engine.get_candles("15m")
        loc_res = loc_engine.evaluate_location(c15m, current_price=last)

        is_passed = sweep_engine.evaluate_sweep_confluence(bias_res, loc_res, feats, spec, config)
        if is_passed:
            candidate_count += 1

        direction = "BUY" if "BULLISH" in bias_res.bias else "SELL"
        levels = exit_v2.calculate_exit_levels(feats, spec, direction=direction, atr_multiple_target=3.0, atr_multiple_stop=1.5)
        cost_res = cost_filter.evaluate_cost(feats, spec, target_distance_pips=levels.target_distance_pips, volume=0.05)

        if is_passed and cost_res.passed:
            future_ticks = ticks[tick_idx+1:tick_idx+300]
            is_buy = (direction == "BUY")
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
                "regime": "PHASE_23_SWEEP"
            })

    metrics = TickMetricsCalculator.calculate_metrics(executed_trades)
    res_dict = metrics.to_dict()
    res_dict["candidate_count"] = candidate_count
    return res_dict

def run_phase23_benchmark():
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
    print(" PHASE 23 CONDITIONAL CONFLUENCE LADDER BENCHMARK")
    print("==================================================")

    for sym, ticks in raw_data.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        print(f"\nEvaluating Confluence Ladder for {sym} ({len(ticks):,} ticks)...")

        # Exp A: Sweep Alone
        exp_a = run_sweep_confluence_backtest(ticks, spec, SweepConfluenceConfig())

        # Exp B: Sweep + HTF Bias
        exp_b = run_sweep_confluence_backtest(ticks, spec, SweepConfluenceConfig(require_htf_bias=True))

        # Exp C: Sweep + HTF Bias + Prem/Disc
        exp_c = run_sweep_confluence_backtest(ticks, spec, SweepConfluenceConfig(require_htf_bias=True, require_prem_disc=True))

        # Exp D: Sweep + HTF Bias + Prem/Disc + Structure Shift
        exp_d = run_sweep_confluence_backtest(ticks, spec, SweepConfluenceConfig(require_htf_bias=True, require_prem_disc=True, require_structure_shift=True))

        # Exp E: Sweep + HTF Bias + Prem/Disc + Structure Shift + Displacement
        exp_e = run_sweep_confluence_backtest(ticks, spec, SweepConfluenceConfig(require_htf_bias=True, require_prem_disc=True, require_structure_shift=True, require_displacement=True))

        # Exp F: Sweep + HTF Bias + Prem/Disc + Structure Shift + Displacement + 1M Confirm
        exp_f = run_sweep_confluence_backtest(ticks, spec, SweepConfluenceConfig(require_htf_bias=True, require_prem_disc=True, require_structure_shift=True, require_displacement=True, require_ltf_confirm=True))

        benchmark_report[sym] = {
            "exp_a_sweep_alone": exp_a,
            "exp_b_htf_bias": exp_b,
            "exp_c_prem_disc": exp_c,
            "exp_d_structure_shift": exp_d,
            "exp_e_displacement": exp_e,
            "exp_f_full_confluence": exp_f
        }

        print(f"  [EXP A - SWEEP ALONE]      Trades: {exp_a['total_trades']} | Win Rate: {exp_a['win_rate']}% | Profit Factor: {exp_a['profit_factor']} | Net Profit: ${exp_a['net_profit']} | Expectancy: {exp_a['expectancy_r']} R")
        print(f"  [EXP B - HTF BIAS]         Trades: {exp_b['total_trades']} | Win Rate: {exp_b['win_rate']}% | Profit Factor: {exp_b['profit_factor']} | Net Profit: ${exp_b['net_profit']} | Expectancy: {exp_b['expectancy_r']} R")
        print(f"  [EXP C - PREM/DISC]        Trades: {exp_c['total_trades']} | Win Rate: {exp_c['win_rate']}% | Profit Factor: {exp_c['profit_factor']} | Net Profit: ${exp_c['net_profit']} | Expectancy: {exp_c['expectancy_r']} R")
        print(f"  [EXP F - FULL CONFLUENCE]  Trades: {exp_f['total_trades']} | Win Rate: {exp_f['win_rate']}% | Profit Factor: {exp_f['profit_factor']} | Net Profit: ${exp_f['net_profit']} | Expectancy: {exp_f['expectancy_r']} R")

    out_path = Path(__file__).resolve().parent / "phase23_benchmark_report.json"
    with open(out_path, "w") as f:
        json.dump(benchmark_report, f, indent=2)

    print(f"\n[SUCCESS] Phase 23 Benchmark Report saved to {out_path}")

if __name__ == "__main__":
    run_phase23_benchmark()
