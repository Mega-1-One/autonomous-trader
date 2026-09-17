# Autonomous Trading Bot

A production-grade, deterministic algorithmic trading system connecting to MetaTrader 5 (MT5). Features an ICT/SMC-inspired strategy engine, quantitative risk engine, real-time web dashboard, paper trading, and deterministic backtesting.

> [!WARNING]
> Live trading is disabled by default (`EXECUTION_MODE=PAPER`). Live execution requires explicit safety configuration (`ENABLE_LIVE_TRADING=true` AND `LIVE_TRADING_CONFIRMATION=true`).
>
> Mutating API endpoints (order submission, close-all/close-position, emergency-stop) require a bearer token **only** when `APP_ENV=production` **and** `AUTOMATION_API_TOKEN` is set (`Authorization: Bearer <token>`; the dashboard sends it via `NEXT_PUBLIC_API_TOKEN`). Production deployments without the token configured must front the API with a reverse proxy or accept the exposure in writing.
>
> Optional risk guard (D-05, off by default): `risk_rules.reject_when_clamped_over_risk_multiple` (default `0` = disabled, current behavior). When set > 0, position sizing that would clamp *up* to the broker minimum lot is rejected if it risks more than that multiple of the per-trade risk. Enabling changes live sizing on small accounts — requires explicit owner sign-off.

## Architecture

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy (Async), Pydantic v2, Pytest, MetaTrader5
- **Frontend**: Next.js, React, TypeScript, Tailwind CSS
- **Database**: PostgreSQL with AsyncPG & Alembic migrations
- **Infrastructure**: Docker & Docker Compose

## Quick Start (Local Development)

```bash
# 1. Install backend dependencies
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Run backend test suite
pytest tests/ -v

# 3. Run FastAPI development server
uvicorn app.main:app --reload --port 8000
```

## Database

Tables are created automatically at startup via `Base.metadata.create_all`
(SQLite by default, Postgres via `DATABASE_URL`). Alembic (`database/`) is
optional scaffolding for future schema changes: it reads the database URL
from the `DATABASE_URL` environment variable and stores no credentials.
