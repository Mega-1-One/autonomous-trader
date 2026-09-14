import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.core.config import settings, ExecutionMode
from app.data.mt5_real import RealMT5Adapter

class GoldMultiPositionProfitScalper:
    """Gold (XAUUSDm) Reversal Scalper Engine (Explicit TP + protective SL, profit-target close)."""

    def __init__(
        self,
        symbol: str = "XAUUSDm",
        volume: float = 0.01,
        max_open_positions: int = 5,
        take_profit_pips: float = 15.0,
        min_profit_target_usd: float = 0.15,
        stop_loss_pips: float = 5.0,
        max_loss_usd: float = 1.0,
        max_holding_seconds: float = 120.0
    ):
        self.symbol = symbol
        self.volume = volume
        self.max_open_positions = max_open_positions
        self.take_profit_pips = take_profit_pips
        self.min_profit_target_usd = min_profit_target_usd
        self.stop_loss_pips = stop_loss_pips
        self.max_loss_usd = max_loss_usd
        self.max_holding_seconds = max_holding_seconds
        self.adapter = RealMT5Adapter()
        self.magic_number = 888777
        self.last_price = 0.0

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

        pip_scale = 0.01 if "XAU" in self.symbol or "USTEC" in self.symbol else 0.0001

        print("\n==================================================")
        print(" GOLD REVERSAL & PROFIT-ONLY SCALPER ACTIVE")
        print("==================================================")
        print(f"MT5 Account:            {acc.login} ({acc.server})")
        print(f"Current Balance:        ${acc.balance:.2f} USD")
        print(f"Target Symbol:          {self.symbol} (Gold)")
        print(f"Micro Volume:           {self.volume} lot per trade")
        print(f"Max Concurrent Trades:  {self.max_open_positions} positions")
        print(f"Take Profit Target:     +{self.take_profit_pips} pips (Explicit TP on Broker)")
        print(f"Stop Loss:              -{self.stop_loss_pips} pips (Protective SL on Broker) + ${self.max_loss_usd:.2f} loss cap")
        print(f"Close Triggers:         PROFIT >= +${self.min_profit_target_usd:.2f} | LOSS <= -${self.max_loss_usd:.2f} | HOLD >= {int(self.max_holding_seconds)}s")
        print("==================================================")
        print("Scanning live Gold market and executing scalps...")
        print("Press Ctrl+C in terminal to stop at any time.\n")

        start_time = time.time()
        trades_opened = 0
        trades_closed_in_profit = 0
        trades_closed_stoploss = 0
        trades_closed_maxhold = 0

        try:
            while True:
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break

                now = time.time()
                acc_curr = mt5.account_info()
                balance = acc_curr.balance if acc_curr else acc.balance

                # 1. Fetch active positions managed by this bot
                open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                active = [p for p in (open_positions or []) if p.magic == self.magic_number]

                # 2. CLOSE MONITOR: profit target, loss cap, and max-hold timeout.
                # Phase 1 fix: losers are closed on STOP_LOSS / MAX_HOLD instead of held indefinitely.
                for pos in active:
                    net_profit = pos.profit + pos.swap
                    hold_time = now - pos.time
                    if net_profit >= self.min_profit_target_usd:
                        reason, comment = "PROFIT", "Gold Profit-Only Close"
                    elif net_profit <= -self.max_loss_usd:
                        reason, comment = "STOP_LOSS", "Gold Stop-Loss Close"
                    elif self.max_holding_seconds and self.max_holding_seconds > 0 and hold_time >= self.max_holding_seconds:
                        reason, comment = "MAX_HOLD", "Gold Max-Hold Close"
                    else:
                        continue
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
                        "comment": comment,
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    res_close = mt5.order_send(req_close)
                    if res_close and res_close.retcode == mt5.TRADE_RETCODE_DONE:
                        if reason == "PROFIT":
                            trades_closed_in_profit += 1
                        elif reason == "STOP_LOSS":
                            trades_closed_stoploss += 1
                        else:
                            trades_closed_maxhold += 1
                        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [{reason} CLOSE SUCCESS] Ticket #{pos.ticket} closed at {res_close.price} | Net Profit: ${net_profit:+.2f} USD (held {int(hold_time)}s)")

                # Re-query active positions
                open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                active = [p for p in (open_positions or []) if p.magic == self.magic_number]

                if active:
                    total_floating = sum(p.profit + p.swap for p in active)
                    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Active Trades: {len(active)}/{self.max_open_positions} | Floating PnL: ${total_floating:+.2f} USD | Acc Balance: ${balance:.2f}")

                # 3. OPEN NEW SCALP POSITIONS UP TO MAX CAPACITY
                while len(active) < self.max_open_positions:
                    tick = mt5.symbol_info_tick(self.symbol)
                    if not tick:
                        break
                    curr_mid = (tick.ask + tick.bid) / 2.0

                    # Determine direction based on tick momentum reversal
                    if self.last_price > 0:
                        direction = "BUY" if curr_mid >= self.last_price else "SELL"
                    else:
                        direction = "BUY"

                    self.last_price = curr_mid
                    is_buy = (direction == "BUY")
                    price = tick.ask if is_buy else tick.bid

                    # Explicit Take Profit + protective Stop Loss
                    tp = round(price + (self.take_profit_pips * pip_scale), 3) if is_buy else round(price - (self.take_profit_pips * pip_scale), 3)
                    sl = round(price - (self.stop_loss_pips * pip_scale), 3) if is_buy else round(price + (self.stop_loss_pips * pip_scale), 3)

                    req_open = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": self.symbol,
                        "volume": self.volume,
                        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                        "price": price,
                        "sl": sl,
                        "tp": tp,
                        "deviation": 10,
                        "magic": self.magic_number,
                        "comment": f"Gold ProfitScalp #{trades_opened+1}",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }

                    res_open = mt5.order_send(req_open)
                    if res_open and res_open.retcode == mt5.TRADE_RETCODE_DONE:
                        trades_opened += 1
                        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [SCALP OPENED] Ticket #{res_open.order} ({direction}) at {res_open.price} (SL: {sl}, TP Target: {tp})")
                        open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                        active = [p for p in (open_positions or []) if p.magic == self.magic_number]
                    else:
                        if res_open and res_open.retcode == 10027:
                            print("\n[ACTION REQUIRED] Click the GREEN 'Algo Trading' button in MT5 to allow scalping orders.")
                        break

                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[INFO] Gold Scalper stopped by user.")

        self.adapter.disconnect()
        acc_end = mt5.account_info()
        print(f"\nSession Complete. Trades Opened: {trades_opened} | Closed In Profit: {trades_closed_in_profit} | Stop-Loss: {trades_closed_stoploss} | Max-Hold: {trades_closed_maxhold} | Final Balance: ${acc_end.balance if acc_end else balance:.2f} USD")
        return {"trades_opened": trades_opened, "trades_closed_in_profit": trades_closed_in_profit, "trades_closed_stoploss": trades_closed_stoploss, "trades_closed_maxhold": trades_closed_maxhold}
