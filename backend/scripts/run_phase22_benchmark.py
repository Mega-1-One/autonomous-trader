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
from app.context.bias_engine import BiasEngine
from app.context.price_location import PriceLocationEngine
from app.context.setup_classifier import SetupClassifier
from app.scalper.adaptive_exit_v2 import AdaptiveExitEngineV2
from app.intelligence.cost_analyzer import CostFilter
from app.backtest.tick_metrics import TickMetricsCalculator

def fetch_real_ticks(symbol_map: dict) -> dict:
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return {}

    import MetaTrader5 as mt5

    dataset = {}
    utc_from = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
    utc_to = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)

    for canonical, broker_symbol in symbol_map.items():
        print(f"Ingesting real ticks for {canonical} ({broker_symbol})...")
        raw_ticks = mt5.copy_ticks_range(broker_symbol, utc_from, utc_to, mt5.COPY_TICKS_ALL)
        if raw_ticks is not None and len(raw_ticks) > 0:
            step = max(1, len(raw_ticks) // 25000)
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
            print(f"  -> {canonical}: Loaded {len(parsed):,} real Exness ticks.")

    adapter.disconnect()
    return dataset

def run_independent_setup_backtest(
    ticks: list,
    spec: InstrumentSpecification,
    setup_filter: str = "TREND_CONTINUATION",
    require_ltf_confirm: bool = True
) -> dict:
    tick_engine = TickEngine(max_stale_seconds=float('inf'))
    feat_engine = FeatureEngine()
    tf_engine = TimeframeEngine()
    bias_engine = BiasEngine()
    loc_engine = PriceLocationEngine()
    classifier = SetupClassifier()
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

        setup_res = classifier.classify_setup(bias_res, loc_res, feats, spec, target_setup_filter=setup_filter)

        if setup_res.setup_type != "NO_SETUP":
            candidate_count += 1

        if not require_ltf_confirm:
            setup_res.approved = (setup_res.setup_type != "NO_SETUP")

        levels = exit_v2.calculate_exit_levels(feats, spec, direction=setup_res.direction if setup_res.direction != "NONE" else "BUY", atr_multiple_target=3.0, atr_multiple_stop=1.5)
        cost_res = cost_filter.evaluate_cost(feats, spec, target_distance_pips=levels.target_distance_pips, volume=0.05)

        if setup_res.approved and cost_res.passed:
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
                "regime": "PHASE_22_ENTRY"
            })

    metrics = TickMetricsCalculator.calculate_metrics(executed_trades)
    res_dict = metrics.to_dict()
    res_dict["candidate_setups_count"] = candidate_count
    return res_dict

def run_phase22_benchmark():
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
    print(" PHASE 22 INDEPENDENT SETUP ENTRY BENCHMARK")
    print("==================================================")

    for sym, ticks in raw_data.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        print(f"\nEvaluating Contextual Setup Entry Engine for {sym} ({len(ticks):,} ticks)...")

        # 1. Setup: TREND_CONTINUATION
        tc_res = run_independent_setup_backtest(ticks, spec, setup_filter="TREND_CONTINUATION", require_ltf_confirm=True)

        # 2. Setup: LIQUIDITY_SWEEP_REVERSAL
        ls_res = run_independent_setup_backtest(ticks, spec, setup_filter="LIQUIDITY_SWEEP_REVERSAL", require_ltf_confirm=True)

        # 3. Setup: BREAKOUT_RETEST
        br_res = run_independent_setup_backtest(ticks, spec, setup_filter="BREAKOUT_RETEST", require_ltf_confirm=True)

        # 4. Entry Timing Test: TREND_CONTINUATION (Immediate vs 1M Confirmation)
        imm_res = run_independent_setup_backtest(ticks, spec, setup_filter="TREND_CONTINUATION", require_ltf_confirm=False)

        benchmark_report[sym] = {
            "trend_continuation": tc_res,
            "liquidity_sweep_reversal": ls_res,
            "breakout_retest": br_res,
            "immediate_entry_unconfirmed": imm_res
        }

        print(f"  [TREND CONTINUATION] Trades: {tc_res['total_trades']} | Win Rate: {tc_res['win_rate']}% | Profit Factor: {tc_res['profit_factor']} | Net Profit: ${tc_res['net_profit']} | Expectancy: {tc_res['expectancy_r']} R")
        print(f"  [LIQUIDITY SWEEP]    Trades: {ls_res['total_trades']} | Win Rate: {ls_res['win_rate']}% | Profit Factor: {ls_res['profit_factor']} | Net Profit: ${ls_res['net_profit']} | Expectancy: {ls_res['expectancy_r']} R")
        print(f"  [IMMEDIATE ENTRY]    Trades: {imm_res['total_trades']} | Win Rate: {imm_res['win_rate']}% | Profit Factor: {imm_res['profit_factor']} | Net Profit: ${imm_res['net_profit']} | Expectancy: {imm_res['expectancy_r']} R")

    out_path = Path(__file__).resolve().parent / "phase22_benchmark_report.json"
    with open(out_path, "w") as f:
        json.dump(benchmark_report, f, indent=2)

    print(f"\n[SUCCESS] Phase 22 Benchmark Report saved to {out_path}")

if __name__ == "__main__":
    run_phase22_benchmark()
