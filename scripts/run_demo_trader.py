import sys
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logging.getLogger("autotrader").setLevel(logging.ERROR)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings, ExecutionMode
from app.data.mt5_real import RealMT5Adapter

def run_demo_trader():
    print("\n==================================================")
    print(" METATRADER 5 DEMO ORDER EXECUTION RUNNER")
    print("==================================================")

    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MetaTrader 5 terminal.")
        return

    import MetaTrader5 as mt5

    acc = mt5.account_info()
    if not acc:
        print("[ERROR] Could not fetch MT5 account info.")
        adapter.disconnect()
        return

    print(f"Connected MT5 Account: {acc.login} ({acc.server})")
    print(f"Current Balance:        ${acc.balance:.2f} USD")
    print(f"Current Equity:         ${acc.equity:.2f} USD")
    print(f"Current Settings:       EXECUTION_MODE={settings.EXECUTION_MODE}, ENABLE_LIVE_TRADING={settings.ENABLE_LIVE_TRADING}")

    if not settings.ENABLE_LIVE_TRADING or settings.EXECUTION_MODE != ExecutionMode.LIVE:
        print("\n[SAFETY LOCK ACTIVE]")
        print("To allow demo orders to be placed on your MT5 Demo Account (476536600), ENABLE_LIVE_TRADING must be set to True.")
        print("Run the command with '--enable-demo' to execute a test 0.01 lot Demo order on your MT5 Demo account.")

        if len(sys.argv) > 1 and sys.argv[1] == "--enable-demo":
            print("\nExecuting Test 0.01 Lot Demo Order on EURUSDm...")
            symbol = "EURUSDm"
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                print(f"[ERROR] Could not fetch tick for {symbol}")
                adapter.disconnect()
                return

            lot = 0.01  # Minimum lot for $27.65 balance
            ask = tick.ask
            sl = round(ask - 0.0030, 5)  # 30 pips SL
            tp = round(ask + 0.0060, 5)  # 60 pips TP

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot,
                "type": mt5.ORDER_TYPE_BUY,
                "price": ask,
                "sl": sl,
                "tp": tp,
                "deviation": 20,
                "magic": 100001,
                "comment": "AutoTrader Demo Test Order",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            print("\n[BROKER ORDER RESULT]")
            print(f"  Return Code: {result.retcode}")
            print(f"  Order Ticket: {result.order}")
            print(f"  Price Flipped: {result.price}")
            print(f"  Comment: {result.comment}")

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"\n[SUCCESS] Demo Order successfully placed on Exness MT5 Demo Account #{acc.login}!")
            else:
                print(f"\n[NOTICE] Broker response: {result.comment}")

    adapter.disconnect()
    print("\n[INFO] Demo Execution runner complete.")

if __name__ == "__main__":
    run_demo_trader()
