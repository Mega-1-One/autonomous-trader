import time
from datetime import datetime
from typing import List, Dict, Any

from app.core.safety import ensure_trading_allowed, account_trade_mode_from_mt5, SafetyViolation
from app.data.mt5_real import RealMT5Adapter
from app.scalper.mt5_orders import build_close_request, build_market_order, pip_scale_for

class MT5GridMartingaleScalper:
    """Dynamic Grid & Martingale Scalper Engine for MT5 (Basket Take Profit & Equity Guard)."""

    def __init__(
        self,
        symbol: str = "EURUSDm",
        base_volume: float = 0.01,
        grid_step_pips: float = 10.0,
        lot_multiplier: float = 1.5,
        max_grid_orders: int = 3,
        basket_profit_target_usd: float = 0.50,
        max_basket_loss_usd: float = 0.50,
        commission_per_lot: float = 7.0,
        max_drawdown_pct: float = 20.0
    ):
        self.symbol = symbol
        self.base_volume = base_volume
        self.grid_step_pips = grid_step_pips
        self.lot_multiplier = lot_multiplier
        self.max_grid_orders = max_grid_orders
        self.basket_profit_target_usd = basket_profit_target_usd
        self.max_basket_loss_usd = max_basket_loss_usd
        self.commission_per_lot = commission_per_lot
        self.max_drawdown_pct = max_drawdown_pct
        self.adapter = RealMT5Adapter()
        self.magic_number = 888999

    def initialize(self) -> bool:
        if not self.adapter.connect():
            print("[ERROR] Failed to connect MT5 adapter.")
            return False
        return True

    def run_grid_cycle(self, direction: str = "BUY", max_cycle_sec: int = 60) -> Dict[str, Any]:
        import MetaTrader5 as mt5

        acc = mt5.account_info()
        if not acc:
            print("[ERROR] Could not fetch account info.")
            return {"status": "ERROR"}

        start_balance = acc.balance
        pip_scale = pip_scale_for(self.symbol)
        is_buy = (direction == "BUY")

        print("\n==================================================")
        print(" GRID & MARTINGALE SCALPER CYCLE INITIALIZED")
        print("==================================================")
        print(f"MT5 Account:            {acc.login} ({acc.server})")
        print(f"Current Balance:        ${acc.balance:.2f} USD")
        print(f"Symbol:                 {self.symbol}")
        print(f"Base Volume:            {self.base_volume} lot (Multiplier: {self.lot_multiplier}x)")
        print(f"Grid Step:              {self.grid_step_pips} pips | Max Orders: {self.max_grid_orders}")
        print(f"Basket Target Profit:   +${self.basket_profit_target_usd:.2f} USD (net of commission)")
        print(f"Basket Stop Loss:       -${self.max_basket_loss_usd:.2f} USD (close-all, no uncapped holds)")
        print(f"Max Equity Risk:        {self.max_drawdown_pct}% (Stop Guard)")
        print("==================================================\n")

        start_ts = time.time()
        grid_tickets = []

        # 1. Open Base Grid Order #1
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            print(f"[ERROR] Could not fetch tick for {self.symbol}")
            return {"status": "ERROR"}

        price = tick.ask if is_buy else tick.bid
        req_1 = build_market_order(
            mt5,
            symbol=self.symbol,
            order_type=mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
            volume=self.base_volume,
            price=price,
            deviation=10,
            magic=self.magic_number,
            comment="Grid Base #1",
        )

        try:
            ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
        except SafetyViolation as exc:
            print(f"[SAFETY GATE REFUSED] {exc}")
            return {"status": "REJECTED_BY_SAFETY_GATE", "reason": str(exc)}
        res_1 = mt5.order_send(req_1)
        if res_1 is None:
            print("[BROKER RESPONSE] order_send returned None (request failed)")
            return {"status": "ERROR"}
        if res_1.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[BROKER RESPONSE] Code: {res_1.retcode} | Comment: {res_1.comment}")
            if res_1.retcode == 10027:
                print("\n[ACTION REQUIRED] Click the GREEN 'Algo Trading' button in MT5 to enable grid orders.")
            return {"status": "REJECTED_BY_BROKER", "code": res_1.retcode}

        grid_tickets.append(res_1.order)
        print(f"[GRID #1 OPENED] Ticket #{res_1.order} | Vol: {self.base_volume} lot | Price: {res_1.price}")

        # 2. Grid Management Loop
        cycle_status = "IN_PROGRESS"
        while (time.time() - start_ts) < max_cycle_sec:
            # Check Account Equity Guard
            acc_curr = mt5.account_info()
            if acc_curr:
                equity_dd = ((start_balance - acc_curr.equity) / start_balance) * 100.0
                if equity_dd >= self.max_drawdown_pct:
                    print(f"\n[EQUITY STOP GUARD TRIGGERED ({equity_dd:.1f}% DD)] Closing all grid positions!")
                    self._close_all_grid_positions(grid_tickets)
                    cycle_status = "EQUITY_GUARD_CLOSED"
                    break

            # Calculate Basket Net Profit
            open_positions = mt5.positions_get(group=f"*{self.symbol}*")
            active_grid = [p for p in (open_positions or []) if p.magic == self.magic_number]

            if not active_grid or len(active_grid) == 0:
                print("\n[BASKET CLOSED] All grid positions closed in profit!")
                cycle_status = "TARGET_PROFIT_REACHED"
                break

            total_profit = sum((p.profit or 0.0) + (p.swap or 0.0) - (p.volume or 0.0) * self.commission_per_lot for p in active_grid)
            print(f"[{int(time.time() - start_ts)}s] Active Grid Orders: {len(active_grid)} | Basket Profit (net): ${total_profit:+.2f} USD")

            if total_profit >= self.basket_profit_target_usd:
                print(f"\n[BASKET TARGET REACHED (+${total_profit:.2f})] Closing all grid orders in profit!")
                self._close_all_grid_positions(grid_tickets)
                cycle_status = "TARGET_PROFIT_REACHED"
                break

            if total_profit <= -self.max_basket_loss_usd:
                print(f"\n[BASKET STOP LOSS ({total_profit:+.2f})] Closing all grid orders to cap the loss!")
                self._close_all_grid_positions(grid_tickets)
                cycle_status = "BASKET_STOP_LOSS"
                break

            # Check Grid Step for Order Averaging
            if len(active_grid) < self.max_grid_orders:
                last_pos = active_grid[-1]
                curr_tick = mt5.symbol_info_tick(self.symbol)
                curr_price = curr_tick.ask if is_buy else curr_tick.bid
                dist_pips = abs(curr_price - last_pos.price_open) / pip_scale

                is_adverse = (curr_price < last_pos.price_open) if is_buy else (curr_price > last_pos.price_open)
                if is_adverse and dist_pips >= self.grid_step_pips:
                    next_vol = round(self.base_volume * (self.lot_multiplier ** len(active_grid)), 2)
                    print(f"\n[GRID STEP {len(active_grid)+1} TRIGGERED ({dist_pips:.1f} pips adverse)] Opening Martingale Order Vol: {next_vol} lot...")
                    avg_req = build_market_order(
                        mt5,
                        symbol=self.symbol,
                        order_type=mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                        volume=next_vol,
                        price=curr_price,
                        deviation=10,
                        magic=self.magic_number,
                        comment=f"Grid Step #{len(active_grid)+1}",
                    )
                    try:
                        ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
                    except SafetyViolation as exc:
                        print(f"[SAFETY GATE REFUSED] {exc}")
                        self._close_all_grid_positions(grid_tickets)
                        cycle_status = "SAFETY_GATE_STOP"
                        break
                    avg_res = mt5.order_send(avg_req)
                    if avg_res is None:
                        print("[BROKER RESPONSE] order_send returned None (request failed)")
                    elif avg_res.retcode == mt5.TRADE_RETCODE_DONE:
                        grid_tickets.append(avg_res.order)
                        print(f"[GRID #{len(active_grid)+1} OPENED] Ticket #{avg_res.order} at {avg_res.price}")

            time.sleep(1.0)

        # Autoclose grid at end of cycle if still open
        self._close_all_grid_positions(grid_tickets)

        acc_end = mt5.account_info()
        print(f"\nFinal Account Balance: ${acc_end.balance:.2f} USD")
        self.adapter.disconnect()

        return {"status": cycle_status, "final_balance": acc_end.balance}

    def _close_all_grid_positions(self, tickets: List[int]):
        import MetaTrader5 as mt5
        open_positions = mt5.positions_get(group=f"*{self.symbol}*")
        if not open_positions:
            return

        for pos in open_positions:
            if pos.magic == self.magic_number:
                close_price = mt5.symbol_info_tick(self.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(self.symbol).ask
                req = build_close_request(
                    mt5,
                    symbol=self.symbol,
                    volume=pos.volume,
                    close_type=mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                    position_ticket=pos.ticket,
                    price=close_price,
                    deviation=10,
                    magic=self.magic_number,
                    comment="Grid Basket Close",
                )
                try:
                    ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
                except SafetyViolation as exc:
                    print(f"[SAFETY GATE REFUSED] {exc}")
                    return
                res = mt5.order_send(req)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"  Closed Grid Ticket #{pos.ticket} at {res.price}")
