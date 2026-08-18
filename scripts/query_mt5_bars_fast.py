import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter

def query_fast():
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return

    import MetaTrader5 as mt5

    symbols = ["XAUUSDm", "EURUSDm", "GBPUSDm", "USTECm"]

    print("\n==================================================")
    print(" MT5 FAST OHLC BAR HISTORY AUDIT")
    print("==================================================")

    for sym in symbols:
        # Check oldest H1 bar in MT5 cache
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50000)
        if rates is not None and len(rates) > 0:
            oldest_ts = float(rates[0][0])
            newest_ts = float(rates[-1][0])
            oldest_dt = datetime.fromtimestamp(oldest_ts, tz=timezone.utc)
            newest_dt = datetime.fromtimestamp(newest_ts, tz=timezone.utc)
            days = (newest_dt - oldest_dt).days
            print(f"  [{sym}] 1H Bar History: {len(rates):,} bars | Range: {oldest_dt.strftime('%Y-%m-%d')} to {newest_dt.strftime('%Y-%m-%d')} ({days} days / {round(days/30.0, 1)} months)")
        else:
            print(f"  [{sym}] 1H Bar History: UNAVAILABLE")

    adapter.disconnect()

if __name__ == "__main__":
    query_fast()
