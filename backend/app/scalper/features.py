from dataclasses import dataclass
from typing import Optional
import math
import time

from app.scalper.tick_engine import TickBuffer
from app.scalper.instrument import InstrumentSpecification

@dataclass
class ScalperFeatures:
    symbol: str
    timestamp: float
    bid: float
    ask: float
    spread_pips: float
    tick_velocity_5s: float        # Ticks per second over last 5s
    tick_velocity_10s: float       # Ticks per second over last 10s
    price_velocity: float          # Price change per second over last 5s
    price_acceleration: float      # Acceleration of price velocity over last 5s
    momentum_5s: float             # Price change over last 5s in price units
    normalized_momentum: float     # Dimensionless momentum: momentum_5s / volatility_50t
    bullish_tick_ratio: float      # Fraction of bullish ticks in last 50 ticks
    bearish_tick_ratio: float      # Fraction of bearish ticks in last 50 ticks
    imbalance_edge: float          # Deviation from neutral balance: abs(bullish_ratio - 0.50)
    volatility_50t: float          # Price std dev over last 50 ticks
    dist_micro_high: float         # Distance to micro high in pips
    dist_micro_low: float          # Distance to micro low in pips
    is_micro_breakout_high: bool
    is_micro_breakout_low: bool

class FeatureEngine:
    """Deterministic High-Frequency Feature Engine calculating normalized microstructure metrics."""

    def extract_features(
        self,
        buffer: TickBuffer,
        spec: Optional[InstrumentSpecification] = None,
        point_size: float = 0.001,
        digits: int = 3
    ) -> Optional[ScalperFeatures]:
        ticks = buffer.get_last_n(100)
        n = len(ticks)
        if n < 10:
            return None

        latest_tick = ticks[-1]
        now = latest_tick.timestamp
        symbol = latest_tick.symbol

        if spec is None:
            spec = InstrumentSpecification.get_default_spec(symbol)

        # 1. Spread Calculation
        spread_pips = latest_tick.spread_pips

        # 2. Fast Window Counting (ticks are ordered chronologically)
        c_5s = 0
        c_10s = 0
        p_5s_first = None

        for t in reversed(ticks):
            age = now - t.timestamp
            if age <= 5.0:
                c_5s += 1
                p_5s_first = t.last
            if age <= 10.0:
                c_10s += 1
            else:
                break

        tick_velocity_5s = round(c_5s / 5.0, 2)
        tick_velocity_10s = round(c_10s / 10.0, 2)

        # 3. Price Velocity & Acceleration over 5s window
        p_end = latest_tick.last
        if p_5s_first is not None and c_5s >= 2:
            momentum_5s = round(p_end - p_5s_first, spec.digits)
            price_velocity = round(momentum_5s / 5.0, 4)
            price_acceleration = round(price_velocity / 2.5, 4)
        else:
            momentum_5s = 0.0
            price_velocity = 0.0
            price_acceleration = 0.0

        # 4. Tick Direction Imbalance & Volatility over last 50 ticks
        start_idx = max(0, n - 50)
        ticks_50 = ticks[start_idx:]
        n_50 = len(ticks_50)

        bullish_count = 0
        bearish_count = 0
        price_sum = 0.0

        prev_price = ticks_50[0].last
        micro_high = prev_price
        micro_low = prev_price

        for t in ticks_50:
            price = t.last
            price_sum += price
            if price > micro_high:
                micro_high = price
            if price < micro_low:
                micro_low = price

            diff = price - prev_price
            if diff > 0:
                bullish_count += 1
            elif diff < 0:
                bearish_count += 1
            prev_price = price

        total = max(1, bullish_count + bearish_count)
        bullish_tick_ratio = round(bullish_count / total, 2)
        bearish_tick_ratio = round(bearish_count / total, 2)
        imbalance_edge = round(abs(bullish_tick_ratio - 0.50), 2)

        # Volatility (Std dev)
        mean_p = price_sum / n_50
        var_p = sum((t.last - mean_p) ** 2 for t in ticks_50) / n_50
        volatility_50t = round(math.sqrt(var_p), spec.digits)

        # Normalized Momentum: ratio of 5s momentum to 50-tick volatility
        denom = max(volatility_50t, spec.tick_size)
        normalized_momentum = round(momentum_5s / denom, 2)

        # 5. Micro High / Low & Breakout Detection
        dist_micro_high = round((micro_high - p_end) / spec.pip_size, 1)
        dist_micro_low = round((p_end - micro_low) / spec.pip_size, 1)

        is_micro_breakout_high = (p_end >= micro_high) and (momentum_5s > 0)
        is_micro_breakout_low = (p_end <= micro_low) and (momentum_5s < 0)

        return ScalperFeatures(
            symbol=symbol,
            timestamp=now,
            bid=latest_tick.bid,
            ask=latest_tick.ask,
            spread_pips=spread_pips,
            tick_velocity_5s=tick_velocity_5s,
            tick_velocity_10s=tick_velocity_10s,
            price_velocity=price_velocity,
            price_acceleration=price_acceleration,
            momentum_5s=momentum_5s,
            normalized_momentum=normalized_momentum,
            bullish_tick_ratio=bullish_tick_ratio,
            bearish_tick_ratio=bearish_tick_ratio,
            imbalance_edge=imbalance_edge,
            volatility_50t=volatility_50t,
            dist_micro_high=dist_micro_high,
            dist_micro_low=dist_micro_low,
            is_micro_breakout_high=is_micro_breakout_high,
            is_micro_breakout_low=is_micro_breakout_low
        )
