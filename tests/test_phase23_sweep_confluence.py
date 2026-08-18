import pytest
from app.context.bias_engine import TopDownBiasResult
from app.context.price_location import PriceLocationResult
from app.research.sweep_confluence import SweepConfluenceEngine, SweepConfluenceConfig
from app.scalper.features import ScalperFeatures
from app.scalper.instrument import InstrumentSpecification

def test_sweep_confluence_filter_ladder():
    engine = SweepConfluenceEngine()
    spec = InstrumentSpecification.get_default_spec("XAUUSD")
    bias_res = TopDownBiasResult("STRONG_BULLISH", 1.0, {"4h": "BUY"}, ["Bullish"])
    loc_res = PriceLocationResult("DISCOUNT", 0.20, 2410.0, 2390.0, 2400.0)

    feats = ScalperFeatures(
        symbol="XAUUSD", timestamp=100.0, bid=2392.0, ask=2392.2, spread_pips=0.2,
        tick_velocity_5s=5.0, tick_velocity_10s=5.0, price_velocity=0.1, price_acceleration=0.01,
        momentum_5s=0.5, normalized_momentum=2.5, bullish_tick_ratio=0.60, bearish_tick_ratio=0.40,
        imbalance_edge=0.10, volatility_50t=0.2, dist_micro_high=1.0, dist_micro_low=1.0,
        is_micro_breakout_high=False, is_micro_breakout_low=False
    )

    # Experiment A (Sweep Alone)
    cfg_a = SweepConfluenceConfig()
    assert engine.evaluate_sweep_confluence(bias_res, loc_res, feats, spec, cfg_a) is True

    # Experiment F (Full Confluence)
    cfg_f = SweepConfluenceConfig(
        require_htf_bias=True, require_prem_disc=True, require_structure_shift=True,
        require_displacement=True, require_ltf_confirm=True
    )
    assert engine.evaluate_sweep_confluence(bias_res, loc_res, feats, spec, cfg_f) is True

def test_safety_locks_enforced():
    from app.core.config import settings, ExecutionMode
    assert settings.EXECUTION_MODE == ExecutionMode.PAPER
    assert settings.ENABLE_LIVE_TRADING is False
    assert settings.LIVE_TRADING_CONFIRMATION is False
