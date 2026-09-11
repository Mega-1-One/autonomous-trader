import asyncio
from datetime import datetime, timezone
from app.core.config import settings
from app.core.logging import logger
from app.data.mt5_real import RealMT5Adapter
from app.data.mt5_mock import MockMT5Adapter
from app.services.market_data import MarketDataService
from app.strategy.engine import StrategyEngine
from app.execution.engine import ExecutionEngine

def calculate_spread_in_pips(bid: float, ask: float, digits: int, point_size: float) -> float:
    """Calculates spread in standard pips (accounting for 3-digit Gold and 5-digit Forex broker quotes)."""
    raw_diff = abs(ask - bid)
    if digits == 3: # Gold 3-digit (e.g. 4425.518 -> 0.260 spread is 2.6 pips)
        pips = raw_diff / (point_size * 100.0)
    elif digits == 5: # Forex 5-digit (e.g. 1.08500 -> 0.00010 spread is 1.0 pip)
        pips = raw_diff / (point_size * 10.0)
    else:
        pips = raw_diff / point_size
    return round(pips, 1)

async def run_autonomous_trader(symbol: str = "XAUUSD", poll_interval_seconds: int = 5):
    logger.info("==================================================")
    logger.info("  AUTONOMOUS TRADING ENGINE LAUNCHED (BG RUNNER)  ")
    logger.info("==================================================")
    logger.info(f"Target Instrument: {symbol}")
    logger.info(f"Execution Mode: {settings.EXECUTION_MODE.value}")
    logger.info(f"Safety Live Trading Flag: {settings.ENABLE_LIVE_TRADING}")

    # 1. Connect MT5 Adapter
    real_mt5 = RealMT5Adapter()
    if real_mt5.connect():
        adapter = real_mt5
        logger.info("Connected to Real MetaTrader 5 Terminal (Exness).")
    else:
        logger.warning("Real MT5 connection failed; using Mock MT5 Adapter.")
        adapter = MockMT5Adapter()
        adapter.connect()

    market_service = MarketDataService(adapter=adapter)
    strategy_engine = StrategyEngine()
    execution_engine = ExecutionEngine(adapter=adapter)

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
                spread_pips = calculate_spread_in_pips(bid, ask, digits, point_size)

                # 2. Update active positions
                execution_engine.update_positions({symbol: bid}, point_size=point_size)
                open_positions = [p for p in execution_engine.positions.values() if p.status == "OPEN"]

                logger.info(f"[{now_str}] {symbol} Bid: {bid} | Ask: {ask} | Spread: {spread_pips} pips | Open Positions: {len(open_positions)}")

                # 3. Evaluate setup if no active position open
                if len(open_positions) == 0:
                    signal = strategy_engine.evaluate_setup(
                        symbol=symbol,
                        htf_candles=htf_candles,
                        ltf_candles=ltf_candles,
                        point_size=point_size
                    )

                    if signal.status == "APPROVED":
                        logger.info(f"SETUP APPROVED: {signal.direction} {symbol} @ {signal.entry_price} (SL: {signal.stop_loss}, TP: {signal.take_profit})")
                        exec_result = execution_engine.execute_signal(signal.to_dict(), current_spread_pips=spread_pips)
                        logger.info(f"Execution Result: {exec_result}")
                    else:
                        rej_reason = signal.reasons.get("rejection_reason", "Scanning...")
                        logger.info(f"  [Scan] No trade: {rej_reason}")

        except Exception as e:
            logger.error(f"Error in trading loop: {e}", exc_info=True)

        await asyncio.sleep(poll_interval_seconds)

if __name__ == "__main__":
    asyncio.run(run_autonomous_trader())
