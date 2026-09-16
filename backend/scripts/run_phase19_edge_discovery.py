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

from app.research.dataset import SignalResearchObservation
from app.research.labeler import OutcomeLabeler
from app.research.calibration import ProbabilityCalibrator
from app.research.walk_forward_split import WalkForwardCalibrator
from app.research.edge_discovery import EdgeDiscoveryEngine

from app.research.common.mt5_ticks import fetch_real_ticks  # C-04 shared helper

def generate_and_label_observations(ticks: list, spec: InstrumentSpecification) -> List[SignalResearchObservation]:
    tick_engine = TickEngine(max_stale_seconds=float('inf'))
    feat_engine = FeatureEngine()
    tech_analyzer = TechnicalAnalyzer()
    struct_analyzer = MarketStructureAnalyzer()
    liq_analyzer = LiquidityAnalyzer()
    cost_filter = CostFilter(commission_per_lot=7.0, base_slippage_pips=0.1)
    ev_engine = ExpectedValueEngine()
    fusion_engine = SignalFusionEngine2()
    adaptive_exit = AdaptiveExitEngine()
    labeler = OutcomeLabeler()

    price_history = []
    observations = []

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

        results = [
            struct_analyzer.analyze(feats, spec, price_history),
            tech_analyzer.analyze(feats, spec, price_history),
            liq_analyzer.analyze(feats, spec, price_history)
        ]

        levels = adaptive_exit.calculate_levels(feats, spec, direction="BUY", rr_ratio=1.5)
        cost_res = cost_filter.evaluate_cost(feats, spec, target_distance_pips=levels.target_distance_pips, volume=0.05)
        ev_est = ev_engine.calculate_ev(
            confidence_score=0.70,
            target_reward_dollars=levels.target_distance_pips * spec.pip_size * 100.0 * 0.05,
            stop_loss_dollars=levels.stop_distance_pips * spec.pip_size * 100.0 * 0.05,
            transaction_cost_dollars=cost_res.total_transaction_cost_dollars
        )

        fused = fusion_engine.evaluate_multi_factor(results, cost_res, ev_est, min_opportunity_score=0.30)

        if fused.direction != "NONE":
            sig_type = "TRADED" if fused.approved else ("QUALIFIED" if fused.opportunity_score >= 0.50 else "NEAR_MISS")
            obs = SignalResearchObservation(
                signal_id=f"SIG_RES_{tick_idx}",
                timestamp=ts,
                symbol=spec.symbol,
                direction=fused.direction,
                signal_type=sig_type,
                regime="MULTI_FACTOR",
                strategy=fused.recommended_strategy,
                opportunity_score=fused.opportunity_score,
                bullish_evidence=fused.bullish_evidence,
                bearish_evidence=fused.bearish_evidence,
                conflict_score=1.0 if fused.conflicting_evidence else 0.0,
                technical_score=results[1].confidence,
                structure_score=results[0].confidence,
                liquidity_score=results[2].confidence,
                momentum_score=feats.normalized_momentum,
                volatility_score=feats.volatility_50t,
                session_score=0.5,
                spread_pips=feats.spread_pips,
                estimated_slippage_pips=0.1,
                estimated_commission_dollars=0.35,
                estimated_total_cost_dollars=cost_res.total_transaction_cost_dollars,
                entry_reference=levels.entry_price,
                stop_reference=levels.stop_loss,
                target_reference=levels.take_profit,
                ev_estimate_raw=ev_est.expected_value_dollars
            )

            future_slice = ticks[tick_idx+1:tick_idx+500]
            labeled_obs = labeler.label_observation(obs, future_slice, spec)
            observations.append(labeled_obs)

    return observations

def run_phase19_benchmark():
    symbol_map = {
        "XAUUSD": "XAUUSDm",
        "EURUSD": "EURUSDm",
        "GBPUSD": "GBPUSDm",
        "NAS100": "USTECm"
    }

    raw_data = fetch_real_ticks(symbol_map)
    if not raw_data:
        return

    all_observations = []
    symbol_reports = {}
    edge_engine = EdgeDiscoveryEngine()

    print("\n==================================================")
    print(" PHASE 19 FEATURE IMPORTANCE & EDGE DISCOVERY")
    print("==================================================")

    for sym, ticks in raw_data.items():
        spec = InstrumentSpecification.get_default_spec(sym)
        print(f"\nAnalyzing Baseline vs Edge Discovery for {sym} ({len(ticks):,} ticks)...")
        obs_list = generate_and_label_observations(ticks, spec)
        all_observations.extend(obs_list)

        decile_res = edge_engine.analyze_opportunity_deciles(obs_list)
        symbol_reports[sym] = {
            "total_candidate_signals": len(obs_list),
            "decile_analysis": [d.to_dict() for d in decile_res]
        }
        print(f"  -> {sym}: Candidate Signals = {len(obs_list):,} | Deciles Calculated = {len(decile_res)}")

    # Overall Combined Walk-Forward & Baseline Comparison
    n = len(all_observations)
    split1 = int(n * 0.60)
    split2 = int(n * 0.80)

    train_obs = all_observations[:split1]
    val_obs = all_observations[split1:split2]
    oos_obs = all_observations[split2:]

    def calibrated_model(s): return 1.0 / (1.0 + np.exp(-(0.0986 * s + 0.2102)))
    baseline_res = edge_engine.evaluate_baseline_comparison(train_obs, val_obs, oos_obs, calibrated_model)
    deciles_overall = edge_engine.analyze_opportunity_deciles(all_observations)

    report_output = {
        "total_research_observations": len(all_observations),
        "baseline_comparison": baseline_res.to_dict(),
        "overall_opportunity_deciles": [d.to_dict() for d in deciles_overall],
        "symbol_reports": symbol_reports
    }

    out_path = Path(__file__).resolve().parent / "phase19_edge_discovery_report.json"
    with open(out_path, "w") as f:
        json.dump(report_output, f, indent=2)

    print(f"\n==================================================")
    print(f" BASELINE VS CALIBRATED MODEL COMPARISON (N = {len(all_observations):,})")
    print(f"==================================================")
    print(f"Out-of-Sample Baseline Brier:    {baseline_res.oos_baseline_brier:.4f}")
    print(f"Out-of-Sample Model Brier:       {baseline_res.oos_model_brier:.4f}")
    print(f"Brier Improvement Over Baseline: {baseline_res.brier_improvement_percent:+.2f}%")
    print(f"Outperforms Baseline:            {baseline_res.outperforms_baseline}")
    print(f"[SUCCESS] Phase 19 Edge Discovery Report saved to {out_path}")

if __name__ == "__main__":
    run_phase19_benchmark()
