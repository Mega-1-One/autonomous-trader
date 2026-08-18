import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter

def test_bounds():
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return

    import MetaTrader5 as mt5

    symbols = ["XAUUSDm", "EURUSDm", "GBPUSDm", "USTECm"]

    dates = [
        ("12 Months (2025-08-18)", datetime(2025, 8, 18, 0, 0, tzinfo=timezone.utc)),
        ("6 Months (2026-02-18)", datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc)),
        ("1 Month (2026-07-18)", datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)),
        ("8 Days (2026-08-10)", datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc))
    ]

    print("\n==================================================")
    print(" MT5 SERVER HISTORICAL DATA BOUNDS QUERY")
    print("==================================================")

    for sym in symbols:
        print(f"\nSymbol: {sym}")
        for label, dt in dates:
            rates = mt5.copy_rates_from(sym, mt5.TIMEFRAME_H1, dt, 10)
            ticks = mt5.copy_ticks_from(sym, dt, 10, mt5.COPY_TICKS_ALL)
            rates_ok = "AVAILABLE" if rates is not None and len(rates) > 0 else "UNAVAILABLE"
            ticks_ok = "AVAILABLE" if ticks is not None and len(ticks) > 0 else "UNAVAILABLE"
            print(f"  [{label}] H1 Rates: {rates_ok} | Ticks: {ticks_ok}")

    adapter.disconnect()

if __name__ == "__main__":
    test_bounds()
