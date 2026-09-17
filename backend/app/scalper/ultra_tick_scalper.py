import time
from datetime import datetime, timezone

from app.core.safety import ensure_trading_allowed, account_trade_mode_from_mt5, SafetyViolation
from app.data.mt5_real import RealMT5Adapter
from app.scalper.mt5_orders import build_close_request, build_market_order, pip_scale_for

class UltraTickScalperEngine:
    """Ultra-Aggressive High-Frequency Tick Scalper Engine (Instant Tick Execution & Continuous Re-entry)."""

    def __init__(self, symbol: str = "EURUSDm", volume: float = 0.01, sl_pips: float = 3.0, tp_pips: float = 5.0):
        self.symbol = symbol
        self.volume = volume
        self.sl_pips = sl_pips
        self.tp_pips = tp_pips
        self.adapter = RealMT5Adapter()
        self.magic_number = 999333

    def initialize(self) -> bool:
        if not self.adapter.connect():
            print("[ERROR] Failed to connect MT5 adapter.")
            return False
        return True

    def run_ultra_scalping_session(self, total_scalps_to_execute: int = 3):
        import MetaTrader5 as mt5

        acc = mt5.account_info()
        if not acc:
            print("[ERROR] Could not fetch account info.")
            return

        pip_scale = pip_scale_for(self.symbol)

        print("\n==================================================")
        print(" ULTRA-AGGRESSIVE TICK SCALPER ENGINE STARTED")
        print("==================================================")
        print(f"MT5 Account:      {acc.login} ({acc.server})")
        print(f"Current Balance:  ${acc.balance:.2f} USD")
        print(f"Scalp Symbol:     {self.symbol}")
        print(f"Micro Volume:     {self.volume} lot")
        print(f"Ultra SL / TP:    {self.sl_pips} pips SL / {self.tp_pips} pips TP")
        print(f"Target Scalps:    {total_scalps_to_execute} consecutive scalps")
        print("==================================================\n")

        completed_scalps = 0

        while completed_scalps < total_scalps_to_execute:
            # Check open positions
            open_pos = mt5.positions_get(group=f"*{self.symbol}*")
            active = [p for p in (open_pos or []) if p.magic == self.magic_number]

            if not active or len(active) == 0:
                tick = mt5.symbol_info_tick(self.symbol)
                if not tick:
                    time.sleep(0.5)
                    continue

                # Alternating direction or tick momentum
                direction = "BUY" if (completed_scalps % 2 == 0) else "SELL"
                is_buy = (direction == "BUY")

                price = tick.ask if is_buy else tick.bid
                sl = round(price - (self.sl_pips * pip_scale), 5 if "EUR" in self.symbol else 3) if is_buy else round(price + (self.sl_pips * pip_scale), 5 if "EUR" in self.symbol else 3)
                tp = round(price + (self.tp_pips * pip_scale), 5 if "EUR" in self.symbol else 3) if is_buy else round(price - (self.tp_pips * pip_scale), 5 if "EUR" in self.symbol else 3)

                req = build_market_order(
                    mt5,
                    symbol=self.symbol,
                    order_type=mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
                    volume=self.volume,
                    price=price,
                    sl=sl,
                    tp=tp,
                    deviation=10,
                    magic=self.magic_number,
                    comment=f"UltraScalp #{completed_scalps+1}",
                )

                print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Triggering Instant Scalp #{completed_scalps+1} ({direction})...")
                try:
                    ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5())
                except SafetyViolation as exc:
                    print(f"[SAFETY GATE REFUSED] {exc}")
                    break
                res = mt5.order_send(req)

                if res is None:
                    print("  [ERROR] order_send returned None (request failed)")
                    time.sleep(2.0)
                    continue
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"  [SCALP OPENED] Ticket #{res.order} at {res.price} (SL: {sl}, TP: {tp})")
                    ticket = res.order
                    start_pos_time = time.time()

                    # Monitor until SL/TP or 15s max horizon
                    while (time.time() - start_pos_time) < 15.0:
                        pos_list = mt5.positions_get(ticket=ticket)
                        if not pos_list or len(pos_list) == 0:
                            print(f"  [SCALP CLOSED] Ticket #{ticket} closed by SL/TP!")
                            break
                        time.sleep(0.5)

                    # Autoclose if still open after 15s
                    pos_list = mt5.positions_get(ticket=ticket)
                    if pos_list and len(pos_list) > 0:
                        pos = pos_list[0]
                        c_price = mt5.symbol_info_tick(self.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(self.symbol).ask
                        close_req = build_close_request(
                            mt5,
                            symbol=self.symbol,
                            volume=pos.volume,
                            close_type=mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                            position_ticket=pos.ticket,
                            price=c_price,
                            deviation=10,
                            magic=self.magic_number,
                            comment="UltraScalp 15s Close",
                        )
                        try:
                            # Close/reduce intent: de-risking is never trapped by the sentinel.
                            ensure_trading_allowed("REAL", account_trade_mode=account_trade_mode_from_mt5(), intent="close")
                        except SafetyViolation as exc:
                            print(f"[SAFETY GATE REFUSED] {exc}")
                            break
                        c_res = mt5.order_send(close_req)
                        if c_res and c_res.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"  [SCALP 15s AUTOCLOSED] Closed ticket #{ticket} at {c_res.price}")

                    completed_scalps += 1
                    acc_now = mt5.account_info()
                    print(f"  Updated Account Balance: ${acc_now.balance:.2f} USD\n")
                    time.sleep(1.0)
                else:
                    print(f"  [ERROR] Broker Response: {res.comment if res else 'Failed'}")
                    time.sleep(2.0)

        self.adapter.disconnect()
        print(f"[SUCCESS] Ultra-Aggressive Scalping Session Complete ({completed_scalps} scalps executed).")
