import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import numpy as np

from app.core.config import settings, ExecutionMode
from app.data.mt5_real import RealMT5Adapter

class AutonomousScalperDaemon:
    """Fully Autonomous High-Speed Micro-Scalper & Risk Manager for MT5 Demo Account."""

    def __init__(
        self,
        symbol: str = "EURUSDm",
        max_holding_seconds: float = 45.0,
        risk_percent: float = 0.1,
        cooldown_seconds: int = 0,
        max_drawdown_pct: float = 0.0
    ):
        self.symbol = symbol
        self.max_holding_seconds = max_holding_seconds
        self.risk_percent = risk_percent
        self.cooldown_seconds = cooldown_seconds
        self.max_drawdown_pct = max_drawdown_pct

        self.adapter = RealMT5Adapter()
        self.magic_number = 777111
        self.last_trade_exit_time = 0.0
        self.consecutive_losses = 0
        self.is_running = False

    def initialize(self) -> bool:
        if not self.adapter.connect():
            print("[ERROR] Failed to connect MT5 adapter.")
            return False
        return True

    def detect_scalp_signal(self) -> Optional[str]:
        import MetaTrader5 as mt5

        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, 30)
        if rates is None or len(rates) < 25:
            return None

        closes = rates['close']
        ema9 = float(np.mean(closes[-9:]))
        ema21 = float(np.mean(closes[-21:]))
        c_curr = closes[-1]
        c_prev = closes[-2]

        # Trend & Momentum Signal Logic
        if ema9 > ema21 and c_curr > ema9 and c_curr > c_prev:
            return "BUY"
        elif ema9 < ema21 and c_curr < ema9 and c_curr < c_prev:
            return "SELL"
        return None

    def run_autonomous_loop(self, duration_seconds: Optional[int] = None):
        import MetaTrader5 as mt5

        acc = mt5.account_info()
        if not acc:
            print("[ERROR] Could not fetch account info.")
            return

        start_balance = acc.balance
        pip_scale = 0.10 if "XAU" in self.symbol or "USTEC" in self.symbol else 0.0001

        print("\n==================================================")
        print(" AUTONOMOUS HIGH-SPEED SCALPER DAEMON STARTED")
        print("==================================================")
        print(f"MT5 Account:          {acc.login} ({acc.server})")
        print(f"Current Balance:      ${acc.balance:.2f} USD")
        print(f"Target Symbol:        {self.symbol}")
        print(f"Micro Volume:         0.01 lot")
        print(f"Target Risk/Reward:   5.0 pips SL / 10.0 pips TP")
        print(f"Max Holding Horizon:  {self.max_holding_seconds} seconds")
        print(f"Post-Trade Cooldown:  {self.cooldown_seconds} seconds")
        print(f"Equity Stop Guard:    {self.max_drawdown_pct if self.max_drawdown_pct > 0 else 'Disabled (Continuous Scalp)'}")
        print("==================================================")
        print("Scanning live MT5 market for autonomous scalp signals...")
        print("Press Ctrl+C in terminal to stop at any time.\n")

        start_time = time.time()
        trades_executed = 0

        try:
            while True:
                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break

                now = time.time()
                acc_curr = mt5.account_info()
                if acc_curr:
                    balance = acc_curr.balance
                    equity = acc_curr.equity
                    dd_pct = ((start_balance - equity) / start_balance) * 100.0
                    if self.max_drawdown_pct > 0 and dd_pct >= self.max_drawdown_pct:
                        print(f"\n[EQUITY GUARD TRIGGERED ({dd_pct:.1f}% DD)] Stopping autonomous scalp daemon.")
                        break

                # Check if position currently open
                open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                active = [p for p in (open_positions or []) if p.magic == self.magic_number]

                if active and len(active) > 0:
                    pos = active[0]
                    hold_time = now - pos.time
                    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Active Scalp Ticket #{pos.ticket} | Direction: {'BUY' if pos.type==0 else 'SELL'} | Profit: ${pos.profit:+.2f} USD | Hold Time: {int(hold_time)}s")

                    # Autoclose if max horizon reached
                    if hold_time >= self.max_holding_seconds:
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
                            "comment": "AutoScalp Timeout Close",
                            "type_time": mt5.ORDER_TIME_GTC,
                            "type_filling": mt5.ORDER_FILLING_IOC,
                        }
                        res_close = mt5.order_send(req_close)
                        if res_close and res_close.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"\n[AUTOCLOSED TICKET #{pos.ticket}] Closed at price {res_close.price} | Profit: ${pos.profit:+.2f} USD")
                            self.last_trade_exit_time = time.time()
                else:
                    # Check Cooldown
                    if (now - self.last_trade_exit_time) < self.cooldown_seconds:
                        rem_cd = int(self.cooldown_seconds - (now - self.last_trade_exit_time))
                        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Cooldown active ({rem_cd}s remaining)... Balance: ${acc_curr.balance:.2f}")
                    else:
                        # Scan for Autonomous Scalp Signal
                        sig = self.detect_scalp_signal()
                        if sig:
                            tick = mt5.symbol_info_tick(self.symbol)
                            if tick:
                                is_buy = (sig == "BUY")
                                price = tick.ask if is_buy else tick.bid
                                sl = round(price - (5.0 * pip_scale), 5) if is_buy else round(price + (5.0 * pip_scale), 5)
                                tp = round(price + (10.0 * pip_scale), 5) if is_buy else round(price - (10.0 * pip_scale), 5)

                                req_open = {
                                    "action": mt5.TRADE_ACTION_DEAL,
                                    "symbol": self.symbol,
                                    "volume": 0.01,
                                    "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                                    "price": price,
                                    "sl": sl,
                                    "tp": tp,
                                    "deviation": 10,
                                    "magic": self.magic_number,
                                    "comment": "Autonomous Scalp",
                                    "type_time": mt5.ORDER_TIME_GTC,
                                    "type_filling": mt5.ORDER_FILLING_IOC,
                                }

                                print(f"\n[SIGNAL DETECTED: {sig}] Submitting Autonomous Scalp Order to MT5...")
                                res_open = mt5.order_send(req_open)
                                if res_open and res_open.retcode == mt5.TRADE_RETCODE_DONE:
                                    trades_executed += 1
                                    print(f"[SCALP OPENED SUCCESS] Ticket #{res_open.order} at {res_open.price} (SL: {sl}, TP: {tp})")
                                else:
                                    print(f"[BROKER RESPONSE] Code: {res_open.retcode if res_open else 'None'} | Comment: {res_open.comment if res_open else 'Error'}")

                time.sleep(2.0)
        except KeyboardInterrupt:
            print("\n[INFO] Autonomous Scalper Daemon stopped by user.")

        self.adapter.disconnect()
        acc_final = mt5.account_info()
        print(f"\nDaemon Stopped. Final Balance: ${acc_final.balance if acc_final else start_balance:.2f} USD")
        return {"trades_executed": trades_executed}
