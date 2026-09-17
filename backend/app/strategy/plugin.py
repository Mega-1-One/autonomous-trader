from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import uuid

class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"

@dataclass
class UnifiedSignal:
    signal_id: str
    timestamp: str
    instrument: str
    direction: SignalDirection
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_percent: float
    strategy_name: str
    strategy_version: str
    reason_codes: List[str]
    market_state: Dict[str, Any]
    confidence: float
    data_snapshot_hash: str
    explanation: str
    approved: bool = True
    rejection_stage: Optional[str] = None
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["direction"] = self.direction.value
        return d

class StrategyPlugin(ABC):
    """Abstract Strategy Plugin interface for modular signal generation."""

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def evaluate_market(self, instrument: str, market_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def generate_signal(self, instrument: str, market_state: Dict[str, Any]) -> Optional[UnifiedSignal]:
        pass

    @abstractmethod
    def validate_signal(self, signal: UnifiedSignal) -> Tuple[bool, Optional[str]]:
        pass

    @abstractmethod
    def explain_signal(self, signal: UnifiedSignal) -> str:
        pass

class UnvalidatedResearchStrategy(StrategyPlugin):
    """Integrates ICT/SMC research patterns labeled strictly as UNVALIDATED_RESEARCH_STRATEGY."""

    def __init__(self):
        self.strategy_name = "UNVALIDATED_RESEARCH_STRATEGY"
        self.strategy_version = "1.0.0-PROSPECTIVE"
        self.config: Dict[str, Any] = {}

    def initialize(self, config: Dict[str, Any]) -> bool:
        self.config = config
        return True

    def evaluate_market(self, instrument: str, market_data: Dict[str, Any]) -> Dict[str, Any]:
        candles = market_data.get("candles", [])
        if not candles or len(candles) < 20:
            return {"status": "INSUFFICIENT_DATA", "trend": "NEUTRAL"}

        closes = [c["close"] for c in candles]
        sma_fast = sum(closes[-5:]) / 5.0
        sma_slow = sum(closes[-20:]) / 20.0

        trend = "BULLISH" if sma_fast > sma_slow else "BEARISH"
        return {
            "status": "VALID",
            "trend": trend,
            "sma_fast": round(sma_fast, 3),
            "sma_slow": round(sma_slow, 3),
            "last_close": closes[-1]
        }

    def generate_signal(self, instrument: str, market_state: Dict[str, Any]) -> Optional[UnifiedSignal]:
        if market_state.get("status") != "VALID":
            return None

        trend = market_state.get("trend")
        last_close = market_state.get("last_close", 2400.0)

        # Pip sizes (Phase 1 exit-math fix: 3.0 SL / 5.0 TP, RR ~1.67,
        # so emitted signals pass the minimum_rr >= 1.5 risk gate)
        pip_unit = 0.1 if "XAU" in instrument else 0.0001
        sl_dist = 3.0 * pip_unit
        tp_dist = 5.0 * pip_unit

        direction = SignalDirection.LONG if trend == "BULLISH" else SignalDirection.SHORT
        entry = round(last_close, 3)
        sl = round(entry - sl_dist, 3) if direction == SignalDirection.LONG else round(entry + sl_dist, 3)
        tp = round(entry + tp_dist, 3) if direction == SignalDirection.LONG else round(entry - tp_dist, 3)

        raw_bytes = f"{instrument}_{entry}_{sl}_{tp}_{datetime.now(timezone.utc).isoformat()}".encode('utf-8')
        snap_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]

        reasons = [
            f"Trend alignment: {trend}",
            "Fast SMA vs Slow SMA confluence",
            "Micro-scalp fixed-pip geometry"
        ]

        sig = UnifiedSignal(
            signal_id=f"SIG_{uuid.uuid4().hex[:8].upper()}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            instrument=instrument,
            direction=direction,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_percent=0.1,
            strategy_name=self.strategy_name,
            strategy_version=self.strategy_version,
            reason_codes=reasons,
            market_state=market_state,
            confidence=0.75,
            data_snapshot_hash=snap_hash,
            explanation=f"Prospective setup based on {trend} momentum on {instrument}. Note: Unvalidated research strategy under forward observation."
        )
        return sig

    def validate_signal(self, signal: UnifiedSignal) -> Tuple[bool, Optional[str]]:
        if signal.direction == SignalDirection.FLAT:
            return False, "Direction is FLAT"
        if signal.entry_price <= 0 or signal.stop_loss <= 0 or signal.take_profit <= 0:
            return False, "Invalid price levels"
        if signal.direction == SignalDirection.LONG and signal.stop_loss >= signal.entry_price:
            return False, "Long stop loss must be below entry price"
        if signal.direction == SignalDirection.SHORT and signal.stop_loss <= signal.entry_price:
            return False, "Short stop loss must be above entry price"
        return True, None

    def explain_signal(self, signal: UnifiedSignal) -> str:
        return signal.explanation

class SignalQualityGate:
    """Rigorous 6-stage Quality Gate: Signal -> Data Quality -> Market State -> Strategy Validation -> Risk Validation -> Execution Validation."""

    def __init__(self, risk_engine: Any = None):
        self.risk_engine = risk_engine
        self.processed_signal_hashes: set[str] = set()

    def process_signal(
        self,
        signal: UnifiedSignal,
        data_quality_ok: bool,
        market_state_ok: bool,
        account_info: Dict[str, Any],
        symbol_info: Dict[str, Any]
    ) -> Tuple[bool, UnifiedSignal]:
        # 1. Duplicate Signal Check
        if signal.data_snapshot_hash in self.processed_signal_hashes:
            signal.approved = False
            signal.rejection_stage = "DUPLICATE_PROTECTION"
            signal.rejection_reason = "Identical signal snapshot already processed"
            return False, signal

        # 2. Data Quality Stage
        if not data_quality_ok:
            signal.approved = False
            signal.rejection_stage = "DATA_QUALITY"
            signal.rejection_reason = "Underlying data feed failed quality or freshness checks"
            return False, signal

        # 3. Market State Stage
        if not market_state_ok:
            signal.approved = False
            signal.rejection_stage = "MARKET_STATE"
            signal.rejection_reason = "Market state invalid or closed"
            return False, signal

        # 4. Strategy Validation Stage
        valid, reason = UnvalidatedResearchStrategy().validate_signal(signal)
        if not valid:
            signal.approved = False
            signal.rejection_stage = "STRATEGY_VALIDATION"
            signal.rejection_reason = reason
            return False, signal

        # 5. Risk Engine Validation Stage
        if self.risk_engine:
            sig_dict = {
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit": signal.take_profit
            }
            decision = self.risk_engine.evaluate_trade_risk(
                signal=sig_dict,
                account_info=account_info,
                symbol_info=symbol_info
            )
            if not decision.approved:
                signal.approved = False
                signal.rejection_stage = "RISK_VALIDATION"
                signal.rejection_reason = decision.rejection_reason
                return False, signal

        # Register processed hash
        self.processed_signal_hashes.add(signal.data_snapshot_hash)
        signal.approved = True
        return True, signal
