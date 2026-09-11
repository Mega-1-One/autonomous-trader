# Autonomous Trading Bot

A production-grade, deterministic algorithmic trading system connecting to MetaTrader 5 (MT5). Features an ICT/SMC-inspired strategy engine, quantitative risk engine, real-time web dashboard, paper trading, and deterministic backtesting.

> [!WARNING]
> Live trading is disabled by default (`EXECUTION_MODE=PAPER`). Live execution requires explicit safety configuration (`ENABLE_LIVE_TRADING=true` AND `LIVE_TRADING_CONFIRMATION=true`).

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
