import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List
import numpy as np

@dataclass
class BacktestTradeRecord:
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    stop_loss: float
    take_profit: float
    volume: float
    pnl: float
    r_multiple: float
    entry_time: str
    exit_time: str
    exit_reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class EquityPoint:
    timestamp: str
    equity: float
    drawdown_percent: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class BacktestMetricsReport:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    profit_factor: float
    expectancy: float
    average_r: float
    max_drawdown_amount: float
    max_drawdown_percent: float
    sharpe_ratio: float
    sortino_ratio: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    largest_win: float
    largest_loss: float
    equity_curve: List[EquityPoint]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["equity_curve"] = [e.to_dict() for e in self.equity_curve]
        return d

class BacktestMetricsCalculator:
    """Calculates quantitative performance and risk metrics for backtesting."""

    @staticmethod
    def calculate(
        initial_balance: float,
        trades: List[BacktestTradeRecord],
        equity_curve: List[EquityPoint]
    ) -> BacktestMetricsReport:
        if not trades:
            return BacktestMetricsReport(
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
                gross_profit=0.0, gross_loss=0.0, net_profit=0.0, profit_factor=0.0,
                expectancy=0.0, average_r=0.0, max_drawdown_amount=0.0, max_drawdown_percent=0.0,
                sharpe_ratio=0.0, sortino_ratio=0.0, max_consecutive_wins=0, max_consecutive_losses=0,
                largest_win=0.0, largest_loss=0.0, equity_curve=equity_curve
            )

        total_trades = len(trades)
        pnls = [t.pnl for t in trades]
        r_multiples = [t.r_multiple for t in trades]

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = round((winning_trades / total_trades) * 100.0, 2)

        gross_profit = round(float(sum(wins)), 2)
        gross_loss = round(float(abs(sum(losses))), 2)
        net_profit = round(gross_profit - gross_loss, 2)

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        expectancy = round(net_profit / total_trades, 2)
        average_r = round(float(np.mean(r_multiples)), 2)

        largest_win = round(float(max(pnls)), 2) if pnls else 0.0
        largest_loss = round(float(min(pnls)), 2) if pnls else 0.0

        # Calculate max drawdown from equity curve
        max_dd_amount = 0.0
        max_dd_pct = 0.0
        peak = initial_balance

        for pt in equity_curve:
            if pt.equity > peak:
                peak = pt.equity
            dd = peak - pt.equity
            dd_pct = (dd / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd_amount:
                max_dd_amount = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # Consecutive streak calculation
        max_c_wins = 0
        max_c_losses = 0
        curr_wins = 0
        curr_losses = 0

        for p in pnls:
            if p > 0:
                curr_wins += 1
                curr_losses = 0
                max_c_wins = max(max_c_wins, curr_wins)
            else:
                curr_losses += 1
                curr_wins = 0
                max_c_losses = max(max_c_losses, curr_losses)

        # Sharpe & Sortino calculation
        returns = np.array(pnls) / initial_balance
        avg_ret = np.mean(returns)
        std_ret = np.std(returns)

        sharpe_ratio = round(float((avg_ret / std_ret) * math.sqrt(252)), 2) if std_ret > 0 else 0.0

        downside_returns = returns[returns < 0]
        downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0.0
        sortino_ratio = round(float((avg_ret / downside_std) * math.sqrt(252)), 2) if downside_std > 0 else 0.0

        return BacktestMetricsReport(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=net_profit,
            profit_factor=profit_factor,
            expectancy=expectancy,
            average_r=average_r,
            max_drawdown_amount=round(max_dd_amount, 2),
            max_drawdown_percent=round(max_dd_pct, 2),
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_consecutive_wins=max_c_wins,
            max_consecutive_losses=max_c_losses,
            largest_win=largest_win,
            largest_loss=largest_loss,
            equity_curve=equity_curve
        )
