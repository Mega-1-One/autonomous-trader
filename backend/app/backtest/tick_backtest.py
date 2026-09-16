import time
from typing import Any, Dict, List, Optional
import numpy as np

from app.scalper.tick_engine import TickEngine
from app.scalper.features import FeatureEngine
from app.scalper.strategy import ScalpStrategyEngine
from app.scalper.selector import StrategySelector
from app.scalper.instrument import InstrumentSpecification
from app.scalper.diagnostics import DiagnosticFunnel
from app.regime.engine import MarketRegimeEngine
from app.fusion.engine import SignalFusionEngine
from app.risk.engine import RiskEngine
from app.scalper.position_manager import ScalpPositionManager, ScalpPosition
from app.scalper.cooldown import CooldownManager
from app.backtest.tick_metrics import TickMetricsCalculator, TickBacktestMetrics

class TickBacktestEngine:
    """Zero-Lookahead Tick-by-Tick Simulation & Diagnostic Engine for normalized scalping strategies."""

    def __init__(
        self,
        symbol: str = "XAUUSD",
        initial_balance: float = 10000.0,
        latency_ms: float = 50.0,
        base_slippage_pips: float = 0.1,
        commission_per_lot: float = 7.0,
        spec: Optional[InstrumentSpecification] = None,
        point_size: float = 0.001,
        digits: int = 3,
        min_opportunity_score: float = 0.65,
        min_norm_momentum: float = 0.8,
        min_imbalance_edge: float = 0.05,
        diagnostic_mode: bool = True
    ):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.latency_ms = latency_ms
        self.base_slippage_pips = base_slippage_pips
        self.commission_per_lot = commission_per_lot
        self.min_opportunity_score = min_opportunity_score
        self.min_norm_momentum = min_norm_momentum
        self.min_imbalance_edge = min_imbalance_edge
        self.diagnostic_mode = diagnostic_mode

        if spec is None:
            spec = InstrumentSpecification.get_default_spec(symbol)
        self.spec = spec

        self.point_size = spec.point_size
        self.digits = spec.digits

        # Instantiating Live Production Components
        self.tick_engine = TickEngine(max_stale_seconds=float('inf'))
        self.feature_engine = FeatureEngine()
        self.regime_engine = MarketRegimeEngine()
        self.selector = StrategySelector()
        max_spread = 300.0 if self.spec.asset_class.name == "INDICES" else 3.0
        self.scalp_strategy = ScalpStrategyEngine(
            max_allowed_spread=max_spread,
            min_norm_momentum=self.min_norm_momentum,
            min_imbalance_edge=self.min_imbalance_edge
        )
        self.fusion_engine = SignalFusionEngine()
        self.risk_engine = RiskEngine(config={"minimum_rr": 1.5, "maximum_spread_pips": max_spread})


        self.position_manager = ScalpPositionManager(max_holding_seconds=30.0)
        self.cooldown_manager = CooldownManager(cooldown_seconds=15, max_consecutive_losses=3)
        self.funnel = DiagnosticFunnel()

    def run_backtest(self, historical_ticks: List[Dict[str, Any]]) -> TickBacktestMetrics:
        """Processes 100% of historical ticks sequentially and tracks complete diagnostic funnel."""
        executed_trades: List[Dict[str, Any]] = []
        self.funnel = DiagnosticFunnel()

        symbol_info = {
            "digits": self.spec.digits,
            "point_size": self.spec.point_size,
            "tick_size": self.spec.tick_size,
            "tick_value": 1.0,
            "min_volume": self.spec.volume_min,
            "max_volume": self.spec.volume_max,
            "volume_step": self.spec.volume_step
        }
        account_info = {"equity": self.initial_balance}

        pending_orders: List[Dict[str, Any]] = []

        for tick_idx, t in enumerate(historical_ticks):
            self.funnel.raw_ticks_ingested += 1
            bid = float(t["bid"])
            ask = float(t["ask"])
            last = float(t.get("last", bid))
            ts = float(t.get("timestamp", tick_idx * 0.1))

            # 1. Process Tick in TickEngine
            tick = self.tick_engine.process_tick(
                symbol=self.symbol,
                bid=bid,
                ask=ask,
                last=last,
                timestamp=ts,
                point_size=self.spec.point_size,
                digits=self.spec.digits
            )
            if not tick:
                continue
            self.funnel.ticks_passed_validation += 1

            buffer = self.tick_engine.get_buffer(self.symbol)
            if not buffer or len(buffer) < 10:
                continue

            # 2. Update & Check Position Exits
            closed_pos = self.position_manager.update_and_check_exits(
                current_bid=bid,
                current_ask=ask,
                now=ts
            )
            for c in closed_pos:
                trade_dict = c.to_dict()
                trade_dict["regime"] = getattr(c, "regime_at_entry", "UNKNOWN")
                trade_dict["slippage_cost"] = getattr(c, "slippage_cost", 0.0)
                trade_dict["spread_cost"] = getattr(c, "spread_cost", 0.0)
                executed_trades.append(trade_dict)
                self.funnel.paper_positions_closed = len(executed_trades)
                self.cooldown_manager.record_trade_result(c.realized_pnl, ts)

            # 3. Process Pending Orders (Simulate Latency Delay)
            for order in list(pending_orders):
                fill_ts = order["fill_target_time"]
                if ts >= fill_ts:
                    if tick.spread_pips > 3.0:
                        pending_orders.remove(order)
                        continue

                    velocity = order["features"].price_velocity
                    slippage = self.base_slippage_pips + abs(velocity) * 0.1
                    pip_unit = self.spec.pip_size

                    entry_price = ask + (slippage * pip_unit) if order["direction"] == "BUY" else bid - (slippage * pip_unit)
                    pos_id = f"SCALP_BT_{tick_idx}"

                    pos = ScalpPosition(
                        position_id=pos_id,
                        symbol=self.symbol,
                        direction=order["direction"],
                        volume=order["volume"],
                        entry_price=round(entry_price, self.spec.digits),
                        current_price=round(entry_price, self.spec.digits),
                        stop_loss=order["stop_loss"],
                        take_profit=order["take_profit"],
                        entry_time=ts,
                        status="OPEN"
                    )
                    pos.regime_at_entry = order["regime"]
                    pos.slippage_cost = round(slippage * pip_unit * self.spec.contract_size * order["volume"], 2)
                    pos.spread_cost = round(tick.spread_pips * pip_unit * self.spec.contract_size * order["volume"], 2)
                    self.position_manager.add_position(pos)
                    self.funnel.paper_trades_executed += 1
                    pending_orders.remove(order)

            # 4. Extract Features
            features = self.feature_engine.extract_features(buffer, spec=self.spec)
            if not features:
                continue

            if features.spread_pips <= 3.0:
                self.funnel.ticks_passed_spread += 1

            # 5. Evaluate Regime & Strategy Weight
            regime_state = self.regime_engine.evaluate_regime(features)
            if regime_state.allow_trading:
                self.funnel.ticks_regime_allowed += 1

            strategy_weight = self.selector.get_strategy_weight(regime_state.regime, "MomentumScalper")

            # 6. Generate Strategy Signal & Fusion Evaluation
            signal = self.scalp_strategy.generate_signal(features, spec=self.spec)
            self.funnel.strategy_signals_evaluated += 1

            if abs(features.normalized_momentum) >= self.min_norm_momentum:
                self.funnel.signals_passed_momentum += 1
            if features.imbalance_edge >= self.min_imbalance_edge:
                self.funnel.signals_passed_imbalance += 1

            fused = self.fusion_engine.evaluate_opportunity(
                signal,
                regime_state,
                strategy_weight=strategy_weight,
                min_opportunity_score=self.min_opportunity_score
            )

            # Record Near-Misses in Diagnostic Mode
            if fused.opportunity_score > 0 and fused.opportunity_score < self.min_opportunity_score:
                self.funnel.near_misses.append({
                    "symbol": self.symbol,
                    "direction": signal.direction,
                    "score": fused.opportunity_score,
                    "required": self.min_opportunity_score
                })

            if fused.approved:
                self.funnel.signals_passed_fusion += 1

                # 7. Check Cooldown & Active Positions Limit
                if not self.cooldown_manager.locked and not self.cooldown_manager.is_in_cooldown(ts):
                    open_count = len([p for p in self.position_manager.positions.values() if p.status == "OPEN"]) + len(pending_orders)
                    if open_count == 0:
                        self.risk_engine.maximum_spread_pips = 3.0
                        sig_dict = signal.to_dict()
                        sig_dict["client_signal_id"] = signal.signal_id
                        sig_dict["entry_price"] = signal.entry_reference
                        sig_dict["stop_loss"] = signal.stop_reference
                        sig_dict["take_profit"] = signal.target_reference

                        risk_dec = self.risk_engine.evaluate_trade_risk(
                            signal=sig_dict,
                            account_info=account_info,
                            symbol_info=symbol_info,
                            current_open_positions_count=open_count,
                            current_spread_pips=tick.spread_pips
                        )



                        if risk_dec.approved:
                            self.funnel.signals_passed_risk += 1
                            pending_orders.append({
                                "signal_id": signal.signal_id,
                                "direction": signal.direction,
                                "volume": risk_dec.calculated_volume,
                                "stop_loss": signal.stop_reference,
                                "take_profit": signal.target_reference,
                                "features": features,
                                "regime": regime_state.regime.value,
                                "fill_target_time": ts + (self.latency_ms / 1000.0)
                            })
                        else:
                            if not hasattr(self.funnel, 'risk_rejection_reasons'):
                                self.funnel.risk_rejection_reasons = {}
                            reason = risk_dec.rejection_reason or "Unknown risk failure"
                            self.funnel.risk_rejection_reasons[reason] = self.funnel.risk_rejection_reasons.get(reason, 0) + 1


        return TickMetricsCalculator.calculate_metrics(
            trades=executed_trades,
            initial_balance=self.initial_balance,
            commission_per_lot=self.commission_per_lot
        )
