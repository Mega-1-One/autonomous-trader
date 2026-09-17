"""Shared scalar trade-metric helpers (P-08/C-04).

Single implementations of the win-rate / profit-factor / expectancy
arithmetic recomputed inline across research and backtest code. Engine-level
consolidation of the two metrics calculators (backtest/metrics.py,
backtest/tick_metrics.py) is follow-up material and is NOT attempted here;
these scalar helpers are directly unit-tested.
"""
from typing import List


def win_rate(pnls: List[float]) -> float:
    """Win rate in percent (wins are strictly positive PnLs)."""
    if not pnls:
        return 0.0
    wins = sum(1 for p in pnls if p > 0)
    return round((wins / len(pnls)) * 100.0, 2)


def profit_factor(pnls: List[float]) -> float:
    """Gross profit / gross loss (99.0 when all-winning, 0.0 when empty)."""
    if not pnls:
        return 0.0
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p <= 0))
    if gross_loss > 0:
        return round(gross_profit / gross_loss, 2)
    return 99.0 if gross_profit > 0 else 0.0


def expectancy(pnls: List[float]) -> float:
    """Mean PnL per trade."""
    if not pnls:
        return 0.0
    return round(sum(pnls) / len(pnls), 2)
