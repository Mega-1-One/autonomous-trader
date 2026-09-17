import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.core.config import settings
from app.core.database import get_db_session
from app.models.base import Base
from app.data.mt5_mock import MockMT5Adapter

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(autouse=True)
def isolated_state_dir(tmp_path):
    """Per-test isolation of cross-process state and the shared app engine set.

    - Points the emergency-stop sentinel at a per-test directory (B-05/ADR-8)
      so a triggered stop cannot persist under backend/state/.
    - Re-asserts the canonical ``config.settings`` object before and after each
      test: several tests legitimately replace it wholesale (``mode_env`` /
      ``_fresh_settings``), and a test that forgets to restore would otherwise
      leak its ``STATE_DIR`` (and any sentinel file there) into every later
      test, making the suite order-dependent.
    - Drops lazily-built API engine state between tests so each API test starts
      from a clean ``AppState`` (the re-review's "global app.state" risk).
    """
    import app.core.config as config_module
    from app.main import app as _app

    engine_attrs = ("adapter", "market_service", "risk_engine",
                    "execution_engine", "strategy_engine")
    old_state_dir = settings.STATE_DIR

    def _clear_engines():
        for attr in engine_attrs:
            if hasattr(_app.state, attr):
                delattr(_app.state, attr)

    config_module.settings = settings
    settings.STATE_DIR = tmp_path / "state"
    _clear_engines()
    yield
    _clear_engines()
    _app.dependency_overrides.clear()
    config_module.settings = settings
    settings.STATE_DIR = old_state_dir

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def async_db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(async_db_engine):
    session_factory = async_sessionmaker(async_db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

@pytest_asyncio.fixture(scope="function")
async def async_client(db_session):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def mock_mt5():
    adapter = MockMT5Adapter()
    adapter.connect()
    return adapter
