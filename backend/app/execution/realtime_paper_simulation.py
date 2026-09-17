import time
import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.data.mt5_real import RealMT5Adapter

logger = logging.getLogger("autotrader.paper")

class RealtimePaperSimulationEngine:
    """Real-Time MT5 Account Stream & Demo Monitor Engine."""

    SYMBOLS = [
        ("XAUUSD", "XAUUSDm"),
        ("EURUSD", "EURUSDm"),
        ("GBPUSD", "GBPUSDm"),
        ("NAS100", "USTECm")
    ]

    def __init__(self):
        self.adapter = RealMT5Adapter()
        self.account_login = None
        self.account_server = None
        self.account_balance = 0.0
        self.account_equity = 0.0
        self.account_leverage = 1
        self.active_positions = []

    def initialize(self) -> bool:
        if not self.adapter.connect():
            print("[ERROR] Failed to connect MT5 adapter.")
            return False

        import MetaTrader5 as mt5
        acc = mt5.account_info()
        if acc:
            self.account_login = acc.login
            self.account_server = acc.server
            self.account_balance = acc.balance
            self.account_equity = acc.equity
            self.account_leverage = acc.leverage

        print("\n==================================================")
        print(" METATRADER 5 CONNECTED ACCOUNT INFO")
        print("==================================================")
        print(f"Account Login:    {self.account_login}")
        print(f"Server:           {self.account_server}")
        print(f"Current Balance:  ${self.account_balance:.2f} USD")
        print(f"Current Equity:   ${self.account_equity:.2f} USD")
        print(f"Leverage:         1:{self.account_leverage}")
        print(f"Safety Mode:      EXECUTION_MODE={settings.EXECUTION_MODE}, ENABLE_LIVE_TRADING={settings.ENABLE_LIVE_TRADING}")
        print("==================================================\n")
        return True

    def run_continuous_stream(self, duration_seconds: Optional[int] = None):
        """Runs a continuous real-time streaming loop until interrupted."""
        import MetaTrader5 as mt5

        start_time = time.time()
        tick_count = 0

        print(f"Starting MT5 Account ({self.account_login}) Real-Time Stream Monitor...")
        print("Press Ctrl+C in terminal to stop streaming at any time.\n")

        try:
            while True:
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break

                acc = mt5.account_info()
                if acc:
                    self.account_balance = acc.balance
                    self.account_equity = acc.equity

                for canonical, sym in self.SYMBOLS:
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        tick_count += 1
                        spread_pips = (tick.ask - tick.bid)
                        if canonical in ["EURUSD", "GBPUSD"]:
                            spread_pips /= 0.0001
                        elif canonical in ["XAUUSD", "NAS100"]:
                            spread_pips /= 0.01

                        ts_str = datetime.fromtimestamp(tick.time, tz=timezone.utc).strftime('%H:%M:%S UTC')
                        print(f"[{ts_str}] {canonical:8s} | Bid: {tick.bid:10.5f} | Ask: {tick.ask:10.5f} | Spread: {spread_pips:5.2f} pips | Acc Balance: ${self.account_balance:.2f}")

                time.sleep(2.0)
        except KeyboardInterrupt:
            print("\n[INFO] Streaming stopped by user.")

        summary = {
            "account_login": self.account_login,
            "account_server": self.account_server,
            "final_balance": self.account_balance,
            "final_equity": self.account_equity,
            "ticks_processed": tick_count,
            "status": "STREAM_FINISHED"
        }
        return summary

    def shutdown(self):
        self.adapter.disconnect()
        print("[INFO] MT5 Connection shutdown complete.")
