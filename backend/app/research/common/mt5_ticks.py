"""Shared real-tick ingestion helper (P-08/C-04).

Single implementation of the tick-fetch previously copy-pasted across the
phase benchmark scripts. Defaults reproduce the historical behavior exactly:
the 2026-08-10..2026-08-18 UTC window with stride sampling to ``max_ticks``
samples per symbol.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional

DEFAULT_TICK_WINDOW_START = datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)
DEFAULT_TICK_WINDOW_END = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)


def fetch_real_ticks(
    symbol_map: Dict[str, str],
    max_ticks: int = 25000,
    utc_from: Optional[datetime] = None,
    utc_to: Optional[datetime] = None,
) -> Dict[str, List[dict]]:
    """Fetches real MT5 ticks per canonical symbol (Windows/MT5 required)."""
    from app.data.mt5_real import RealMT5Adapter

    utc_from = utc_from or DEFAULT_TICK_WINDOW_START
    utc_to = utc_to or DEFAULT_TICK_WINDOW_END

    adapter = RealMT5Adapter()
    if not adapter.connect():
        print("[ERROR] Failed to connect to MT5 terminal")
        return {}

    import MetaTrader5 as mt5

    dataset: Dict[str, List[dict]] = {}

    for canonical, broker_symbol in symbol_map.items():
        print(f"Ingesting real ticks for {canonical} ({broker_symbol})...")
        raw_ticks = mt5.copy_ticks_range(broker_symbol, utc_from, utc_to, mt5.COPY_TICKS_ALL)
        if raw_ticks is not None and len(raw_ticks) > 0:
            step = max(1, len(raw_ticks) // max_ticks)
            sampled = raw_ticks[::step]
            parsed = []
            for t in sampled:
                parsed.append({
                    "symbol": canonical,
                    "bid": float(t[1]),
                    "ask": float(t[2]),
                    "last": float(t[3]) if len(t) > 3 and t[3] > 0 else float(t[1]),
                    "timestamp": float(t[0]),
                    "volume": int(t[4]) if len(t) > 4 else 1,
                })
            dataset[canonical] = parsed
            print(f"  -> {canonical}: Loaded {len(parsed):,} real Exness ticks.")

    adapter.disconnect()
    return dataset
