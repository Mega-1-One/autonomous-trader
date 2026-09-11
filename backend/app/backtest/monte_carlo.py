from dataclasses import dataclass, asdict
from typing import Any, Dict, List
import numpy as np

from app.backtest.metrics import BacktestTradeRecord

@dataclass
class MonteCarloSimulationResult:
    iterations: int
    initial_balance: float
    probability_of_ruin_percent: float
    median_net_profit: float
    p95_net_profit: float
    p5_net_profit: float
    median_max_drawdown_percent: float
    p95_max_drawdown_percent: float
    expected_losing_streak: float
    drawdown_distribution: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class MonteCarloSimulator:
    """Monte Carlo Simulation Engine randomizing trade sequence & slippage."""

    def __init__(self, iterations: int = 500, ruin_threshold_percent: float = 50.0):
        self.iterations = iterations
        self.ruin_threshold_percent = ruin_threshold_percent

    def run_simulation(
        self, initial_balance: float, trades: List[BacktestTradeRecord]
    ) -> MonteCarloSimulationResult:
        if not trades:
            return MonteCarloSimulationResult(
                iterations=self.iterations,
                initial_balance=initial_balance,
                probability_of_ruin_percent=0.0,
                median_net_profit=0.0,
                p95_net_profit=0.0,
                p5_net_profit=0.0,
                median_max_drawdown_percent=0.0,
                p95_max_drawdown_percent=0.0,
                expected_losing_streak=0.0,
                drawdown_distribution=[]
            )

        pnls = np.array([t.pnl for t in trades])
        ruin_count = 0
        final_profits: List[float] = []
        max_drawdowns: List[float] = []
        losing_streaks: List[int] = []

        rng = np.random.default_rng(seed=42)

        for _ in range(self.iterations):
            # Reshuffle trades
            shuffled_pnls = rng.choice(pnls, size=len(pnls), replace=True)
            # Add random slippage noise (+- 5% noise)
            noise = rng.normal(1.0, 0.05, size=len(pnls))
            sim_pnls = shuffled_pnls * noise

            balance = initial_balance
            peak = initial_balance
            max_dd_pct = 0.0
            ruined = False

            curr_streak = 0
            max_streak = 0

            for p in sim_pnls:
                balance += p
                if balance > peak:
                    peak = balance
                dd_pct = ((peak - balance) / peak) * 100.0 if peak > 0 else 0.0
                if dd_pct > max_dd_pct:
                    max_dd_pct = dd_pct

                if dd_pct >= self.ruin_threshold_percent or balance <= 0:
                    ruined = True

                if p <= 0:
                    curr_streak += 1
                    max_streak = max(max_streak, curr_streak)
                else:
                    curr_streak = 0

            if ruined:
                ruin_count += 1

            final_profits.append(round(float(balance - initial_balance), 2))
            max_drawdowns.append(round(float(max_dd_pct), 2))
            losing_streaks.append(max_streak)

        prob_ruin = round((ruin_count / self.iterations) * 100.0, 2)
        med_profit = round(float(np.median(final_profits)), 2)
        p95_profit = round(float(np.percentile(final_profits, 95)), 2)
        p5_profit = round(float(np.percentile(final_profits, 5)), 2)

        med_dd = round(float(np.median(max_drawdowns)), 2)
        p95_dd = round(float(np.percentile(max_drawdowns, 95)), 2)
        exp_streak = round(float(np.mean(losing_streaks)), 1)

        return MonteCarloSimulationResult(
            iterations=self.iterations,
            initial_balance=initial_balance,
            probability_of_ruin_percent=prob_ruin,
            median_net_profit=med_profit,
            p95_net_profit=p95_profit,
            p5_net_profit=p5_profit,
            median_max_drawdown_percent=med_dd,
            p95_max_drawdown_percent=p95_dd,
            expected_losing_streak=exp_streak,
            drawdown_distribution=sorted(max_drawdowns)
        )
