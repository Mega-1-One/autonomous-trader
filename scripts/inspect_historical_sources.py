import sys
import os
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter

def inspect_sources():
    print("==================================================")
    print(" HISTORICAL DATA SOURCE INSPECTION")
    print("==================================================")

    # 1. Local Filesystem Discovery
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    print(f"Checking local data directory: {data_dir}")

    csv_files = list(data_dir.rglob("*.csv")) + list(base_dir.rglob("*.csv"))
    parquet_files = list(data_dir.rglob("*.parquet")) + list(base_dir.rglob("*.parquet"))

    print(f"  -> Discovered local CSV files: {len(csv_files)}")
    print(f"  -> Discovered local Parquet files: {len(parquet_files)}")

    # 2. MT5 Provider Query
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return

    import MetaTrader5 as mt5

    symbols = ["XAUUSDm", "EURUSDm", "GBPUSDm", "USTECm"]

    # Test dates: 12 months ago (2025-08-18) vs 1 month ago (2026-07-18) vs 8 days ago (2026-08-10)
    now = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
    dates_to_test = [
        ("12 Months (2025-08-18)", datetime(2025, 8, 18, 0, 0, tzinfo=timezone.utc)),
        ("6 Months (2026-02-18)", datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc)),
        ("1 Month (2026-07-18)", datetime(2026, 7, 18, 0, 0, tzinfo=timezone.utc)),
        ("8 Days (2026-08-10)", datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc))
    ]

    for sym in symbols:
        print(f"\n--- Checking Symbol: {sym} ---")
        for label, from_date in dates_to_test:
            # Query 1: Rates (H1 Candles)
            rates = mt5.copy_rates_range(sym, mt5.TIMEFRAME_H1, from_date, now)
            h1_count = len(rates) if rates is not None else 0

            # Query 2: Ticks (first 1000 ticks from start date)
            ticks = mt5.copy_ticks_range(sym, from_date, datetime(from_date.year, from_date.month, min(28, from_date.day+2), tzinfo=timezone.utc), mt5.COPY_TICKS_ALL)
            tick_count = len(ticks) if ticks is not None else 0

            print(f"  [{label}] H1 Candles: {h1_count:,} | Raw Ticks Sample: {tick_count:,}")

    adapter.disconnect()

if __name__ == "__main__":
    inspect_sources()
