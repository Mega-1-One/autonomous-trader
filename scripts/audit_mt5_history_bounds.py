import sys
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.mt5_real import RealMT5Adapter

def audit_history_bounds():
    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return

    import MetaTrader5 as mt5

    # Check broker symbol mappings
    symbols = [
        ("XAUUSD", "XAUUSDm"),
        ("EURUSD", "EURUSDm"),
        ("GBPUSD", "GBPUSDm"),
        ("NAS100", "USTECm")
    ]

    report = {}

    print("\n==================================================")
    print(" PHASE 27.1 HISTORICAL COVERAGE COMPLETION AUDIT")
    print("==================================================")

    for canonical, sym in symbols:
        # 1. H1 Candle History Depth
        rates_h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 50000)
        if rates_h1 is None or len(rates_h1) == 0:
            # Fallback to canonical symbol name
            rates_h1 = mt5.copy_rates_from_pos(canonical, mt5.TIMEFRAME_H1, 0, 50000)
            if rates_h1 is not None and len(rates_h1) > 0:
                sym = canonical

        h1_bars = len(rates_h1) if rates_h1 is not None else 0

        # 2. Daily Candle History Depth
        rates_d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 5000)
        d1_bars = len(rates_d1) if rates_d1 is not None else 0

        oldest_dt = None
        newest_dt = None
        days_coverage = 0

        if rates_h1 is not None and len(rates_h1) > 0:
            oldest_ts = float(rates_h1[0][0])
            newest_ts = float(rates_h1[-1][0])
            oldest_dt = datetime.fromtimestamp(oldest_ts, tz=timezone.utc)
            newest_dt = datetime.fromtimestamp(newest_ts, tz=timezone.utc)
            days_coverage = (newest_dt - oldest_dt).days

        # Monthly breakdown
        monthly_table = {}
        if rates_h1 is not None and len(rates_h1) > 0:
            for r in rates_h1:
                dt_r = datetime.fromtimestamp(float(r[0]), tz=timezone.utc)
                m_key = dt_r.strftime("%Y-%m")
                monthly_table[m_key] = monthly_table.get(m_key, 0) + 1

        symbol_report = {
            "broker_symbol": sym,
            "h1_candle_count": h1_bars,
            "d1_candle_count": d1_bars,
            "oldest_timestamp_date": oldest_dt.strftime("%Y-%m-%d") if oldest_dt else "N/A",
            "newest_timestamp_date": newest_dt.strftime("%Y-%m-%d") if newest_dt else "N/A",
            "coverage_calendar_days": days_coverage,
            "coverage_months": round(days_coverage / 30.4, 1),
            "monthly_h1_candle_breakdown": monthly_table,
            "sufficient_for_12_months": (days_coverage >= 365)
        }

        report[canonical] = symbol_report

        print(f"\n--- Symbol: {canonical} ({sym}) ---")
        print(f"  Oldest Date: {symbol_report['oldest_timestamp_date']} | Newest Date: {symbol_report['newest_timestamp_date']}")
        print(f"  Calendar Days: {days_coverage} days ({symbol_report['coverage_months']} months)")
        print(f"  H1 Bars: {h1_bars:,} | D1 Bars: {d1_bars:,}")
        print(f"  Sufficient for >=12 Months: {symbol_report['sufficient_for_12_months']}")

    adapter.disconnect()

    out_file = Path(__file__).resolve().parent / "phase27_1_coverage_report.json"
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n[SUCCESS] Phase 27.1 Coverage Report saved to {out_file}")

if __name__ == "__main__":
    audit_history_bounds()
