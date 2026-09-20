import asyncio
from datetime import datetime, timezone
from app.core.config import settings
from app.core.logging import logger
from app.core.pricing import spread_in_pips
from app.data.adapter_factory import build_adapter
from app.data.mt5_real import RealMT5Adapter
from app.risk.engine import RiskEngine
from app.services.market_data import MarketDataService
from app.strategy import ict_adapter  # noqa: F401 (registers the ict_scalp provider)
from app.strategy.provider import MarketInputs, create_provider, evaluate_strategy
from app.execution.engine import ExecutionEngine

def calculate_spread_in_pips(bid: float, ask: float, digits: int, point_size: float, symbol: str = "") -> float:
    """Calculates spread in standard pips.

    Migrated onto the canonical pip-size semantics (ADR-4): when a symbol is
    supplied and resolves to a specification, the spec's pip_size is used
    (gold 0.1, 5-digit FX 0.0001). Without a symbol the legacy digits-derived
    rules are retained for compatibility.
    """
    return spread_in_pips(bid, ask, symbol=symbol, digits=digits, point_size=point_size)

async def run_autonomous_trader(symbol: str = "XAUUSD", poll_interval_seconds: int = 5):
    logger.info("==================================================")
    logger.info("  AUTONOMOUS TRADING ENGINE LAUNCHED (BG RUNNER)  ")
    logger.info("==================================================")
    logger.info(f"Target Instrument: {symbol}")
    logger.info(f"Execution Mode: {settings.EXECUTION_MODE.value}")
    logger.info(f"Safety Live Trading Flag: {settings.ENABLE_LIVE_TRADING}")

    # 1. Select broker adapter honoring EXECUTION_MODE (I-3/H-2 parity).
    #    PAPER/BACKTEST use the mock adapter regardless of host; DEMO/LIVE try
    #    the real terminal first and fall back to mock (which the gate then
    #    refuses for entries in LIVE, so no simulated live fills).
    adapter = build_adapter()
    if isinstance(adapter, RealMT5Adapter):
        logger.info("Connected to Real MetaTrader 5 Terminal (Exness).")
    else:
        logger.warning("Using Mock MT5 Adapter (PAPER/BACKTEST mode or terminal unavailable).")

    market_service = MarketDataService(adapter=adapter)
    # E2: strategy behind the provider seam (default ict_scalp, same config
    # source as the previous direct StrategyEngine() construction).
    strategy_engine = create_provider(
        settings.strategy_config.get("name", "ict_scalp"),
        settings.strategy_config,
    )
    # One RiskEngine per process (ADR-2): explicitly injected into the engine.
    risk_engine = RiskEngine()
    execution_engine = ExecutionEngine(adapter=adapter, risk_engine=risk_engine)

    info = market_service.get_symbol_info(symbol) or {"digits": 3, "point_size": 0.001}
    digits = info.get("digits", 3)
    point_size = info.get("point_size", 0.001)

    while True:
        try:
            now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
            
            # Fetch candles
            htf_candles = market_service.fetch_candles(symbol, "H1", count=100)
            ltf_candles = market_service.fetch_candles(symbol, "M5", count=200)

            if ltf_candles:
                latest = ltf_candles[-1]
                bid = info.get("bid", latest["close"])
                ask = info.get("ask", latest["close"])
                spread_pips = calculate_spread_in_pips(bid, ask, digits, point_size, symbol=symbol)

                # 2. Update active positions
                execution_engine.update_positions({symbol: bid}, point_size=point_size)
                open_positions = [p for p in execution_engine.positions.values() if p.status == "OPEN"]

                logger.info(f"[{now_str}] {symbol} Bid: {bid} | Ask: {ask} | Spread: {spread_pips} pips | Open Positions: {len(open_positions)}")

                # 3. Evaluate setup if no active position open
                if len(open_positions) == 0:
                    signal = evaluate_strategy(
                        strategy_engine,
                        MarketInputs(
                            symbol=symbol,
                            candles={"HTF": htf_candles, "LTF": ltf_candles},
                            point_size=point_size,
                        ),
                    )

                    if signal["status"] == "APPROVED":
                        logger.info(f"SETUP APPROVED: {signal['direction']} {symbol} @ {signal['entry_price']} (SL: {signal['stop_loss']}, TP: {signal['take_profit']})")
                        exec_result = execution_engine.execute_signal(signal, current_spread_pips=spread_pips)
                        logger.info(f"Execution Result: {exec_result}")
                    else:
                        rej_reason = signal["reasons"].get("rejection_reason", "Scanning...")
                        logger.info(f"  [Scan] No trade: {rej_reason}")

        except Exception as e:
            logger.error(f"Error in trading loop: {e}", exc_info=True)

        await asyncio.sleep(poll_interval_seconds)

if __name__ == "__main__":
    asyncio.run(run_autonomous_trader())
