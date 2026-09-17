"""Capture baseline API response samples for every enumerated route.

Run from backend/: python ../docs/baseline/capture_api.py
Writes one JSON file per route into docs/baseline/.
Mock-adapter driven only; real-broker behavior is not captured.
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.config import settings

OUT_DIR = os.path.join(os.path.dirname(__file__))
PARAM_SAMPLES = {
    "symbol": "XAUUSD",
    "timeframe": "M5",
    "count": 50,
    "position_id": None,  # discovered below
}
POST_BODIES = {
    "/api/risk/evaluate": {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry_price": 2400.0,
        "stop_loss_pips": 3.0,
        "take_profit_pips": 5.0,
        "confidence": 0.8,
    },
    "/api/system/emergency-stop": {"reason": "baseline capture"},
    "/api/system/reset-emergency-stop": {},
    "/api/backtest/run": {
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "candle_count": 200,
        "initial_balance": 10000,
    },
    "/api/backtest/monte-carlo": {
        "symbol": "XAUUSD",
        "timeframe": "M5",
        "candle_count": 200,
        "initial_balance": 10000,
    },
    "/api/execution/orders": {
        "symbol": "XAUUSD",
        # N2-H2: "BUY" was never a valid API direction (old code silently
        # sold while recording "BUY"); valid values are LONG/SHORT.
        "direction": "LONG",
        "volume": 0.01,
        "entry_price": 2400.0,
        "stop_loss": 2399.7,
        "take_profit": 2400.5,
        "comment": "baseline",
    },
}


def path_params(path: str):
    return re.findall(r"\{(\w+)\}", path)


async def main():
    os.environ.setdefault("EXECUTION_MODE", "PAPER")
    transport = ASGITransport(app=app)
    manifest = []
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Enumerate routes from the app's own OpenAPI schema (FastAPI 0.141 exposes
        # routers as _IncludedRouter, so direct app.routes iteration is incomplete).
        schema = (await client.get("/openapi.json")).json()
        route_specs = []
        for path, ops in schema["paths"].items():
            for method in ops:
                if method in ("head", "options"):
                    continue
                route_specs.append((method.upper(), path))
        # First pass: find a position id if any exist (paper engine starts with none)
        position_id = None
        for method, path in route_specs:
            if "{position_id}" in path:
                resp = await client.get("/api/execution/positions")
                data = resp.json()
                positions = data if isinstance(data, list) else data.get("positions", [])
                if positions:
                    position_id = positions[0].get("id")
        for method, path in route_specs:
            sample = {k: PARAM_SAMPLES.get(k, "XAUUSD") for k in path_params(path)}
            if "{position_id}" in path:
                sample["position_id"] = position_id
            params = None
            json_body = None
            if method == "GET":
                params = sample
            else:
                json_body = POST_BODIES.get(path)
            try:
                resp = await client.request(method, path, params=params, json=json_body)
                body = {"status": resp.status_code, "json": _safe_json(resp)}
            except Exception as exc:  # noqa: BLE001 - capture is read-only diagnostics
                body = {"error": repr(exc)}
            fname = _fname(path, method)
            with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as f:
                json.dump({"method": method, "path": path, "result": body}, f, indent=2, default=str, sort_keys=True)
            manifest.append(f"{method} {path} -> {fname}")
    with open(os.path.join(OUT_DIR, "api_manifest.txt"), "w") as f:
        f.write("\n".join(manifest))
    print(f"captured {len(manifest)} endpoint samples")


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]


def _fname(path: str, method: str) -> str:
    slug = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"api_{method.lower()}_{slug}.json"


if __name__ == "__main__":
    asyncio.run(main())
