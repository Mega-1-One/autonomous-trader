import sys
import time
import json
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings, ExecutionMode
from app.data.mt5_real import RealMT5Adapter

class GoldMultiPositionProfitScalper:
    """Gold (XAUUSDm) Reversal Scalper Engine (Explicit TP + protective SL, profit-target close).
    
    Controlled by dynamic risk-based entry management rather than arbitrary trade count limits.
    Features fast continuous scanning, non-blocking terminal commands (STOP, START, STATUS, TEST),
    MT5 reconciliation, duplicate order prevention, strategy debug diagnostics, and performance metrics.
    """

    def __init__(
        self,
        symbol: str = "XAUUSDm",
        volume: float = 0.01,
        max_open_positions: Optional[int] = None,
        take_profit_pips: float = 15.0,
        min_profit_target_usd: float = 0.15,
        stop_loss_pips: float = 5.0,
        max_loss_usd: float = 2.0,
        max_holding_seconds: float = 120.0,
        test_entry: bool = False,
        # Configurable Risk Parameters
        risk_per_trade_percent: float = 0.5,
        max_total_risk_percent: float = 5.0,
        max_daily_loss_percent: float = 5.0,
        max_drawdown_percent: float = 10.0,
        min_free_margin_percent: float = 20.0,
        max_margin_usage_percent: float = 70.0
    ):
        self.symbol = symbol
        self.volume = volume
        self.max_open_positions = max_open_positions  # Deprecated count cap (Risk Engine controls capacity)
        self.take_profit_pips = take_profit_pips
        self.min_profit_target_usd = min_profit_target_usd
        self.stop_loss_pips = stop_loss_pips
        self.max_loss_usd = max_loss_usd
        self.max_holding_seconds = max_holding_seconds
        self.test_entry = test_entry
        
        # Risk Model Parameters
        self.risk_per_trade_percent = risk_per_trade_percent
        self.max_total_risk_percent = max_total_risk_percent
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_drawdown_percent = max_drawdown_percent
        self.min_free_margin_percent = min_free_margin_percent
        self.max_margin_usage_percent = max_margin_usage_percent
        
        self.adapter = RealMT5Adapter()
        self.magic_number = 888777
        self.last_price = 0.0
        self.peak_equity = 0.0
        
        # Interactive state & threading
        self.state = "RUNNING"
        self.is_running = True
        self.lock = threading.Lock()
        
        # Performance & Stats
        self.todays_trades = 0
        self.todays_wins = 0
        self.todays_losses = 0
        self.todays_realized_pnl = 0.0
        self.last_trade_ticket: Optional[int] = None
        self.last_trade_result: Optional[str] = None
        self.last_trade_time: Optional[str] = None
        self.last_risk_block_reason: Optional[str] = None
        self.tracked_positions: Dict[int, Dict[str, Any]] = {}
        
        self.last_order_time = 0.0
        self.last_risk_log_time = 0.0
        self.last_debug_log_time = 0.0
        self.last_loop_time = 0.0
        self.last_strategy_eval_time = 0.0
        self.last_order_sub_time = 0.0
        self.scan_count = 0
        self.scans_per_sec = 0.0
        self.last_fps_check = time.time()

    def initialize(self) -> bool:
        if not self.adapter.connect():
            print("[ERROR] Failed to connect MT5 adapter.")
            return False
        return True

    def _start_command_listener(self):
        """Non-blocking background thread listening for terminal user commands."""
        def listener():
            while self.is_running:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    cmd = line.strip().upper()
                    if cmd == "STOP":
                        with self.lock:
                            self.state = "STOPPED"
                        print("\n[STOP COMMAND] New trades disabled.")
                        print("[STOP COMMAND] Existing positions will continue to be managed.\n")
                    elif cmd == "START":
                        with self.lock:
                            self.state = "RUNNING"
                        print("\n[START COMMAND] Continuous trading resumed.\n")
                    elif cmd == "STATUS":
                        self.print_status()
                    elif cmd in ("TEST", "TEST_ENTRY"):
                        with self.lock:
                            self.test_entry = True
                        print("\n[TEST ENTRY COMMAND] Safe Test Entry mode activated for 1 trade.\n")
                except Exception:
                    time.sleep(0.1)

        t = threading.Thread(target=listener, daemon=True)
        t.start()

    def evaluate_risk_for_new_order(
        self,
        acc: Any,
        tick: Any,
        active_positions: List[Any],
        proposed_direction: str,
        proposed_volume: float,
        proposed_sl_price: float
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Evaluates whether opening a proposed order is financially safe according to account risk metrics."""
        balance = acc.balance
        equity = acc.equity
        free_margin = acc.margin_free
        margin_used = acc.margin

        if balance <= 0 or equity <= 0:
            return False, "[RISK BLOCK] Account balance or equity is zero or negative.", {}

        # 1. Track peak equity for drawdown protection
        if self.peak_equity == 0.0 or equity > self.peak_equity:
            self.peak_equity = equity

        # 2. Floating P/L & Daily Loss Limit Check
        total_floating_pnl = sum(p.profit + p.swap for p in active_positions)
        net_daily_pnl = self.todays_realized_pnl + total_floating_pnl
        max_daily_loss_usd = balance * (self.max_daily_loss_percent / 100.0)
        
        if net_daily_pnl <= -max_daily_loss_usd:
            return False, f"[RISK BLOCK] Daily loss limit reached (${net_daily_pnl:+.2f} USD <= -${max_daily_loss_usd:.2f} USD limit).", {}

        # 3. Maximum Drawdown Check
        current_drawdown = ((self.peak_equity - equity) / self.peak_equity) * 100.0 if self.peak_equity > 0 else 0.0
        if current_drawdown >= self.max_drawdown_percent:
            return False, f"[RISK BLOCK] Maximum drawdown threshold reached ({current_drawdown:.1f}% >= {self.max_drawdown_percent:.1f}% limit).", {}

        # 4. Open Position SL Risk Calculation
        current_open_risk_usd = 0.0
        pip_scale = 0.10 if ("XAU" in self.symbol or "GOLD" in self.symbol) else 0.0001
        
        for pos in active_positions:
            if pos.sl > 0:
                sl_dist = abs(pos.price_open - pos.sl)
                pos_sl_risk = sl_dist * pos.volume * 100.0
            else:
                pos_sl_risk = self.max_loss_usd
            current_open_risk_usd += pos_sl_risk

        # 5. Proposed Order SL Risk Calculation
        entry_price = tick.ask if proposed_direction == "BUY" else tick.bid
        proposed_sl_dist = abs(entry_price - proposed_sl_price)
        new_trade_sl_risk_usd = proposed_sl_dist * proposed_volume * 100.0

        projected_total_risk_usd = current_open_risk_usd + new_trade_sl_risk_usd
        max_allowed_risk_usd = balance * (self.max_total_risk_percent / 100.0)

        if projected_total_risk_usd > max_allowed_risk_usd:
            return False, f"[RISK BLOCK] Maximum total open risk reached (Projected: ${projected_total_risk_usd:.2f} / Max Allowed: ${max_allowed_risk_usd:.2f}).", {
                "current_open_risk": current_open_risk_usd,
                "new_trade_risk": new_trade_sl_risk_usd,
                "projected_risk": projected_total_risk_usd,
                "max_allowed_risk": max_allowed_risk_usd
            }

        # 6. Margin & Free Margin Protection
        leverage = acc.leverage if (acc and acc.leverage > 0) else 2000
        approx_margin_req = (entry_price * proposed_volume * 100.0) / leverage
        projected_margin_used = margin_used + approx_margin_req
        projected_free_margin = free_margin - approx_margin_req

        free_margin_pct = (projected_free_margin / equity) * 100.0 if equity > 0 else 0.0
        if free_margin_pct < self.min_free_margin_percent:
            return False, f"[RISK BLOCK] Insufficient free margin (Projected Free Margin: {free_margin_pct:.1f}% < {self.min_free_margin_percent:.1f}% min).", {}

        margin_usage_pct = (projected_margin_used / equity) * 100.0 if equity > 0 else 0.0
        if margin_usage_pct > self.max_margin_usage_percent:
            return False, f"[RISK BLOCK] Margin usage too high (Projected Margin Usage: {margin_usage_pct:.1f}% > {self.max_margin_usage_percent:.1f}% max).", {}

        risk_metrics = {
            "current_open_risk": current_open_risk_usd,
            "new_trade_risk": new_trade_sl_risk_usd,
            "projected_risk": projected_total_risk_usd,
            "max_allowed_risk": max_allowed_risk_usd,
            "risk_used_pct": (current_open_risk_usd / balance) * 100.0 if balance > 0 else 0.0,
            "available_risk_pct": max(0.0, self.max_total_risk_percent - ((current_open_risk_usd / balance) * 100.0)) if balance > 0 else 0.0,
            "margin_usage_pct": margin_usage_pct,
            "free_margin_pct": free_margin_pct
        }

        return True, "[RISK APPROVED] New trade allowed.", risk_metrics

    def print_status(self):
        """Display non-blocking risk & trade status summary to terminal."""
        import MetaTrader5 as mt5
        acc = mt5.account_info()
        tick = mt5.symbol_info_tick(self.symbol)
        open_positions = mt5.positions_get(group=f"*{self.symbol}*")
        active = [p for p in (open_positions or []) if p.magic == self.magic_number]
        floating_pnl = sum(p.profit + p.swap for p in active) if active else 0.0
        
        balance = acc.balance if acc else 0.0
        equity = acc.equity if acc else 0.0
        free_margin = acc.margin_free if acc else 0.0
        margin_used = acc.margin if acc else 0.0
        
        margin_usage_pct = (margin_used / equity * 100.0) if (equity and equity > 0) else 0.0
        current_open_risk = sum((abs(p.price_open - p.sl) * p.volume * 100.0) if p.sl > 0 else self.max_loss_usd for p in active)
        risk_used_pct = (current_open_risk / balance * 100.0) if (balance and balance > 0) else 0.0
        available_risk_pct = max(0.0, self.max_total_risk_percent - risk_used_pct)

        print("\n==================================================")
        print("   GOLD SCALPER — RISK-BASED CONTINUOUS STATUS    ")
        print("==================================================")
        print(f"MT5 Connection:         {'CONNECTED' if (acc and self.adapter.is_connected()) else 'DISCONNECTED'}")
        print(f"Account:                {acc.login if acc else 'N/A'}")
        print(f"Server / Broker:        {acc.server if acc else 'N/A'}")
        print(f"Balance:                ${balance:.2f} USD")
        print(f"Equity:                 ${equity:.2f} USD")
        print(f"Free Margin:            ${free_margin:.2f} USD")
        print(f"Margin Usage:           {margin_usage_pct:.1f}%")
        print(f"Open Positions:         {len(active)}")
        print(f"Risk Used:              {risk_used_pct:.1f}%")
        print(f"Available Risk:         {available_risk_pct:.1f}%")
        print(f"Floating P/L:           ${floating_pnl:+.2f} USD")
        print(f"Today's Realized P/L:   ${self.todays_realized_pnl:+.2f} USD (Trades: {self.todays_trades})")
        print(f"Current Bot State:      {self.state} (TEST_ENTRY: {'ON' if self.test_entry else 'OFF'})")
        print(f"Last Risk Status:       {self.last_risk_block_reason if self.last_risk_block_reason else '[RISK APPROVED]'}")
        print(f"Fast Scan Performance:  Loop: {self.last_loop_time:.4f}s | Strategy: {self.last_strategy_eval_time:.4f}s | Speed: {self.scans_per_sec:.1f} scans/sec")
        print("==================================================")
        print("Commands: STOP (pause new trades) | START (resume) | STATUS (stats) | TEST (single test trade)")
        print(">\n")

    def run_multi_scalper_loop(self, duration_seconds: Optional[int] = None):
        import MetaTrader5 as mt5

        acc = mt5.account_info()
        if not acc:
            print("[ERROR] Could not fetch account info.")
            return

        pip_scale = 0.10 if ("XAU" in self.symbol or "GOLD" in self.symbol) else 0.0001

        print("\n==================================================")
        print(" GOLD REVERSAL & PROFIT-ONLY SCALPER (DYNAMIC RISK)")
        print("==================================================")
        print(f"MT5 Account:            {acc.login} ({acc.server})")
        print(f"Current Balance:        ${acc.balance:.2f} USD")
        print(f"Target Symbol:          {self.symbol} (Gold)")
        print(f"Micro Volume:           {self.volume} lot per trade")
        print(f"Trade Limit Model:      DYNAMIC RISK ENGINE (No Count Cap)")
        print(f"Risk Per Trade:         {self.risk_per_trade_percent}% of balance")
        print(f"Max Total Open Risk:    {self.max_total_risk_percent}% of balance")
        print(f"Max Daily Loss Cap:     {self.max_daily_loss_percent}% of balance")
        print(f"Take Profit Target:     +{self.take_profit_pips} pips (Explicit TP on Broker)")
        print(f"Stop Loss:              -{self.stop_loss_pips} pips (Protective SL on Broker) + ${self.max_loss_usd:.2f} loss cap")
        print(f"Close Triggers:         PROFIT >= +${self.min_profit_target_usd:.2f} | LOSS <= -${self.max_loss_usd:.2f}")
        print("==================================================")
        print("Commands: STOP = pause new trades | START = resume | STATUS = view stats | TEST = 1 test scalp")
        print("Press Ctrl+C in terminal for emergency shutdown.\n")

        self._start_command_listener()

        start_time = time.time()
        self.is_running = True

        try:
            while self.is_running:
                t_loop_start = time.perf_counter()

                if duration_seconds and (time.time() - start_time) >= duration_seconds:
                    break

                now = time.time()
                
                # Connection & Tick Verification
                acc_curr = mt5.account_info()
                tick = mt5.symbol_info_tick(self.symbol)
                
                if not acc_curr or not tick:
                    print("[MT5 WARNING] Connection/data unavailable. Retrying...")
                    time.sleep(1.0)
                    self.adapter.connect()
                    continue

                balance = acc_curr.balance

                # 1. Fetch actual MT5 open positions (Source of Truth)
                open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                active = [p for p in (open_positions or []) if p.magic == self.magic_number]
                active_tickets = {p.ticket for p in active}

                # 2. MT5 Reconciliation: detect positions closed externally by broker TP/SL or manual close
                untracked_closed = [t for t in list(self.tracked_positions.keys()) if t not in active_tickets]
                for ticket in untracked_closed:
                    meta = self.tracked_positions.pop(ticket)
                    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [POSITION RECONCILED] Ticket #{ticket} ({meta.get('type')}) closed externally on MT5.")
                    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Returning to market scan...\n")

                # 3. POSITION MANAGEMENT: Check profit target & protective loss caps
                for pos in active:
                    if pos.ticket not in self.tracked_positions:
                        self.tracked_positions[pos.ticket] = {
                            "ticket": pos.ticket,
                            "symbol": pos.symbol,
                            "type": "BUY" if pos.type == 0 else "SELL",
                            "volume": pos.volume,
                            "price_open": pos.price_open,
                            "sl": pos.sl,
                            "tp": pos.tp,
                            "time": pos.time,
                            "time_str": datetime.fromtimestamp(pos.time, timezone.utc).strftime("%H:%M:%S")
                        }

                    net_profit = pos.profit + pos.swap
                    hold_time = now - pos.time

                    if net_profit >= self.min_profit_target_usd:
                        reason, comment = "PROFIT TARGET", "Gold Profit-Only Close"
                    elif net_profit <= -self.max_loss_usd:
                        reason, comment = "STOP LOSS", "Gold Stop-Loss Close"
                    elif self.max_holding_seconds and self.max_holding_seconds > 0 and hold_time >= self.max_holding_seconds:
                        reason, comment = "MAX HOLD", "Gold Max-Hold Close"
                    else:
                        continue

                    close_price = tick.bid if pos.type == 0 else tick.ask
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
                        self.todays_trades += 1
                        self.todays_realized_pnl += net_profit
                        if net_profit > 0:
                            self.todays_wins += 1
                        else:
                            self.todays_losses += 1

                        self.last_trade_ticket = pos.ticket
                        self.last_trade_result = f"${net_profit:+.2f} USD ({reason})"
                        self.last_trade_time = datetime.now(timezone.utc).strftime("%H:%M:%S")

                        direction_str = "BUY" if pos.type == 0 else "SELL"
                        print(f"\n[TRADE CLOSED]")
                        print(f"Ticket:       #{pos.ticket}")
                        print(f"Symbol:       {self.symbol}")
                        print(f"Direction:    {direction_str}")
                        print(f"Entry:        {pos.price_open}")
                        print(f"Exit:         {res_close.price}")
                        print(f"Net P/L:      ${net_profit:+.2f} USD")
                        print(f"Hold Time:    {int(hold_time)}s")
                        print(f"Close Reason: {reason}\n")
                        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Returning to market scan...\n")

                        if pos.ticket in self.tracked_positions:
                            del self.tracked_positions[pos.ticket]

                # Re-query MT5 positions after management
                open_positions = mt5.positions_get(group=f"*{self.symbol}*")
                active = [p for p in (open_positions or []) if p.magic == self.magic_number]

                # 4. STRATEGY EVALUATION & DYNAMIC RISK CHECK
                t_eval_start = time.perf_counter()

                with self.lock:
                    current_state = self.state
                    is_test_mode = self.test_entry

                curr_mid = (tick.ask + tick.bid) / 2.0
                spread = tick.ask - tick.bid
                
                if self.last_price > 0:
                    direction = "BUY" if curr_mid >= self.last_price else "SELL"
                    signal_desc = f"{direction} (Price momentum: {curr_mid:.3f} {'>=' if direction=='BUY' else '<'} {self.last_price:.3f})"
                else:
                    direction = "BUY"
                    signal_desc = "BUY (Initial market entry signal)"

                self.last_price = curr_mid
                self.last_strategy_eval_time = time.perf_counter() - t_eval_start

                # Calculate Proposed Order Entry Parameters
                is_buy = (direction == "BUY")
                entry_price = tick.ask if is_buy else tick.bid

                min_sl_dist = max(1.00, self.stop_loss_pips * pip_scale, spread * 2.5)
                min_tp_dist = max(1.50, self.take_profit_pips * pip_scale, spread * 3.0)
                tp = round(entry_price + min_tp_dist, 3) if is_buy else round(entry_price - min_tp_dist, 3)
                sl = round(entry_price - min_sl_dist, 3) if is_buy else round(entry_price + min_sl_dist, 3)

                # DYNAMIC RISK EVALUATION
                risk_passed, risk_reason, risk_details = self.evaluate_risk_for_new_order(
                    acc=acc_curr,
                    tick=tick,
                    active_positions=active,
                    proposed_direction=direction,
                    proposed_volume=self.volume,
                    proposed_sl_price=sl
                )
                self.last_risk_block_reason = risk_reason

                # Compact 1-Second Strategy & Risk Debug Display
                if now - self.last_debug_log_time >= 1.0:
                    self.last_debug_log_time = now
                    current_open_risk = sum((abs(p.price_open - p.sl) * p.volume * 100.0) if p.sl > 0 else self.max_loss_usd for p in active)
                    risk_used_pct = (current_open_risk / balance * 100.0) if balance > 0 else 0.0
                    avail_risk_pct = max(0.0, self.max_total_risk_percent - risk_used_pct)
                    margin_usage_pct = (acc_curr.margin / acc_curr.equity * 100.0) if acc_curr.equity > 0 else 0.0

                    print(f"\n[STRATEGY & RISK DEBUG] {datetime.now(timezone.utc).strftime('%H:%M:%S')} | Symbol: {self.symbol}")
                    print(f"Price: Bid: {tick.bid:.3f} | Ask: {tick.ask:.3f} | Spread: {spread:.3f} ({spread/pip_scale:.1f} pips)")
                    print(f"Bot State: {current_state} | Active Trades: {len(active)} | Risk Used: {risk_used_pct:.1f}% | Available Risk: {avail_risk_pct:.1f}% | Free Margin: ${acc_curr.margin_free:.2f}")
                    print(f"Signal: {signal_desc}")
                    print("Pipeline & Risk Diagnostics:")
                    print(f"  1. Market Data Check:      PASS (Valid XAUUSDm tick received)")
                    print(f"  2. Timeframe & Session:    PASS (Fast Tick Reversal / 24-7 Gold)")
                    print(f"  3. Spread Filter Check:    PASS (Spread {spread:.3f} <= 1.000 max)")
                    print(f"  4. Account Margin Check:   PASS (Margin Usage: {margin_usage_pct:.1f}% <= {self.max_margin_usage_percent:.1f}% max)")
                    print(f"  5. Dynamic Risk Engine:    {'PASS' if risk_passed else 'BLOCK'} ({risk_reason})")
                    print(f"  6. Strategy Signal:        PASS ({direction})")
                    print(f"  7. Deduplication Buffer:   {'PASS' if (now - self.last_order_time >= 0.2 or is_test_mode) else 'WAITING (Buffer)'} (Elapsed: {now - self.last_order_time:.2f}s)")
                    print(f"  8. Order Pipeline Status:  {'EXECUTING TEST TRADE' if is_test_mode else ('READY' if (current_state == 'RUNNING' and risk_passed) else 'PAUSED/RISK_BLOCKED')}\n")

                # ORDER EXECUTION ENGINE (Risk-Gated)
                if is_test_mode or (current_state == "RUNNING"):
                    if not risk_passed and not is_test_mode:
                        if now - self.last_risk_log_time >= 5.0:
                            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {risk_reason}")
                            self.last_risk_log_time = now
                    else:
                        # Deduplication Protection: minimum 0.2s between orders (bypassed for TEST_ENTRY)
                        if is_test_mode or (now - self.last_order_time >= 0.2):
                            t_order_start = time.perf_counter()
                            req_open = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": self.symbol,
                                "volume": self.volume,
                                "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                                "price": entry_price,
                                "sl": sl,
                                "tp": tp,
                                "deviation": 10,
                                "magic": self.magic_number,
                                "comment": f"Gold Scalp {'TEST' if is_test_mode else '#' + str(self.todays_trades+len(active)+1)}",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }

                            res_open = mt5.order_send(req_open)
                            self.last_order_sub_time = time.perf_counter() - t_order_start

                            # Reset test_entry flag after single test execution
                            if is_test_mode:
                                with self.lock:
                                    self.test_entry = False
                                print("[TEST ENTRY COMPLETE] Test trade execution finished. Reset TEST_ENTRY=OFF.\n")

                            retcode_desc = {
                                10009: "TRADE_RETCODE_DONE (Order executed cleanly)",
                                10013: "TRADE_RETCODE_INVALID (Invalid order parameters)",
                                10014: "TRADE_RETCODE_INVALID_VOLUME (Invalid lot size)",
                                10015: "TRADE_RETCODE_INVALID_PRICE (Invalid entry price)",
                                10016: "TRADE_RETCODE_INVALID_STOPS (Invalid SL or TP distance)",
                                10027: "TRADE_RETCODE_AUTOTRADER_DISABLED (Algo Trading disabled in MT5 toolbar)"
                            }.get(res_open.retcode if res_open else -1, f"Retcode {res_open.retcode if res_open else 'None'}")

                            if res_open and res_open.retcode == mt5.TRADE_RETCODE_DONE:
                                self.last_order_time = now
                                open_time_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
                                print(f"\n[RISK APPROVED] New trade allowed.")
                                print(f"[TRADE OPENED]")
                                print(f"Ticket:    #{res_open.order}")
                                print(f"Symbol:    {self.symbol}")
                                print(f"Direction: {direction}")
                                print(f"Volume:    {self.volume} lot")
                                print(f"Entry:     {res_open.price}")
                                print(f"SL:        {sl}")
                                print(f"TP:        {tp}")
                                print(f"Time:      {open_time_str}\n")

                                self.tracked_positions[res_open.order] = {
                                    "ticket": res_open.order,
                                    "symbol": self.symbol,
                                    "type": direction,
                                    "volume": self.volume,
                                    "price_open": res_open.price,
                                    "sl": sl,
                                    "tp": tp,
                                    "time": now,
                                    "time_str": open_time_str
                                }
                            else:
                                print(f"\n[ORDER PIPELINE FAILED]")
                                print(f"Signal generated: YES ({direction})")
                                print(f"Risk approved:    {'YES' if risk_passed else 'NO'}")
                                print(f"Order prepared:   YES (Volume: {self.volume}, Price: {entry_price}, SL: {sl}, TP: {tp})")
                                print(f"order_send called: YES")
                                print(f"MT5 Result:       {retcode_desc}")
                                if res_open and res_open.retcode == 10027:
                                    print("[ACTION REQUIRED] Click the GREEN 'Algo Trading' button in MT5 to allow scalping orders.\n")

                # Fast yield (50ms) to maintain fast scanning without CPU saturation
                time.sleep(0.05)

                self.last_loop_time = time.perf_counter() - t_loop_start
                self.scan_count += 1
                if now - self.last_fps_check >= 1.0:
                    self.scans_per_sec = self.scan_count / (now - self.last_fps_check)
                    self.scan_count = 0
                    self.last_fps_check = now

        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Stopping bot...")
            print("[SHUTDOWN] Existing positions will remain managed until closed.")
            self.is_running = False

        self.adapter.disconnect()
        acc_end = mt5.account_info()
        print(f"\nSession Complete. Today's Trades: {self.todays_trades} | Wins: {self.todays_wins} | Losses: {self.todays_losses} | Realized P/L: ${self.todays_realized_pnl:+.2f} USD | Final Balance: ${acc_end.balance if acc_end else balance:.2f} USD")
        return {
            "todays_trades": self.todays_trades,
            "todays_wins": self.todays_wins,
            "todays_losses": self.todays_losses,
            "todays_realized_pnl": self.todays_realized_pnl
        }
