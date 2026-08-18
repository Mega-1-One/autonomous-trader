from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import numpy as np

@dataclass
class TickBacktestMetrics:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy_r: float
    profit_factor: float
    avg_r_multiple: float
    max_drawdown_percent: float
    max_consecutive_losses: int
    avg_holding_time_sec: float
    median_holding_time_sec: float
    gross_profit: float
    gross_loss: float
    spread_cost: float
    slippage_cost: float
    commission_cost: float
    net_profit: float
    regime_breakdown: Dict[str, Any]
    validation_passed: bool
    validation_reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class TickMetricsCalculator:
    """Calculates comprehensive performance metrics and regime breakdowns for tick backtesting."""

    @staticmethod
    def calculate_metrics(
        trades: List[Dict[str, Any]],
        initial_balance: float = 10000.0,
        commission_per_lot: float = 7.0,
        min_expectancy_r: float = 0.15,
        min_profit_factor: float = 1.2,
        max_drawdown_limit: float = 10.0
    ) -> TickBacktestMetrics:
        if not trades:
            return TickBacktestMetrics(
                total_trades=0, wins=0, losses=0, win_rate=0.0, avg_win=0.0, avg_loss=0.0,
                expectancy_r=0.0, profit_factor=0.0, avg_r_multiple=0.0, max_drawdown_percent=0.0,
                max_consecutive_losses=0, avg_holding_time_sec=0.0, median_holding_time_sec=0.0,
                gross_profit=0.0, gross_loss=0.0, spread_cost=0.0, slippage_cost=0.0,
                commission_cost=0.0, net_profit=0.0, regime_breakdown={},
                validation_passed=False, validation_reasons=["No trades executed"]
            )

        total_trades = len(trades)
        pnls = []
        r_multiples = []
        holding_times = []

        gross_profit = 0.0
        gross_loss = 0.0
        total_commission = 0.0
        total_slippage_cost = 0.0
        total_spread_cost = 0.0

        wins = 0
        losses = 0

        current_streak = 0
        max_consecutive_losses = 0

        equity = initial_balance
        peak_equity = initial_balance
        max_drawdown_amount = 0.0
        max_drawdown_pct = 0.0

        regime_stats: Dict[str, Dict[str, Any]] = {}

        for t in trades:
            raw_pnl = t.get("realized_pnl", 0.0)
            vol = t.get("volume", 0.05)
            comm = vol * commission_per_lot
            slip_cost = t.get("slippage_cost", 0.0)
            sprd_cost = t.get("spread_cost", 0.0)

            net_trade_pnl = raw_pnl - comm - slip_cost
            pnls.append(net_trade_pnl)

            r_mult = t.get("r_multiple", 0.0)
            r_multiples.append(r_mult)

            hold_t = t.get("holding_time_seconds", 0.0)
            holding_times.append(hold_t)

            total_commission += comm
            total_slippage_cost += slip_cost
            total_spread_cost += sprd_cost

            if net_trade_pnl > 0:
                wins += 1
                gross_profit += net_trade_pnl
                current_streak = 0
            else:
                losses += 1
                gross_loss += abs(net_trade_pnl)
                current_streak += 1
                max_consecutive_losses = max(max_consecutive_losses, current_streak)

            equity += net_trade_pnl
            if equity > peak_equity:
                peak_equity = equity
            dd = peak_equity - equity
            dd_pct = (dd / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            max_drawdown_amount = max(max_drawdown_amount, dd)
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)

            # Regime Breakdown
            reg = t.get("regime", "UNKNOWN")
            if reg not in regime_stats:
                regime_stats[reg] = {"trades": 0, "wins": 0, "net_pnl": 0.0}
            regime_stats[reg]["trades"] += 1
            if net_trade_pnl > 0:
                regime_stats[reg]["wins"] += 1
            regime_stats[reg]["net_pnl"] = round(regime_stats[reg]["net_pnl"] + net_trade_pnl, 2)

        win_rate = round((wins / total_trades) * 100.0, 2)
        avg_win = round(gross_profit / wins, 2) if wins > 0 else 0.0
        avg_loss = round(gross_loss / losses, 2) if losses > 0 else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        avg_r = round(float(np.mean(r_multiples)), 2) if r_multiples else 0.0

        loss_rate = losses / total_trades
        expectancy_r = round((win_rate / 100.0 * (avg_win / max(1.0, avg_loss))) - (loss_rate * 1.0), 2) if avg_loss > 0 else round(avg_r, 2)

        avg_hold = round(float(np.mean(holding_times)), 2) if holding_times else 0.0
        med_hold = round(float(np.median(holding_times)), 2) if holding_times else 0.0
        net_profit = round(equity - initial_balance, 2)

        # Validation Checks
        val_reasons = []
        val_passed = True

        if expectancy_r < min_expectancy_r:
            val_passed = False
            val_reasons.append(f"Expectancy ({expectancy_r} R) below threshold ({min_expectancy_r} R)")

        if profit_factor < min_profit_factor:
            val_passed = False
            val_reasons.append(f"Profit Factor ({profit_factor}) below threshold ({min_profit_factor})")

        if max_drawdown_pct > max_drawdown_limit:
            val_passed = False
            val_reasons.append(f"Max Drawdown ({max_drawdown_pct}%) exceeds limit ({max_drawdown_limit}%)")

        if val_passed:
            val_reasons.append("Strategy Edge Validated: Positive Expectancy & Risk Metrics Passed")

        return TickBacktestMetrics(
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            expectancy_r=expectancy_r,
            profit_factor=profit_factor,
            avg_r_multiple=avg_r,
            max_drawdown_percent=round(max_drawdown_pct, 2),
            max_consecutive_losses=max_consecutive_losses,
            avg_holding_time_sec=avg_hold,
            median_holding_time_sec=med_hold,
            gross_profit=round(gross_profit, 2),
            gross_loss=round(gross_loss, 2),
            spread_cost=round(total_spread_cost, 2),
            slippage_cost=round(total_slippage_cost, 2),
            commission_cost=round(total_commission, 2),
            net_profit=net_profit,
            regime_breakdown=regime_stats,
            validation_passed=val_passed,
            validation_reasons=val_reasons
        )
