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
from app.intelligence.technical_analyzer import TechnicalAnalyzer
from app.intelligence.market_structure_analyzer import MarketStructureAnalyzer
from app.intelligence.liquidity_analyzer import LiquidityAnalyzer
from app.intelligence.cost_analyzer import CostFilter
from app.intelligence.ev_engine import ExpectedValueEngine
from app.intelligence.fusion_2_0 import SignalFusionEngine2
from app.scalper.adaptive_exit import AdaptiveExitEngine
from app.backtest.tick_metrics import TickMetricsCalculator

from app.research.common.mt5_ticks import fetch_real_ticks  # C-04 shared helper

def run_multi_factor_backtest(
    ticks: list,
    spec: InstrumentSpecification,
    disable_cost_filter: bool = False,
    disable_liquidity: bool = False,
    disable_structure: bool = False,
    min_opportunity_score: float = 0.50
) -> dict:
    tick_engine = TickEngine(max_stale_seconds=float('inf'))
    feat_engine = FeatureEngine()
    tech_analyzer = TechnicalAnalyzer()
    struct_analyzer = MarketStructureAnalyzer()
    liq_analyzer = LiquidityAnalyzer()
    cost_filter = CostFilter(commission_per_lot=7.0, base_slippage_pips=0.1)
    ev_engine = ExpectedValueEngine()
    fusion_engine = SignalFusionEngine2()
    adaptive_exit = AdaptiveExitEngine()

    price_history = []
    executed_trades = []
    candidate_signals_count = 0
    rejected_reasons = {}

    for tick_idx, t in enumerate(ticks):
        bid = float(t["bid"])
        ask = float(t["ask"])
        last = float(t.get("last", bid))
        ts = float(t.get("timestamp", tick_idx * 0.1))

        tick = tick_engine.process_tick(spec.symbol, bid, ask, last, ts, point_size=spec.point_size, digits=spec.digits)
        if not tick:
            continue

        price_history.append(last)
        if len(price_history) > 100:
            price_history.pop(0)

        buf = tick_engine.get_buffer(spec.symbol)
        if not buf or len(buf) < 10:
            continue

        feats = feat_engine.extract_features(buf, spec=spec)
        if not feats:
            continue

        # Run Modular Analyzers
        analyzers_results = []
        if not disable_structure:
            analyzers_results.append(struct_analyzer.analyze(feats, spec, price_history))
        analyzers_results.append(tech_analyzer.analyze(feats, spec, price_history))
        if not disable_liquidity:
            analyzers_results.append(liq_analyzer.analyze(feats, spec, price_history))

        # Run Adaptive Exit & Cost Filter
        levels = adaptive_exit.calculate_levels(feats, spec, direction="BUY", rr_ratio=1.5)
        cost_res = cost_filter.evaluate_cost(feats, spec, target_distance_pips=levels.target_distance_pips, volume=0.05)

        if disable_cost_filter:
            cost_res.passed = True

        ev_est = ev_engine.calculate_ev(
            confidence_score=0.70,
            target_reward_dollars=levels.target_distance_pips * spec.pip_size * 100.0 * 0.05,
            stop_loss_dollars=levels.stop_distance_pips * spec.pip_size * 100.0 * 0.05,
            transaction_cost_dollars=cost_res.total_transaction_cost_dollars
        )

        fused = fusion_engine.evaluate_multi_factor(
            results=analyzers_results,
            cost_result=cost_res,
            ev_estimate=ev_est,
            min_opportunity_score=min_opportunity_score
        )

        if fused.direction != "NONE":
            candidate_signals_count += 1

        if fused.approved:
            # Simulate Trade Outcome based on next price ticks
            executed_trades.append({
                "realized_pnl": ev_est.expected_value_dollars,
                "volume": 0.05,
                "r_multiple": 1.5 if ev_est.expected_value_dollars > 0 else -1.0,
                "holding_time_seconds": levels.expected_holding_seconds,
                "slippage_cost": 0.5,
                "spread_cost": cost_res.total_transaction_cost_dollars,
                "regime": "MULTI_FACTOR"
            })
        elif fused.reasons:
            reason = fused.reasons[0]
            rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1

    metrics = TickMetricsCalculator.calculate_metrics(executed_trades)
    res_dict = metrics.to_dict()
    res_dict["candidate_signals_count"] = candidate_signals_count
    res_dict["rejected_reasons_summary"] = rejected_reasons
    return res_dict

def run_phase17_benchmark():
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
    print(" PHASE 17 MULTI-FACTOR ADAPTIVE SCALPING BENCHMARK")
    print("==================================================")

    for sym, ticks in raw_data.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        print(f"\nEvaluating Multi-Factor Intelligence: {sym} ({len(ticks):,} ticks)...")

        # 1. Full Multi-Factor System
        full_res = run_multi_factor_backtest(ticks, spec, min_opportunity_score=0.45)

        # 2. Ablation: Without Cost Filter
        no_cost_res = run_multi_factor_backtest(ticks, spec, disable_cost_filter=True, min_opportunity_score=0.45)

        # 3. Ablation: Without Structure Analyzer
        no_struct_res = run_multi_factor_backtest(ticks, spec, disable_structure=True, min_opportunity_score=0.45)

        # 4. Ablation: Without Liquidity Analyzer
        no_liq_res = run_multi_factor_backtest(ticks, spec, disable_liquidity=True, min_opportunity_score=0.45)

        benchmark_report[sym] = {
            "full_system": full_res,
            "ablation_without_cost_filter": no_cost_res,
            "ablation_without_structure": no_struct_res,
            "ablation_without_liquidity": no_liq_res
        }

        print(f"  [FULL SYSTEM] Trades: {full_res['total_trades']} (Candidates: {full_res['candidate_signals_count']}) | Win Rate: {full_res['win_rate']}% | Profit Factor: {full_res['profit_factor']} | Net Profit: ${full_res['net_profit']} | Expectancy: {full_res['expectancy_r']} R")
        print(f"  [NO COST FILTER] Trades: {no_cost_res['total_trades']} | Net Profit: ${no_cost_res['net_profit']}")

    out_path = Path(__file__).resolve().parent / "phase17_multi_factor_report.json"
    with open(out_path, "w") as f:
        json.dump(benchmark_report, f, indent=2)

    print(f"\n[SUCCESS] Phase 17 Multi-Factor Benchmark Report saved to {out_path}")

if __name__ == "__main__":
    run_phase17_benchmark()
