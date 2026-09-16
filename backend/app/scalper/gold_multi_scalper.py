import sys
import time
import json
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from app.core.config import settings, ExecutionMode
from app.core.pricing import pnl as spec_pnl
from app.core.safety import ensure_trading_allowed, account_trade_mode_from_mt5, SafetyViolation
from app.data.mt5_real import RealMT5Adapter
from app.scalper.mt5_orders import (
    broker_reject_hint,
    build_close_request,
    build_market_order,
    pip_scale_for,
)

class GoldMultiPositionProfitScalper:
    """Gold (XAUUSDm) Reversal Scalper Engine (Explicit TP + protective SL, profit-target close).
    
    MANUAL STOP ONLY Architecture:
    The bot trades continuously until the user explicitly types 'STOP'.
    All risk, drawdown, daily P/L, and margin calculations are displayed for MONITORING ONLY,
    and never automatically halt or block valid strategy trade entries.
    """

    def __init__(
        self,
        symbol: str = "XAUUSDm",
        volume: float = 0.01,
        max_open_positions: Optional[int] = None,
        take_profit_pips: float = 15.0,
        min_profit_target_usd: float = 0.60,
        stop_loss_pips: float = 5.0,
        max_loss_usd: float = 0.50,
        max_holding_seconds: float = 120.0,
        commission_per_lot: float = 7.0,
        test_entry: bool = False
    ):
        self.symbol = symbol
        self.volume = volume
        self.max_open_positions = max_open_positions
        self.take_profit_pips = take_profit_pips
        self.min_profit_target_usd = min_profit_target_usd
        self.stop_loss_pips = stop_loss_pips
        self.max_loss_usd = max_loss_usd
        self.max_holding_seconds = max_holding_seconds
        self.commission_per_lot = commission_per_lot
        self.test_entry = test_entry
        
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
        self.tracked_positions: Dict[int, Dict[str, Any]] = {}
        
        self.last_order_time = 0.0
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

    def _net_profit(self, pos: Any) -> float:
        """Net floating P/L after estimated commission.

        MT5 pos.profit is net of spread but commission posts separately to
        balance, so close decisions must subtract it or sub-cost 'wins'
        (e.g. +$0.20 gross ≈ +$0.13 net on 0.01 lot) look profitable.
        """
        return (pos.profit or 0.0) + (pos.swap or 0.0) - (pos.volume or 0.0) * self.commission_per_lot

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

    def calculate_account_risk_metrics(
        self,
        acc: Any,
        tick: Any,
        active_positions: List[Any],
        proposed_direction: str,
        proposed_volume: float,
        proposed_sl_price: float
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Calculates account metrics for MONITORING DISPLAY ONLY.
        
        Does NOT block trades based on drawdown, daily loss, total risk, or position count.
        Only checks basic MT5 broker account availability (balance > 0 and free_margin > 0).
        """
        balance = acc.balance if acc else 0.0
        equity = acc.equity if acc else 0.0
        free_margin = acc.margin_free if acc else 0.0
        margin_used = acc.margin if acc else 0.0

        # Track peak equity for information display
        if self.peak_equity == 0.0 or equity > self.peak_equity:
            self.peak_equity = equity

        current_drawdown_pct = ((self.peak_equity - equity) / self.peak_equity * 100.0) if self.peak_equity > 0 else 0.0
        total_floating_pnl = sum(p.profit + p.swap for p in active_positions)
        net_daily_pnl = self.todays_realized_pnl + total_floating_pnl

        # Calculate open SL risk for monitoring (spec-based contract, gold => 100)
        current_open_risk_usd = 0.0
        for pos in active_positions:
            if pos.sl > 0:
                current_open_risk_usd += spec_pnl(abs(pos.price_open - pos.sl), pos.volume, self.symbol)
            else:
                current_open_risk_usd += self.max_loss_usd

        entry_price = tick.ask if proposed_direction == "BUY" else tick.bid
        proposed_sl_dist = abs(entry_price - proposed_sl_price)
        new_trade_sl_risk_usd = spec_pnl(proposed_sl_dist, proposed_volume, self.symbol)
        projected_total_risk_usd = current_open_risk_usd + new_trade_sl_risk_usd

        risk_used_pct = (current_open_risk_usd / balance * 100.0) if balance > 0 else 0.0
        margin_usage_pct = (margin_used / equity * 100.0) if equity > 0 else 0.0

        metrics = {
            "balance": balance,
            "equity": equity,
            "free_margin": free_margin,
            "margin_used": margin_used,
            "margin_usage_pct": margin_usage_pct,
            "current_drawdown_pct": current_drawdown_pct,
            "net_daily_pnl": net_daily_pnl,
            "floating_pnl": total_floating_pnl,
            "current_open_risk": current_open_risk_usd,
            "new_trade_risk": new_trade_sl_risk_usd,
            "projected_risk": projected_total_risk_usd,
            "risk_used_pct": risk_used_pct
        }

        # ONLY BROKER EXECUTION MARGIN CHECK (Does not block for drawdown/daily loss/risk caps)
        if balance <= 0 or equity <= 0:
            return False, "[ORDER REJECTED BY BROKER] Account balance or equity is zero.", metrics
        if free_margin <= 0:
            return False, "[ORDER REJECTED BY BROKER] Insufficient free margin for order execution.", metrics

        return True, "PASS (Broker Execution Ready)", metrics

    def print_status(self):
        """Display non-blocking status summary for monitoring to terminal."""
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
        current_drawdown_pct = ((self.peak_equity - equity) / self.peak_equity * 100.0) if (self.peak_equity and self.peak_equity > 0) else 0.0
        current_open_risk = sum((spec_pnl(abs(p.price_open - p.sl), p.volume, self.symbol)) if p.sl > 0 else self.max_loss_usd for p in active)
        risk_used_pct = (current_open_risk / balance * 100.0) if (balance and balance > 0) else 0.0

        print("\n==================================================")
        print("    GOLD SCALPER — CONTINUOUS MONITORING DISPLAY  ")
        print("==================================================")
        print(f"MT5 Connection:         {'CONNECTED' if (acc and self.adapter.is_connected()) else 'DISCONNECTED'}")
        print(f"Account:                {acc.login if acc else 'N/A'}")
        print(f"Server / Broker:        {acc.server if acc else 'N/A'}")
        print(f"Balance:                ${balance:.2f} USD")
        print(f"Equity:                 ${equity:.2f} USD")
        print(f"Free Margin:            ${free_margin:.2f} USD")
        print(f"Margin Usage:           {margin_usage_pct:.1f}%")
        print(f"Drawdown:               {current_drawdown_pct:.1f}% (Information Only)")
        print(f"Open Positions:         {len(active)}")
        print(f"Risk Used:              {risk_used_pct:.1f}% (${current_open_risk:.2f} USD)")
        print(f"Floating P/L:           ${floating_pnl:+.2f} USD")
        print(f"Today's Realized P/L:   ${self.todays_realized_pnl:+.2f} USD (Trades: {self.todays_trades})")
        print(f"Trading State:          {self.state} (Manual Stop Only)")
        print(f"Fast Scan Performance:  Loop: {self.last_loop_time:.4f}s | Strategy: {self.last_strategy_eval_time:.4f}s | Speed: {self.scans_per_sec:.1f} scans/sec")
        print("==================================================")
        print("Commands: STOP (stop new trades) | START (resume trading) | STATUS (view details) | TEST (test scalp)")
        print(">\n")

    def run_multi_scalper_loop(self, duration_seconds: Optional[int] = None):
        import MetaTrader5 as mt5

        acc = mt5.account_info()
        if not acc:
            print("[ERROR] Could not fetch account info.")
            return

        pip_scale = pip_scale_for(self.symbol)

        print("\n==================================================")
        print(" GOLD REVERSAL SCALPER (MANUAL STOP ONLY MODE)   ")
        print("==================================================")
        print(f"MT5 Account:            {acc.login} ({acc.server})")
        print(f"Current Balance:        ${acc.balance:.2f} USD")
        print(f"Target Symbol:          {self.symbol} (Gold)")
        print(f"Micro Volume:           {self.volume} lot per trade")
        print(f"Control Model:          MANUAL STOP ONLY (No Auto Halts)")
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

                # 3. POSITION MANAGEMENT: Check profit target & protective loss caps for individual trades
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

                    net_profit = self._net_profit(pos)
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
                    req_close = build_close_request(
                        mt5,
                        symbol=self.symbol,
                        volume=pos.volume,
                        close_type=mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                        position_ticket=pos.ticket,
                        price=close_price,
                        deviation=10,
                        magic=self.magic_number,
                        comment=comment,
                    )
                    try:
                        ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
                    except SafetyViolation as exc:
                        print(f"[SAFETY GATE REFUSED] {exc}")
                        return {"error": str(exc)}
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

                # 4. STRATEGY EVALUATION & ORDER ENTRY PIPELINE
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

                # CALCULATE MONITORING METRICS & BROKER MARGIN CHECK ONLY
                broker_ready, broker_status, metrics = self.calculate_account_risk_metrics(
                    acc=acc_curr,
                    tick=tick,
                    active_positions=active,
                    proposed_direction=direction,
                    proposed_volume=self.volume,
                    proposed_sl_price=sl
                )

                # Compact 1-Second Strategy & Monitoring Debug Display
                if now - self.last_debug_log_time >= 1.0:
                    self.last_debug_log_time = now
                    print(f"\n[STRATEGY & RISK DEBUG] {datetime.now(timezone.utc).strftime('%H:%M:%S')} | Symbol: {self.symbol}")
                    print(f"Price: Bid: {tick.bid:.3f} | Ask: {tick.ask:.3f} | Spread: {spread:.3f} ({spread/pip_scale:.1f} pips)")
                    print(f"Balance: ${metrics.get('balance', 0):.2f} | Equity: ${metrics.get('equity', 0):.2f} | Free Margin: ${metrics.get('free_margin', 0):.2f} | Floating P/L: ${metrics.get('floating_pnl', 0):+.2f}")
                    print(f"Drawdown: {metrics.get('current_drawdown_pct', 0):.1f}% | Daily P/L: ${metrics.get('net_daily_pnl', 0):+.2f} | Open Positions: {len(active)}")
                    print(f"Trading State: {current_state}")
                    print(f"Signal: {direction}")
                    print("Diagnostics:")
                    print(f"  Strategy:           PASS ({signal_desc})")
                    print(f"  Broker Conditions:  {'PASS' if broker_ready else 'FAIL (' + broker_status + ')'}")
                    print(f"  Deduplication:      {'PASS' if (now - self.last_order_time >= 0.2 or is_test_mode) else 'WAITING (Buffer)'}")
                    print(f"  Order Pipeline:     {'EXECUTING TEST TRADE' if is_test_mode else ('READY' if (current_state == 'RUNNING' and broker_ready) else 'STOPPED_BY_USER')}\n")

                # ORDER EXECUTION ENGINE (Only user STOP or MT5 broker margin rejection stops orders)
                if is_test_mode or (current_state == "RUNNING"):
                    if not broker_ready and not is_test_mode:
                        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {broker_status}")
                    else:
                        # Deduplication Protection: minimum 0.2s between orders (bypassed for TEST_ENTRY)
                        if is_test_mode or (now - self.last_order_time >= 0.2):
                            t_order_start = time.perf_counter()
                            req_open = build_market_order(
                                mt5,
                                symbol=self.symbol,
                                order_type=mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                                volume=self.volume,
                                price=entry_price,
                                sl=sl,
                                tp=tp,
                                deviation=10,
                                magic=self.magic_number,
                                comment=f"Gold Scalp {'TEST' if is_test_mode else '#' + str(self.todays_trades+len(active)+1)}",
                            )

                            try:
                                ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
                            except SafetyViolation as exc:
                                print(f"[SAFETY GATE REFUSED] {exc}")
                                return {"error": str(exc)}

                            res_open = mt5.order_send(req_open)
                            if res_open is None:
                                print("[BROKER RESPONSE] order_send returned None (request failed)")
                                self.last_order_sub_time = time.perf_counter() - t_order_start
                                continue
                            self.last_order_sub_time = time.perf_counter() - t_order_start

                            # Reset test_entry flag after single test execution
                            if is_test_mode:
                                with self.lock:
                                    self.test_entry = False
                                print("[TEST ENTRY COMPLETE] Test trade execution finished. Reset TEST_ENTRY=OFF.\n")

                            retcode_desc = broker_reject_hint(res_open.retcode if res_open else None)

                            if res_open and res_open.retcode == mt5.TRADE_RETCODE_DONE:
                                self.last_order_time = now
                                open_time_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
                                print(f"\n[TRADE OPENED]")
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
                                print(f"\n[ORDER REJECTED BY MT5]")
                                print(f"Retcode:   {res_open.retcode if res_open else 'None'}")
                                print(f"Reason:    {retcode_desc}")
                                print(f"Signal:    {direction} at {entry_price}")
                                print(f"Returning to market scan...\n")

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
