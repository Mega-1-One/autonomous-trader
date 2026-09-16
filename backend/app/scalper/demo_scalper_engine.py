import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from app.core.config import settings, ExecutionMode
from app.core.safety import ensure_trading_allowed, account_trade_mode_from_mt5, SafetyViolation
from app.data.mt5_real import RealMT5Adapter
from app.scalper.mt5_orders import build_close_request, build_market_order, pip_scale_for

class MT5DemoMicroScalper:
    """High-Speed Micro-Scalper Engine for MT5 Demo Account (30s max holding, tight 5/10 pip SL/TP)."""

    def __init__(self, target_symbol: str = "XAUUSDm", volume: float = 0.01):
        self.symbol = target_symbol
        self.volume = volume
        self.adapter = RealMT5Adapter()

    def initialize(self) -> bool:
        if not self.adapter.connect():
            print("[ERROR] Failed to connect MT5 adapter.")
            return False
        return True

    def execute_micro_scalp(self, direction: str = "BUY", sl_pips: float = 5.0, tp_pips: float = 10.0, max_hold_sec: float = 30.0):
        import MetaTrader5 as mt5

        acc = mt5.account_info()
        if not acc:
            print("[ERROR] Could not fetch account info.")
            return

        print("\n==================================================")
        print(" HIGH-SPEED MICRO-SCALPER ENGINE EXECUTION")
        print("==================================================")
        print(f"MT5 Account:      {acc.login} ({acc.server})")
        print(f"Account Balance:  ${acc.balance:.2f} USD")
        print(f"Scalp Symbol:     {self.symbol}")
        print(f"Scalp Volume:     {self.volume} lot")
        print(f"Scalp Direction:  {direction}")
        print(f"Target Risk/Reward: {sl_pips} pips SL / {tp_pips} pips TP")
        print(f"Max Scalp Horizon: {max_hold_sec} seconds")
        print("==================================================\n")

        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            print(f"[ERROR] Could not fetch live tick for {self.symbol}")
            return

        pip_scale = pip_scale_for(self.symbol)
        is_buy = (direction == "BUY")

        price = tick.ask if is_buy else tick.bid
        sl = round(price - (sl_pips * pip_scale), 3 if "XAU" in self.symbol else 5) if is_buy else round(price + (sl_pips * pip_scale), 3 if "XAU" in self.symbol else 5)
        tp = round(price + (tp_pips * pip_scale), 3 if "XAU" in self.symbol else 5) if is_buy else round(price - (tp_pips * pip_scale), 3 if "XAU" in self.symbol else 5)

        request = build_market_order(
            mt5,
            symbol=self.symbol,
            order_type=mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            volume=self.volume,
            price=price,
            sl=sl,
            tp=tp,
            deviation=10,
            magic=999111,
            comment="MicroScalp 30s",
        )

        print(f"Submitting Instant Micro-Scalp Order to MT5...")
        try:
            ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
        except SafetyViolation as exc:
            print(f"[SAFETY GATE REFUSED] {exc}")
            self.adapter.disconnect()
            return
        start_ts = time.time()
        result = mt5.order_send(request)

        if result is None:
            print("[BROKER RESPONSE] order_send returned None (request failed)")
            return
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[BROKER RESPONSE] Code: {result.retcode} | Comment: {result.comment}")
            if result.retcode == 10027:
                print("\n[ACTION REQUIRED] Please click the GREEN 'Algo Trading' button in your MT5 terminal to allow scalping orders.")
            return

        print(f"\n[SCALP OPENED SUCCESS] Ticket #{result.order} at price {result.price} (SL: {sl}, TP: {tp})")

        # Scalp Management Loop (Max 30s)
        ticket = result.order
        print("Monitoring micro-scalp position (30s max horizon)...")

        while (time.time() - start_ts) < max_hold_sec:
            positions = mt5.positions_get(ticket=ticket)
            if not positions or len(positions) == 0:
                print(f"[SCALP CLOSED] Position #{ticket} closed by SL/TP target!")
                break
            time.sleep(0.5)

        # Autoclose after 30s if still open
        positions = mt5.positions_get(ticket=ticket)
        if positions and len(positions) > 0:
            pos = positions[0]
            print(f"[MAX HORIZON REACHED ({max_hold_sec}s)] Autoclosing micro-scalp position #{ticket}...")
            close_price = mt5.symbol_info_tick(self.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(self.symbol).ask
            close_req = build_close_request(
                mt5,
                symbol=self.symbol,
                volume=pos.volume,
                close_type=mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                position_ticket=pos.ticket,
                price=close_price,
                deviation=10,
                magic=999111,
                comment="Scalp Timeout Close",
            )
            try:
                ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
            except SafetyViolation as exc:
                print(f"[SAFETY GATE REFUSED] {exc}")
                return
            close_res = mt5.order_send(close_req)
            if close_res is None:
                print("[BROKER RESPONSE] close order_send returned None")
            elif close_res.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[SCALP AUTOCLOSED] Closed ticket #{ticket} at {close_res.price}")

        acc_after = mt5.account_info()
        print(f"Updated Demo Balance: ${acc_after.balance:.2f} USD")
        self.adapter.disconnect()
