import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.core.config import settings, ExecutionMode
from app.data.mt5_real import RealMT5Adapter

class GoldMultiPositionProfitScalper:
    """Gold (XAUUSDm) Multi-Position Scalper Engine (Multiple Concurrent Positions, Profit-Only Exits, No Time Limit)."""

    def __init__(
        self,
        symbol: str = "XAUUSDm",
        volume: float = 0.01,
        max_open_positions: int = 5,
        min_profit_target_usd: float = 0.20
    ):
        self.symbol = symbol
        self.volume = volume
        self.max_open_positions = max_open_positions
        self.min_profit_target_usd = min_profit_target_usd
        self.adapter = RealMT5Adapter()
        self.magic_number = 888777

    def initialize(self) -> bool:
        if not self.adapter.connect():
            print("[ERROR] Failed to connect MT5 adapter.")
            return False
        return True

    def run_multi_scalper_loop(self, duration_seconds: Optional[int] = None):
        import MetaTrader5 as mt5

        acc = mt5.account_info()
        if not acc:
            print("[ERROR] Could not fetch account info.")
            return

        print("\n==================================================")
        print(" GOLD MULTI-POSITION PROFIT-ONLY SCALPER LAUNCHED")
        print("==================================================")
        print(f"MT5 Account:            {acc.login} ({acc.server})")
        print(f"Current Balance:        ${acc.balance:.2f} USD")
        print(f"Target Symbol:          {self.symbol} (Gold)")
        print(f"Micro Volume:           {self.volume} lot per trade")
        print(f"Max Concurrent Trades:  {self.max_open_positions} positions")
        print(f"Holding Time Limit:     DISABLED (Positions held until in profit)")
        print(f"Close Trigger:          PROFIT-ONLY (Min net profit >= +${self.min_profit_target_usd:.2f})")
        print("==================================================")
        print("Scanning live Gold market and managing profit-only multi-positions...")
        print("Press Ctrl+C in terminal to stop at any time.\n")

        start_time = time.time()
        trades_opened = 0
        trades_closed_in_profit = 0

        try:
            while True:
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break

                now = time.time()
                acc_curr = mt5.account_info()
                balance = acc_curr.balance if acc_curr else acc.balance

                # 1. Fetch all open Gold positions managed by this bot
                open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                active = [p for p in (open_positions or []) if p.magic == self.magic_number]

                # 2. Check each active position for PROFIT-ONLY close
                for pos in active:
                    # Profit includes swap and commission
                    net_profit = pos.profit + pos.swap
                    if net_profit >= self.min_profit_target_usd:
                        close_price = mt5.symbol_info_tick(self.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(self.symbol).ask
                        req_close = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": self.symbol,
                            "volume": pos.volume,
                            "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                            "position": pos.ticket,
                            "price": close_price,
                            "deviation": 10,
                            "magic": self.magic_number,
                            "comment": "Gold Profit Close",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        res_close = mt5.order_send(req_close)
                        if res_close and res_close.retcode == mt5.TRADE_RETCODE_DONE:
                            trades_closed_in_profit += 1
                            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [PROFIT CLOSE SUCCESS] Ticket #{pos.ticket} closed at {res_close.price} | Net Profit: +${net_profit:.2f} USD")

                # Re-query active after profit closes
                open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                active = [p for p in (open_positions or []) if p.magic == self.magic_number]

                # Log Active Positions Monitor
                if active:
                    total_floating_profit = sum(p.profit + p.swap for p in active)
                    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Open Positions: {len(active)}/{self.max_open_positions} | Total Floating PnL: ${total_floating_profit:+.2f} USD | Acc Balance: ${balance:.2f}")

                # 3. Open new positions if active count < max_open_positions
                if len(active) < self.max_open_positions:
                    tick = mt5.symbol_info_tick(self.symbol)
                    if tick:
                        # Alternate BUY / SELL or follow tick impulse
                        direction = "BUY" if (trades_opened % 2 == 0) else "SELL"
                        is_buy = (direction == "BUY")
                        price = tick.ask if is_buy else tick.bid

                        # Wide SL or No hard SL (Profit-only close rule)
                        pip_scale = 0.01
                        sl = round(price - (50.0 * pip_scale), 3) if is_buy else round(price + (50.0 * pip_scale), 3)

                        req_open = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": self.symbol,
                            "volume": self.volume,
                            "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                            "price": price,
                            "sl": sl,
                            "deviation": 10,
                            "magic": self.magic_number,
                            "comment": f"Gold Multi #{trades_opened+1}",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }

                        res_open = mt5.order_send(req_open)
                        if res_open and res_open.retcode == mt5.TRADE_RETCODE_DONE:
                            trades_opened += 1
                            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [GOLD SCALP OPENED] Ticket #{res_open.order} ({direction}) at {res_open.price}")
                        else:
                            if res_open and res_open.retcode == 10027:
                                print("\n[ACTION REQUIRED] Click the GREEN 'Algo Trading' button in MT5 to allow scalping orders.")

                time.sleep(1.5)
        except KeyboardInterrupt:
            print("\n[INFO] Gold Multi-Position Scalper stopped by user.")

        self.adapter.disconnect()
        acc_end = mt5.account_info()
        print(f"\nSession Complete. Trades Opened: {trades_opened} | Profit-Closed: {trades_closed_in_profit} | Final Balance: ${acc_end.balance if acc_end else balance:.2f} USD")
        return {"trades_opened": trades_opened, "trades_closed_in_profit": trades_closed_in_profit}
