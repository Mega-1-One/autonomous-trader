from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

from app.context.timeframe_engine import Candle
from app.scalper.instrument import InstrumentSpecification

@dataclass
class SwingSetupResult:
    setup_type: str                   # "TREND_PULLBACK", "BREAKOUT_RETEST", "LIQUIDITY_SWEEP_REVERSAL", "BOS_RETRACEMENT", "CHOCH_REVERSAL", "NO_SETUP"
    direction: str                    # "BUY", "SELL", "NONE"
    approved: bool
    regime_4h: str
    bias_1h: str
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_pips: float
    target_pips: float
    rr_ratio: float
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SwingEngine:
    """Multi-Timeframe Intraday & Swing Intelligence Engine (4H Regime -> 1H Bias -> 15M Setup -> 1M Entry)."""

    def evaluate_swing_setup(
        self,
        candles_4h: List[Candle],
        candles_1h: List[Candle],
        candles_15m: List[Candle],
        spec: InstrumentSpecification,
        current_price: float,
        target_setup_filter: Optional[str] = None,
        rr_target_ratio: float = 2.0
    ) -> SwingSetupResult:
        reasons = []

        if len(candles_4h) < 10 or len(candles_1h) < 10 or len(candles_15m) < 10:
            return SwingSetupResult(
                setup_type="NO_SETUP", direction="NONE", approved=False,
                regime_4h="NEUTRAL", bias_1h="NEUTRAL",
                entry_price=current_price, stop_loss=current_price, take_profit=current_price,
                stop_pips=0.0, target_pips=0.0, rr_ratio=0.0,
                reasons=["Insufficient multi-timeframe candle history"]
            )

        # 1. 4H Market Regime
        c4_closes = [c.close for c in candles_4h[-10:]]
        sma4h = sum(c4_closes) / len(c4_closes)
        regime_4h = "TRENDING_UP" if current_price > sma4h else "TRENDING_DOWN"

        # 2. 1H Directional Bias
        c1_closes = [c.close for c in candles_1h[-10:]]
        sma1h = sum(c1_closes) / len(c1_closes)
        bias_1h = "BULLISH" if current_price > sma1h else "BEARISH"

        is_buy = (regime_4h == "TRENDING_UP" and bias_1h == "BULLISH")
        is_sell = (regime_4h == "TRENDING_DOWN" and bias_1h == "BEARISH")

        if not (is_buy or is_sell):
            return SwingSetupResult(
                setup_type="NO_SETUP", direction="NONE", approved=False,
                regime_4h=regime_4h, bias_1h=bias_1h,
                entry_price=current_price, stop_loss=current_price, take_profit=current_price,
                stop_pips=0.0, target_pips=0.0, rr_ratio=0.0,
                reasons=["Regime/Bias conflict: 4H and 1H not aligned"]
            )

        direction = "BUY" if is_buy else "SELL"

        # 3. 15M Setup Detection
        c15_highs = [c.high for c in candles_15m[-15:]]
        c15_lows = [c.low for c in candles_15m[-15:]]
        c15_closes = [c.close for c in candles_15m[-15:]]

        pip_unit = spec.pip_size
        atr_15m = max(1.0, (max(c15_highs) - min(c15_lows)) / (15.0 * pip_unit))

        # Classify specific swing setup
        if is_buy and c15_closes[-1] < c15_closes[-3]:
            st_type = "TREND_PULLBACK"
        elif is_sell and c15_closes[-1] > c15_closes[-3]:
            st_type = "TREND_PULLBACK"
        elif is_buy and current_price > max(c15_highs[:-2]):
            st_type = "BREAKOUT_RETEST"
        elif is_sell and current_price < min(c15_lows[:-2]):
            st_type = "BREAKOUT_RETEST"
        else:
            st_type = "BOS_RETRACEMENT"

        if target_setup_filter and st_type != target_setup_filter:
            return SwingSetupResult(
                setup_type="NO_SETUP", direction="NONE", approved=False,
                regime_4h=regime_4h, bias_1h=bias_1h,
                entry_price=current_price, stop_loss=current_price, take_profit=current_price,
                stop_pips=0.0, target_pips=0.0, rr_ratio=0.0,
                reasons=[f"Setup filter mismatch: {st_type} != {target_setup_filter}"]
            )

        # 4. Swing SL / TP Sizing
        stop_pips = round(atr_15m * 1.5, 1)
        target_pips = round(stop_pips * rr_target_ratio, 1)

        if direction == "BUY":
            sl = round(current_price - (stop_pips * pip_unit), spec.digits)
            tp = round(current_price + (target_pips * pip_unit), spec.digits)
        else:
            sl = round(current_price + (stop_pips * pip_unit), spec.digits)
            tp = round(current_price - (target_pips * pip_unit), spec.digits)

        reasons.append(f"Swing Setup Approved: {st_type} ({direction}) | 4H: {regime_4h} | 1H: {bias_1h} | Target: {target_pips} pips")

        return SwingSetupResult(
            setup_type=st_type,
            direction=direction,
            approved=True,
            regime_4h=regime_4h,
            bias_1h=bias_1h,
            entry_price=current_price,
            stop_loss=sl,
            take_profit=tp,
            stop_pips=stop_pips,
            target_pips=target_pips,
            rr_ratio=rr_target_ratio,
            reasons=reasons
        )
