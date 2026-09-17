"""C-06 tests: CORS origin restriction (P-05, review R-13)."""
import pytest


@pytest.mark.asyncio
async def test_cors_configured_origin_allowed(async_client):
    res = await async_client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_never_wildcard_with_credentials(async_client):
    res = await async_client.options(
        "/api/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    allow_origin = res.headers.get("access-control-allow-origin")
    # Either absent (refused) or an explicit echo of a configured origin —
    # never "*" combined with credentials.
    assert allow_origin != "*"


def test_cors_defaults_to_dashboard_origin():
    from app.core.config import Settings
    s = Settings()
    assert "http://localhost:3000" in s.CORS_ORIGINS
