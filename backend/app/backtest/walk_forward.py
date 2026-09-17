from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import numpy as np

from app.backtest.tick_backtest import TickBacktestEngine
from app.backtest.tick_metrics import TickBacktestMetrics, TickMetricsCalculator

# N2-M5: walk-forward Monte Carlo treats ruin as a >20% drawdown. Deliberately
# distinct from MONTE_CARLO_RUIN_THRESHOLD_PERCENT (different methodology).
WALK_FORWARD_RUIN_THRESHOLD_PERCENT = 20.0

@dataclass
class WalkForwardReport:
    total_windows: int
    train_metrics: TickBacktestMetrics
    validation_metrics: TickBacktestMetrics
    out_of_sample_metrics: TickBacktestMetrics
    robustness_score: float
    passed: bool
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class WalkForwardValidator:
    """Walk-Forward Rolling Window Validation Engine."""

    def __init__(self, engine: Optional[TickBacktestEngine] = None):
        if engine is None:
            engine = TickBacktestEngine()
        self.engine = engine

    def run_walk_forward(self, historical_ticks: List[Dict[str, Any]]) -> WalkForwardReport:
        n = len(historical_ticks)
        if n < 300:
            empty_m = TickMetricsCalculator.calculate_metrics([])
            return WalkForwardReport(
                total_windows=3,
                train_metrics=empty_m,
                validation_metrics=empty_m,
                out_of_sample_metrics=empty_m,
                robustness_score=0.0,
                passed=False,
                summary="Insufficient ticks for Walk-Forward validation (min 300 required)"
            )

        split1 = int(n * 0.50)
        split2 = int(n * 0.75)

        train_ticks = historical_ticks[:split1]
        val_ticks = historical_ticks[split1:split2]
        oos_ticks = historical_ticks[split2:]

        train_m = self.engine.run_backtest(train_ticks)
        val_m = self.engine.run_backtest(val_ticks)
        oos_m = self.engine.run_backtest(oos_ticks)

        # Robustness ratio: OOS Expectancy / Train Expectancy
        train_exp = max(0.01, train_m.expectancy_r)
        oos_exp = oos_m.expectancy_r
        robustness = round(oos_exp / train_exp, 2)

        passed = (oos_m.validation_passed and robustness >= 0.5)
        summary = "PASS: Out-of-Sample edge sustained across rolling windows" if passed else "FAIL: Edge degraded in Out-of-Sample evaluation"

        return WalkForwardReport(
            total_windows=3,
            train_metrics=train_m,
            validation_metrics=val_m,
            out_of_sample_metrics=oos_m,
            robustness_score=robustness,
            passed=passed,
            summary=summary
        )

class TickMonteCarloSimulator:
    """500-Iteration Trade Sequence Randomization & Drawdown Distribution Analysis."""

    def run_monte_carlo(self, trades: List[Dict[str, Any]], iterations: int = 500, initial_balance: float = 10000.0, seed: int = 42,
                          ruin_threshold_percent: float = WALK_FORWARD_RUIN_THRESHOLD_PERCENT) -> Dict[str, Any]:
        if not trades:
            return {
                "iterations": iterations,
                "median_net_profit": 0.0,
                "median_max_drawdown_percent": 0.0,
                "probability_of_ruin_percent": 0.0,
                "max_losing_streak_95th_percentile": 0
            }

        pnls = [t.get("realized_pnl", 0.0) for t in trades]
        net_profits = []
        max_drawdowns = []
        losing_streaks = []
        ruin_count = 0

        rng = np.random.default_rng(seed)  # P-09/C-02: seeded reproducibility

        for _ in range(iterations):
            shuffled = rng.choice(pnls, size=len(pnls), replace=True)
            equity = initial_balance
            peak = initial_balance
            max_dd = 0.0
            streak = 0
            max_streak = 0

            for pnl in shuffled:
                equity += pnl
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak * 100.0 if peak > 0 else 0.0
                max_dd = max(max_dd, dd)

                if pnl < 0:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 0

            net_profits.append(equity - initial_balance)
            max_drawdowns.append(max_dd)
            losing_streaks.append(max_streak)

            if max_dd > ruin_threshold_percent:
                ruin_count += 1

        return {
            "iterations": iterations,
            "median_net_profit": round(float(np.median(net_profits)), 2),
            "median_max_drawdown_percent": round(float(np.median(max_drawdowns)), 2),
            "probability_of_ruin_percent": round((ruin_count / iterations) * 100.0, 2),
            "max_losing_streak_95th_percentile": int(np.percentile(losing_streaks, 95))
        }
