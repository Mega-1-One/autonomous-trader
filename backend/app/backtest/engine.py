from typing import Any, Dict, List, Optional
import uuid

from app.core.pricing import contract_size as spec_contract_size
from app.strategy.engine import StrategyEngine
from app.risk.engine import RiskEngine
from app.backtest.metrics import (
    BacktestTradeRecord,
    EquityPoint,
    BacktestMetricsReport,
    BacktestMetricsCalculator,
)

class BacktestEngine:
    """Deterministic, Zero-Lookahead Backtesting Engine sharing exact live strategy and risk logic."""

    def __init__(
        self,
        initial_balance: float = 10000.0,
        spread_pips: float = 1.0,
        slippage_pips: float = 0.5,
        commission_per_lot: float = 7.0
    ):
        self.initial_balance = initial_balance
        self.spread_pips = spread_pips
        self.slippage_pips = slippage_pips
        self.commission_per_lot = commission_per_lot

        self.strategy_engine = StrategyEngine()
        self.risk_engine = RiskEngine()

    def run(
        self,
        symbol: str,
        candles: List[Dict[str, Any]],
        point_size: float = 0.01,
        symbol_info: Optional[Dict[str, Any]] = None,
    ) -> BacktestMetricsReport:
        """Executes backtest over historical candle series without look-ahead bias."""
        balance = self.initial_balance
        equity = balance
        trades: List[BacktestTradeRecord] = []
        equity_curve: List[EquityPoint] = []

        open_position: Optional[Dict[str, Any]] = None
        # Spec-derived symbol info (ADR-4 precedence: broker symbol_info overrides
        # the static spec for point/tick/contract/volume; legacy point-size
        # fallback only when no broker info is available).
        broker = symbol_info or {}
        tick_size = broker.get("tick_size", point_size)
        tick_value = broker.get("tick_value", 1.0 if point_size >= 0.01 else 10.0)
        contract = broker.get("contract_size")
        if not contract or contract <= 0:
            contract = spec_contract_size(
                symbol,
                symbol_info={"point_size": broker.get("point_size", point_size)},
            )
        symbol_info = {
            "tick_size": tick_size,
            "tick_value": tick_value,
            "contract_size": contract,
            "min_volume": broker.get("min_volume", 0.01),
            "max_volume": broker.get("max_volume", 100.0),
            "volume_step": broker.get("volume_step", 0.01),
        }

        n = len(candles)
        if n < 30:
            return BacktestMetricsCalculator.calculate(self.initial_balance, [], [])

        peak_equity = self.initial_balance

        for i in range(25, n):
            current_candle = candles[i]
            history = candles[: i + 1]  # Zero lookahead slice

            # 1. Manage existing open position
            if open_position:
                pos = open_position
                direction = pos["direction"]
                entry = pos["entry_price"]
                sl = pos["stop_loss"]
                tp = pos["take_profit"]
                vol = pos["volume"]

                high = current_candle["high"]
                low = current_candle["low"]
                close = current_candle["close"]

                exit_price: Optional[float] = None
                exit_reason: Optional[str] = None

                if direction == "LONG":
                    if low <= sl:
                        exit_price = sl - (self.slippage_pips * point_size)
                        exit_reason = "STOP_LOSS"
                    elif high >= tp:
                        exit_price = tp
                        exit_reason = "TAKE_PROFIT"
                elif direction == "SHORT":
                    if high >= sl:
                        exit_price = sl + (self.slippage_pips * point_size)
                        exit_reason = "STOP_LOSS"
                    elif low <= tp:
                        exit_price = tp
                        exit_reason = "TAKE_PROFIT"

                if exit_price is not None and exit_reason is not None:
                    # Calculate PnL
                    price_diff = (
                        (exit_price - entry) if direction == "LONG" else (entry - exit_price)
                    )
                    raw_pnl = price_diff * (symbol_info["contract_size"]) * vol
                    commission = vol * self.commission_per_lot
                    net_trade_pnl = raw_pnl - commission

                    risk_dist = abs(entry - sl)
                    r_mult = round(price_diff / risk_dist, 2) if risk_dist > 0 else 0.0

                    balance += net_trade_pnl
                    equity = balance

                    trades.append(
                        BacktestTradeRecord(
                            trade_id=pos["trade_id"],
                            symbol=symbol,
                            direction=direction,
                            entry_price=entry,
                            exit_price=round(exit_price, 4),
                            stop_loss=sl,
                            take_profit=tp,
                            volume=vol,
                            pnl=round(net_trade_pnl, 2),
                            r_multiple=r_mult,
                            entry_time=pos["entry_time"],
                            exit_time=current_candle["timestamp"],
                            exit_reason=exit_reason,
                        )
                    )
                    open_position = None

            # 2. Evaluate new entries if no position open
            if not open_position:
                signal = self.strategy_engine.evaluate_setup(
                    symbol=symbol,
                    htf_candles=history,
                    ltf_candles=history,
                    point_size=point_size,
                )

                if signal.status == "APPROVED":
                    acc_info = {"equity": equity}
                    decision = self.risk_engine.evaluate_trade_risk(
                        signal=signal.to_dict(),
                        account_info=acc_info,
                        symbol_info=symbol_info,
                        current_open_positions_count=0,
                        current_spread_pips=self.spread_pips,
                    )

                    if decision.approved:
                        open_position = {
                            "trade_id": f"BT_{uuid.uuid4().hex[:6].upper()}",
                            "direction": signal.direction,
                            "entry_price": signal.entry_price,
                            "stop_loss": signal.stop_loss,
                            "take_profit": signal.take_profit,
                            "volume": decision.calculated_volume,
                            "entry_time": current_candle["timestamp"],
                        }

            # Update equity curve
            if equity > peak_equity:
                peak_equity = equity
            dd_pct = round(((peak_equity - equity) / peak_equity) * 100.0, 2) if peak_equity > 0 else 0.0
            equity_curve.append(
                EquityPoint(
                    timestamp=current_candle["timestamp"],
                    equity=round(equity, 2),
                    drawdown_percent=dd_pct,
                )
            )

        return BacktestMetricsCalculator.calculate(self.initial_balance, trades, equity_curve)
