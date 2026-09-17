"""E-03: API contract diff vs docs/baseline (volatile fields normalized).

Volatile (expected to differ run-to-run): timestamps, uuids/signal/order/
position IDs, broker tickets, latency, equity-curve timestamps.
Permitted real diffs: monte-carlo simulation content (C-02), failure-path
status codes (C-01), CORS/security headers (C-06/D-01), position price
values (C-01/N-06).

M-5: exits non-zero on any unexpected diff and runs in CI.
NEW-03: instead of exempting whole endpoints, the mock wall clock is frozen
(see FROZEN_NOW), so liquidity/patterns values compare fully. Only execution
timestamps/IDs/latency are normalized away.
"""
import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "baseline")))

from capture_api import PARAM_SAMPLES, POST_BODIES, path_params, _fname  # noqa: E402

BASELINE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "baseline"))

UUID_RE = re.compile(r"(SIG|ORD|POS|BT)_[0-9A-F]{4,}")
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\"']*")


def normalize(obj):
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()
                if k not in ("latency_ms", "timestamp", "entry_time", "exit_time")}
    if isinstance(obj, list):
        return [normalize(v) for v in obj]
    if isinstance(obj, str):
        if "Previous Day" in obj:
            # Calendar-day label derived from wall-clock mock candles
            return re.sub(r"\(\d{4}-\d{2}-\d{2}\)", "(<DAY>)", obj)
        obj = UUID_RE.sub("<ID>", obj)
        obj = TS_RE.sub("<TS>", obj)
        return obj
    if isinstance(obj, float):
        return round(obj, 4)
    return obj


# NEW-03: frozen instant for the mock wall clock. Mock candle/tick
# timestamps (day/session buckets in liquidity/patterns/signals) derive from
# `datetime.now(timezone.utc)` in app.data.mt5_mock and app.strategy.sessions;
# freezing both makes those endpoints fully deterministic, so values (not
# just keys) are compared. Chosen near the A-02 capture time so the frozen
# samples below reproduce the original session/day context.
FROZEN_NOW_ISO = "2026-09-16T21:42:25+00:00"


def _freeze_mock_clock():
    """Patch module-level `datetime` to a fixed instant wherever mock
    wall-clock time feeds endpoint values: candle/tick generation
    (app.data.mt5_mock), session windows (app.strategy.sessions), and the
    staleness check (app.services.market_data)."""
    from datetime import datetime, timezone
    import app.data.mt5_mock as mock_module
    import app.strategy.sessions as sessions_module
    import app.services.market_data as market_data_module

    frozen = datetime.fromisoformat(FROZEN_NOW_ISO)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen if tz is None else frozen.astimezone(tz)

    mock_module.datetime = _FrozenDateTime
    sessions_module.datetime = _FrozenDateTime
    market_data_module.datetime = _FrozenDateTime


def main():
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    _freeze_mock_clock()

    async def run():
        transport = ASGITransport(app=app)
        diffs = []
        checked = 0
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            manifest = open(os.path.join(BASELINE_DIR, "api_manifest.txt")).read().splitlines()
            for entry in manifest:
                method, _, rest = entry.partition(" ")
                path, _, fname = rest.partition(" -> ")
                if "docs" in path or "openapi" in path or "redoc" in path:
                    continue
                with open(os.path.join(BASELINE_DIR, fname), encoding="utf-8") as f:
                    baseline = json.load(f)["result"]
                sample = {k: PARAM_SAMPLES.get(k, "XAUUSD") for k in path_params(path)}
                if "{position_id}" in path:
                    # positions are ephemeral; use shape check with None
                    sample["position_id"] = None
                params = sample if method == "GET" else None
                json_body = POST_BODIES.get(path) if method != "GET" else None
                try:
                    resp = await client.request(method, path, params=params, json=json_body)
                    current = {"status": resp.status_code, "json": resp.json()}
                except Exception as exc:  # noqa: BLE001
                    current = {"error": repr(exc)}
                checked += 1
                base_norm = normalize(copy.deepcopy(baseline))
                cur_norm = normalize(copy.deepcopy(current))
                # Monte Carlo content is a permitted diff (C-02): keys only.
                if "monte-carlo" in path:
                    if set((cur_norm.get("json") or {}).keys()) != set((base_norm.get("json") or {}).keys()):
                        diffs.append((entry, "simulation keys differ"))
                    continue
                if base_norm != cur_norm:
                    diffs.append((entry, json.dumps({"baseline": base_norm, "current": cur_norm})[:800]))
        print(f"checked={checked} diffs={len(diffs)}")
        for entry, detail in diffs:
            print("DIFF:", entry)
            print("  ", detail[:400])
        return diffs

    diffs = asyncio.run(run())
    sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
