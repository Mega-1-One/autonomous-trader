from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings
from app.scalper.instrument import InstrumentSpecification
from app.strategy.structure import StructureEngine, TrendRegime
from app.strategy.liquidity import LiquidityEngine, LiquiditySide
from app.strategy.displacement import DisplacementEngine
from app.strategy.fvg import FVGEngine, FVGType
from app.strategy.sweeps import SweepEngine
from app.strategy.order_block import OrderBlockEngine
from app.strategy.sessions import SessionFilter

@dataclass
class TradeSignal:
    client_signal_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    timeframe: str
    setup_type: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward: float
    confidence: float
    status: str  # "APPROVED" or "REJECTED"
    reasons: Dict[str, Any]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class StrategyEngine:
    """Fast scalp engine: ICT/SMC as a trigger, tight pip stops, small pip targets."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = settings.strategy_config

        entry_cfg = config.get("entry", {})
        tf_cfg = config.get("timeframes", {})
        stops_cfg = settings.risk_config.get("stops_and_targets", {})

        self.minimum_rr = entry_cfg.get("minimum_rr", 0)
        self.take_profit_pips = entry_cfg.get("take_profit_pips", stops_cfg.get("take_profit_pips", 2.0))
        self.stop_loss_pips = entry_cfg.get("stop_loss_pips", stops_cfg.get("stop_loss_pips", 5.0))
        self.ltf = tf_cfg.get("ltf", "M1")
        self.swing_lookback = config.get("market_structure", {}).get("swing_lookback", 3)
        self.session_filter = SessionFilter(config.get("sessions", {}))
        
        self.struct_engine = StructureEngine(swing_lookback=self.swing_lookback)
        self.liq_engine = LiquidityEngine()
        self.disp_engine = DisplacementEngine()
        self.fvg_engine = FVGEngine()
        self.sweep_engine = SweepEngine()
        self.ob_engine = OrderBlockEngine()

    def _pip_size(self, symbol: str, point_size: float) -> float:
        spec = InstrumentSpecification.get_default_spec(symbol)
        if spec and spec.pip_size > 0:
            return spec.pip_size
        return point_size * 10.0 if point_size > 0 else 0.1

    def _scalp_levels(self, symbol: str, direction: str, entry_price: float, point_size: float) -> tuple[float, float, float]:
        """Tight stop and small profit target in pips from entry."""
        pip = self._pip_size(symbol, point_size)
        digits = 2 if point_size >= 0.01 else 5
        sl_dist = self.stop_loss_pips * pip
        tp_dist = self.take_profit_pips * pip
        if direction == "LONG":
            stop_loss = round(entry_price - sl_dist, digits)
            take_profit = round(entry_price + tp_dist, digits)
        else:
            stop_loss = round(entry_price + sl_dist, digits)
            take_profit = round(entry_price - tp_dist, digits)
        risk_dist = abs(entry_price - stop_loss)
        rr = round(abs(take_profit - entry_price) / risk_dist, 2) if risk_dist > 0 else 0.0
        return stop_loss, take_profit, rr

    def evaluate_setup(
        self,
        symbol: str,
        htf_candles: List[Dict[str, Any]],
        ltf_candles: List[Dict[str, Any]],
        point_size: float = 0.01
    ) -> TradeSignal:
        """Evaluates live market state against the 10-step ICT entry model."""
        timestamp = datetime.now(timezone.utc).isoformat()
        signal_id = f"SIG_{uuid.uuid4().hex[:8].upper()}"
        reasons: Dict[str, Any] = {}

        if not ltf_candles:
            return self._build_rejected_signal(
                signal_id, symbol, self.ltf, 0.0, 0.0, 0.0,
                {"rejection_reason": "No market candles available"}, timestamp
            )

        latest_candle = ltf_candles[-1]

        # 1. Session Filter Check (always-on when sessions.enabled is false)
        in_session, session_name = self.session_filter.is_in_active_session(latest_candle["timestamp"])
        reasons["session_check"] = {"active": in_session, "session": session_name}
        if not in_session:
            return self._build_rejected_signal(
                signal_id, symbol, self.ltf, 0.0, 0.0, 0.0,
                {**reasons, "rejection_reason": "Outside active trading session"}, timestamp
            )

        # 2. HTF Directional Context
        htf_res = self.struct_engine.analyze_structure(htf_candles) if htf_candles else self.struct_engine.analyze_structure(ltf_candles)
        htf_trend = htf_res.trend
        reasons["htf_context"] = {"trend": htf_trend}

        # 3. LTF Structure & Sweeps
        ltf_res = self.struct_engine.analyze_structure(ltf_candles)
        liq_levels = self.liq_engine.get_all_liquidity_levels(ltf_candles, ltf_res.swing_points, point_size)
        sweeps = self.sweep_engine.detect_sweeps(ltf_candles, liq_levels, point_size)
        displacements = self.disp_engine.detect_displacement(ltf_candles)
        fvgs = self.fvg_engine.detect_fvgs(ltf_candles, timeframe=self.ltf, point_size=point_size)
        obs = self.ob_engine.detect_order_blocks(ltf_candles, displacements, ltf_res.events)

        # Evaluate LONG Setup
        recent_bullish_sweep = next((s for s in reversed(sweeps) if s.sweep_type == "BULLISH_SWEEP"), None)
        if htf_trend in [TrendRegime.BULLISH.value, TrendRegime.RANGING.value] and recent_bullish_sweep:
            active_fvg = next((f for f in reversed(fvgs) if f.fvg_type == FVGType.BULLISH.value and f.mitigation_status != "FILLED"), None)
            active_ob = next((ob for ob in reversed(obs) if ob.ob_type == "BULLISH" and not ob.mitigated), None)

            if active_fvg or active_ob:
                entry_price = latest_candle["close"]
                stop_loss, take_profit, rr = self._scalp_levels(symbol, "LONG", entry_price, point_size)
                if self.minimum_rr > 0 and rr < self.minimum_rr:
                    return self._build_rejected_signal(
                        signal_id, symbol, self.ltf, entry_price, stop_loss, take_profit,
                        {**reasons, "rejection_reason": f"Risk/Reward {rr} below minimum {self.minimum_rr}"}, timestamp
                    )
                if abs(entry_price - stop_loss) > 0:
                    reasons["setup_confirmation"] = {
                        "htf_trend": htf_trend,
                        "sweep": recent_bullish_sweep.to_dict(),
                        "fvg": active_fvg.to_dict() if active_fvg else None,
                        "order_block": active_ob.to_dict() if active_ob else None,
                        "take_profit_pips": self.take_profit_pips,
                        "stop_loss_pips": self.stop_loss_pips,
                    }
                    return TradeSignal(
                        client_signal_id=signal_id,
                        symbol=symbol,
                        direction="LONG",
                        timeframe=self.ltf,
                        setup_type="SCALP_BULLISH_SWEEP",
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        risk_reward=rr,
                        confidence=0.85,
                        status="APPROVED",
                        reasons=reasons,
                        timestamp=timestamp
                    )

        # Evaluate SHORT Setup
        recent_bearish_sweep = next((s for s in reversed(sweeps) if s.sweep_type == "BEARISH_SWEEP"), None)
        if htf_trend in [TrendRegime.BEARISH.value, TrendRegime.RANGING.value] and recent_bearish_sweep:
            active_fvg = next((f for f in reversed(fvgs) if f.fvg_type == FVGType.BEARISH.value and f.mitigation_status != "FILLED"), None)
            active_ob = next((ob for ob in reversed(obs) if ob.ob_type == "BEARISH" and not ob.mitigated), None)

            if active_fvg or active_ob:
                entry_price = latest_candle["close"]
                stop_loss, take_profit, rr = self._scalp_levels(symbol, "SHORT", entry_price, point_size)
                if self.minimum_rr > 0 and rr < self.minimum_rr:
                    return self._build_rejected_signal(
                        signal_id, symbol, self.ltf, entry_price, stop_loss, take_profit,
                        {**reasons, "rejection_reason": f"Risk/Reward {rr} below minimum {self.minimum_rr}"}, timestamp
                    )
                if abs(entry_price - stop_loss) > 0:
                    reasons["setup_confirmation"] = {
                        "htf_trend": htf_trend,
                        "sweep": recent_bearish_sweep.to_dict(),
                        "fvg": active_fvg.to_dict() if active_fvg else None,
                        "order_block": active_ob.to_dict() if active_ob else None,
                        "take_profit_pips": self.take_profit_pips,
                        "stop_loss_pips": self.stop_loss_pips,
                    }
                    return TradeSignal(
                        client_signal_id=signal_id,
                        symbol=symbol,
                        direction="SHORT",
                        timeframe=self.ltf,
                        setup_type="SCALP_BEARISH_SWEEP",
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        risk_reward=rr,
                        confidence=0.85,
                        status="APPROVED",
                        reasons=reasons,
                        timestamp=timestamp
                    )

        reasons["rejection_reason"] = "No scalp setup satisfied (missing sweep or valid entry zone)"
        return self._build_rejected_signal(signal_id, symbol, self.ltf, 0.0, 0.0, 0.0, reasons, timestamp)

    def _build_rejected_signal(
        self,
        signal_id: str,
        symbol: str,
        timeframe: str,
        entry: float,
        sl: float,
        tp: float,
        reasons: Dict[str, Any],
        timestamp: str
    ) -> TradeSignal:
        return TradeSignal(
            client_signal_id=signal_id,
            symbol=symbol,
            direction="NEUTRAL",
            timeframe=timeframe,
            setup_type="NO_SETUP",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_reward=0.0,
            confidence=0.0,
            status="REJECTED",
            reasons=reasons,
            timestamp=timestamp
        )
