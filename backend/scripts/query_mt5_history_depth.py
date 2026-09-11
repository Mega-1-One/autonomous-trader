import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter

def query_depth():
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return

    import MetaTrader5 as mt5

    symbols = ["XAUUSDm", "EURUSDm", "GBPUSDm", "USTECm"]
    now = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)

    print("\n==================================================")
    print(" MT5 HISTORICAL DATA DEPTH AUDIT")
    print("==================================================")

    for sym in symbols:
        # Check oldest 1H candle available from MT5 server
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 10000)
        if rates is not None and len(rates) > 0:
            oldest_ts = float(rates[0][0])
            newest_ts = float(rates[-1][0])
            oldest_dt = datetime.fromtimestamp(oldest_ts, tz=timezone.utc)
            newest_dt = datetime.fromtimestamp(newest_ts, tz=timezone.utc)
            days = (newest_dt - oldest_dt).days
            print(f"  [{sym}] 1H Candle History: {len(rates):,} bars | Range: {oldest_dt.strftime('%Y-%m-%d')} to {newest_dt.strftime('%Y-%m-%d')} ({days} days)")
        else:
            print(f"  [{sym}] 1H Candle History: UNAVAILABLE")

        # Check tick history for last 30 days
        month_ago = now - timedelta(days=30)
        ticks = mt5.copy_ticks_range(sym, month_ago, month_ago + timedelta(days=1), mt5.COPY_TICKS_ALL)
        if ticks is not None and len(ticks) > 0:
            print(f"  [{sym}] 30-Day Ago Tick Sample: {len(ticks):,} ticks available on {month_ago.strftime('%Y-%m-%d')}")
        else:
            print(f"  [{sym}] 30-Day Ago Tick Sample: UNAVAILABLE (Exness demo trial limits tick history)")

    adapter.disconnect()

if __name__ == "__main__":
    query_depth()
