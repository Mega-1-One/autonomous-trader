<div align="center">

# Autonomous Trader

**A deterministic, research-driven algorithmic trading platform for MetaTrader 5**

[![CI](https://github.com/Mega-1-One/autonomous-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/Mega-1-One/autonomous-trader/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An ICT/SMC-inspired strategy engine, quantitative risk engine, real-time tick scalpers,
paper-trading simulator, deterministic backtesting suite, and a live web dashboard —
backed by a 27-phase quantitative research program.

</div>

---

> [!WARNING]
> **Live trading is disabled by default.** The system boots in `EXECUTION_MODE=PAPER`.
> Enabling real-money execution requires *both* `ENABLE_LIVE_TRADING=true` **and**
> `LIVE_TRADING_CONFIRMATION=true`; otherwise the application refuses to start in `LIVE` mode.
> See [Safety Model](#-safety-model).
>
> Mutating API endpoints (order submission, close/close-all, emergency-stop/reset) require a
> bearer token **only** when `APP_ENV=production` **and** `AUTOMATION_API_TOKEN` is set
> (`Authorization: Bearer <token>`; the dashboard sends it via `NEXT_PUBLIC_API_TOKEN`).
> Without the token configured in production, front the API with a reverse proxy or accept
> the exposure in writing. CORS is restricted to `CORS_ORIGINS` (default `http://localhost:3000`).

> [!IMPORTANT]
> **Strategy edge is not yet validated.** The research program (Phases 15–41) found **no
> statistically significant, out-of-sample-robust trading edge** in the tested feature space.
> The infrastructure is production-grade; the *profitability* of the strategies is not proven.
> Treat this as an engineering and research platform, not a money machine.

---

## Table of Contents

- [Overview](#-overview)
- [Architecture](#-architecture)
- [Features](#-features)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Running the Trading Bots](#-running-the-trading-bots)
- [API Reference](#-api-reference)
- [Web Dashboard](#-web-dashboard)
- [Research Program](#-research-program)
- [Testing](#-testing)
- [Continuous Integration](#-continuous-integration)
- [Safety Model](#-safety-model)
- [Contributing](#-contributing)
- [Tech Stack](#-tech-stack)
- [License](#-license)
- [Disclaimer](#-disclaimer)

---

## Overview

Autonomous Trader is a full-stack algorithmic trading platform built around
MetaTrader 5 (MT5). It combines:

- **A strategy layer** — ICT/SMC market-structure analysis (liquidity sweeps, fair value
  gaps, order blocks, displacement, BOS/MSS) that produces entry signals with explicit
  stop-loss and take-profit levels.
- **A risk layer** — position sizing from account equity, risk/reward gating,
  spread/margin checks, emergency-stop and circuit-breaker controls.
- **An execution layer** — a broker-adapter abstraction with `Mock`, `Real` (MT5), and
  paper-trading implementations, plus an order/position lifecycle manager.
- **A research layer** — 27 phases of data pipeline, feature discovery, edge discovery,
  walk-forward validation, and forensic auditing, with machine-readable artifacts.
- **A presentation layer** — a Next.js dashboard for monitoring signals, positions, risk,
  and backtests.

The codebase is intentionally deterministic: data pipelines are hashed and manifests
locked, walk-forward splits are chronological, and live-trading safety is enforced at the
configuration layer rather than by convention.

---

## Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │              Next.js Dashboard               │
                    │   (React 18 · TypeScript · Tailwind CSS)     │
                    └───────────────────────┬──────────────────────┘
                                            │ HTTP / JSON (CORS)
                    ┌───────────────────────▼──────────────────────┐
                    │            FastAPI Application               │
                    │  api/ ─ market · structure · liquidity ·     │
                    │         strategy · risk · backtest ·         │
                    │         execution · health                   │
                    └───────┬───────────────┬───────────────┬──────┘
                            │               │               │
             ┌──────────────▼──┐   ┌────────▼────────┐   ┌──▼──────────────┐
             │ Strategy         │   │ Risk            │   │ Execution       │
             │ strategy/        │   │ risk/           │   │ execution/      │
             │  structure,      │   │  RiskEngine,    │   │  ExecutionEngine│
             │  liquidity, fvg, │   │  failure        │   │  paper sim,     │
             │  order_block,    │   │  recovery,      │   │  position mgmt  │
             │  sweeps,         │   │  circuit        │   │                 │
             │  sessions,       │   │  breakers       │   │                 │
             │  plugin/gate     │   │                 │   │                 │
             └──────────┬───────┘   └────────┬────────┘   └──┬──────────────┘
                        │                    │                │
             ┌──────────▼────────────────────▼────────────────▼──────────┐
             │              Data & Intelligence Layer                     │
             │  data/ (MT5 adapter: abstract / mock / real)               │
             │  intelligence/ (technical, structure, liquidity, cost, EV) │
             │  context/ · regime/ · fusion/ · information/ · services/   │
             └───────────────────────────┬────────────────────────────────┘
                                         │
             ┌───────────────────────────▼────────────────────────────────┐
             │                 Research & Backtest Layer                   │
             │  backtest/ (engine · metrics · monte_carlo · walk_forward)  │
             │  research/ (27 phases · data_pipeline · feature discovery)  │
             └───────────────────────────┬────────────────────────────────┘
                                         │
             ┌───────────────────────────▼────────────────────────────────┐
             │   Persistence: SQLAlchemy (async) → PostgreSQL / SQLite      │
             │   Migrations: Alembic (database/migrations)                 │
             └─────────────────────────────────────────────────────────────┘
```

### Layers

| Layer | Package | Responsibility |
|---|---|---|
| HTTP API | `backend/app/api/` | FastAPI routers and request/response schemas |
| Strategy | `backend/app/strategy/` | ICT/SMC engines + plugin interface & 6-stage quality gate |
| Risk | `backend/app/risk/` | Position sizing, RR gating, emergency stop, failure recovery |
| Execution | `backend/app/execution/` | Order submission, position lifecycle, paper simulation |
| Data | `backend/app/data/`, `services/` | MT5 adapter abstraction (mock/real), market data service |
| Intelligence | `backend/app/intelligence/` | Multi-factor analysis, cost/EV engines, Fusion 2.0 |
| Context | `backend/app/context/`, `regime/`, `fusion/` | Multi-timeframe bias, market regime, signal fusion |
| Information | `backend/app/information/` | Pluggable external data (calendar, futures volume, L2 book) |
| Scalping | `backend/app/scalper/` | Tick-level engines and standalone trading bots |
| Backtest | `backend/app/backtest/` | Deterministic backtests, metrics, Monte Carlo, walk-forward |
| Research | `backend/app/research/` | Phase engines, data pipeline, feature discovery |
| Persistence | `backend/app/models/`, `database/` | SQLAlchemy domain models and Alembic migrations |

---

## Features

### Strategy & analysis
- **Market structure engine** — swing detection, BOS (break of structure), MSS (market
  structure shift), trend-regime classification.
- **Liquidity engine** — PDH/PDL, session highs/lows, equal highs/lows, sweep detection.
- **ICT pattern engines** — fair value gaps (FVG) with mitigation tracking, order blocks,
  displacement, and liquidity sweeps.
- **Session filter** — London / New York trading windows (UTC), toggleable.
- **Plugin architecture** — `StrategyPlugin` ABC with a `UnifiedSignal` schema and a
  **6-stage quality gate**: Signal → Data Quality → Market State → Strategy Validation →
  Risk Validation → Execution Validation.

### Risk management
- Equity-based position sizing snapped to broker volume steps.
- Risk/Reward minimum enforcement (default `minimum_rr: 1.5`).
- Spread, margin, trade-count and daily-loss limit checks (each disabled when set to `0`).
- Global **emergency stop** and **daily risk lock**.
- **Phase 40 failure-recovery engine** — `NORMAL / SOFT_STOP / HARD_STOP / EMERGENCY_STOP`
  circuit-breaker state machine handling disconnects, stale ticks, spread explosions,
  crossed books, duplicate replay and process-restart recovery.

### Execution
- Broker-adapter abstraction: `AbstractMT5Adapter` → `MockMT5Adapter`, `RealMT5Adapter`.
- Idempotent order submission (duplicate order-ID blocking) and broker position sync.
- Paper-trading simulator and a real-time tick stream monitor.
- Position management: SL/TP touch detection, break-even, max-holding-time stops.
- Structured JSON order-audit logging with latency measurement.

### Backtesting & research
- Deterministic candle backtester with commission and slippage modelling.
- Tick-level backtester driven by the same position manager as live scalping.
- Monte Carlo simulation, walk-forward validation, and a full metrics suite
  (win rate, profit factor, expectancy, Sharpe, Sortino, max drawdown, streaks).
- 27-phase research program with locked datasets, hashed manifests, FDR
  multiple-testing correction, placebo tests, and machine-readable artifacts.

### Every trading bot
- `AutonomousScalperDaemon` — EMA-trend micro-scalper with SL/TP and max-hold.
- `GoldMultiPositionProfitScalper` — XAUUSD multi-position scalper with profit target,
  protective stop-loss, loss cap and max-hold; commission-aware close decisions.
- `MT5GridMartingaleScalper` — grid/martingale basket with profit target **and** a
  basket-level stop-loss.
- `UltraTickScalperEngine` — tight 3/5-pip tick scalper with forced time exit.
- `MT5DemoMicroScalper` — single demo micro-scalp executor.
- Manual override: `STOP` / `START` / `STATUS` / `TEST` commands during a live session.

### Dashboard
- Real-time health, positions, signals, risk and backtest views (see
  [Web Dashboard](#-web-dashboard)).

---

## Project Structure

```
autonomous-trader/
├── .github/workflows/ci.yml        # CI: pytest, ruff, contract diff, compose smoke, Next.js build
├── backend/                        # Python application root
│   ├── app/
│   │   ├── api/                    # FastAPI routers (9 routers, 19 endpoints)
│   │   ├── backtest/               # engine, metrics, monte_carlo, tick_backtest, walk_forward
│   │   ├── context/                # multi-timeframe bias, price location, setup classifier
│   │   ├── core/                   # config (Settings), async database, logging
│   │   ├── data/                   # MT5 adapter: interface / mock / real / adapter_factory
│   │   ├── execution/              # ExecutionEngine, models, paper simulation
│   │   ├── fusion/                 # signal fusion & conflict detection
│   │   ├── information/            # external data providers + pipeline
│   │   ├── intelligence/           # analyzers, cost/EV engines, fusion 2.0
│   │   ├── models/                 # SQLAlchemy base + 12 domain entities
│   │   ├── regime/                 # market-regime detection
│   │   ├── research/               # phase engines, data_pipeline, feature_discovery
│   │   ├── risk/                   # RiskEngine, Phase 40 failure recovery
│   │   ├── scalper/                # tick engines + standalone bots
│   │   ├── services/               # market data service
│   │   ├── strategy/               # ICT/SMC engines, plugin + SignalQualityGate
│   │   ├── swing/                  # multi-timeframe swing engine
│   │   ├── main.py                 # FastAPI application factory + lifespan
│   │   └── runner.py               # async autonomous trading loop
│   ├── data/                       # 60+ research artifacts (phase*.json/md/csv)
│   ├── scripts/                    # 40 scripts: entry-point runners + _bootstrap.py
│   ├── tests/                      # 76 test modules, 323 tests + conftest.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── PHASE_28–30_*_REPORT.md     # published research reports
├── config/
│   ├── risk.yaml                   # risk rules, stops/targets, position management
│   └── strategy.yaml               # timeframes, structure, liquidity, entries
├── database/
│   ├── alembic.ini
│   └── migrations/                 # env.py, script template, versions/
├── frontend/                       # Next.js 14 dashboard (App Router)
│   └── app/                        # layout + dashboard, strategy, risk, positions,
│                                   #   orders (signal log), backtest pages
├── .env.example                    # environment template
├── docker-compose.yml              # postgres + backend
└── LICENSE                         # MIT
```

---

## Quick Start

### Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.12+ | backend & research |
| Node.js | 20+ | frontend dashboard |
| PostgreSQL | 16 (optional) | defaults to in-memory SQLite when unset |
| MetaTrader 5 | — | **Windows only**, required only for real/demo MT5 execution |
| Docker | optional | for the Postgres/backend stack |

### 1. Clone & configure

```bash
git clone https://github.com/Mega-1-One/autonomous-trader.git
cd autonomous-trader
cp .env.example .env      # then edit values as needed (Windows: copy .env.example .env)
```

### 2. Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
# source venv/bin/activate

pip install -r requirements.txt

# Run the test suite (no MT5 required — uses the mock adapter)
pytest tests/ -v

# Start the API
uvicorn app.main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs> · Health: <http://localhost:8000/api/health>

> **MT5 execution only:** the `MetaTrader5` package is *not* in `requirements.txt`
> (it is Windows-only and needed solely for `RealMT5Adapter`). Install it on the trading
> machine with `pip install MetaTrader5`. The import is guarded, so the API, tests and
> backtests run anywhere without it. Set `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` and
> `MT5_PATH` in `.env`.

### 3. Frontend

```bash
cd frontend
npm ci
npm run dev            # http://localhost:3000
```

### 4. Docker stack (Postgres + Backend)

```bash
docker compose up --build
```

> The Docker backend starts with `EXECUTION_MODE=PAPER`,
> `ENABLE_LIVE_TRADING=false`, `LIVE_TRADING_CONFIRMATION=false`.

### 5. Database migrations (Alembic)

```bash
cd database
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

> In development, `app/main.py` also runs `Base.metadata.create_all` on startup, so the
> API works against SQLite with zero migration setup.

---

## Configuration

Configuration is split across three places: **environment variables** (`.env`),
**YAML domain configs** (`config/`), and **code defaults** (`app/core/config.py`).

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `EXECUTION_MODE` | `PAPER` | `BACKTEST` · `PAPER` · `DEMO` · `LIVE` |
| `ENABLE_LIVE_TRADING` | `false` | Must be `true` **and** confirmation `true` for `LIVE` |
| `LIVE_TRADING_CONFIRMATION` | `false` | Second key required to unlock live trading |
| `APP_NAME` / `APP_ENV` / `LOG_LEVEL` | `Autonomous Trader` / `development` / `INFO` | App metadata & logging |
| `DATABASE_URL` | `sqlite+aiosqlite:///:memory:` | Async SQLAlchemy URL |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed dashboard origins (no wildcard) |
| `AUTOMATION_API_TOKEN` | *(unset)* | When set **and** `APP_ENV=production`, mutating endpoints require `Authorization: Bearer <token>` |
| `NEXT_PUBLIC_API_TOKEN` | *(unset)* | Frontend build-time token sent by the dashboard (must match `AUTOMATION_API_TOKEN`) |
| `AUTOTRADER_STATE_DIR` | `<repo>/backend/state` | Directory for the cross-process emergency-stop sentinel; gitignored |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` / `MT5_PATH` | *(unset)* | MT5 credentials (live/demo only) |
| `PORT` / `FRONTEND_PORT` | `8000` / `3000` | Service ports |

### `config/risk.yaml`

```yaml
risk_rules:
  risk_per_trade_percent: 0.1
  maximum_daily_loss_percent: 0     # 0 = disabled
  maximum_trades_per_day: 0         # 0 = disabled
  maximum_open_positions: 0         # 0 = disabled
  maximum_spread_pips: 0            # 0 = disabled
  minimum_rr: 1.5
  # Optional min-lot over-risk guard (default 0 = disabled). When > 0, sizing
  # clamped up to the broker minimum lot is rejected if it exceeds this multiple
  # of the per-trade risk; enabling changes live sizing on small accounts.
  reject_when_clamped_over_risk_multiple: 0
stops_and_targets:
  take_profit_mode: FIXED_PIPS
  take_profit_pips: 5.0
  stop_loss_pips: 3.0
position_management:
  break_even_enabled: false
  trailing_stop_enabled: false
  partial_tp_enabled: false
  max_holding_time_seconds: 30
```

### `config/strategy.yaml`

```yaml
mode: "SCALP"
timeframes: { htf: M5, ltf: M1 }
entry:
  minimum_rr: 1.5
  require_liquidity_sweep: true
  take_profit_pips: 5.0
  stop_loss_pips: 3.0
# plus market_structure, liquidity, displacement, fvg, order_block, sessions blocks
```

> Limits set to `0` are treated as **disabled** — the engine will not block on them.
> `symbol_mappings` in `risk.yaml` maps canonical symbols (e.g. `XAUUSD`) to broker
> aliases (`XAUUSDm`, `GOLD`, `GOLDm`).

---

## Running the Trading Bots

All runners live in `backend/scripts/` and can be invoked directly (they self-inject
`site-packages`). Run from the `backend/` directory.

```bash
# Autonomous EMA micro-scalper (EURUSDm by default)
python scripts/run_autonomous_scalper.py 300      # duration in seconds (0 = forever)

# Gold multi-position profit scalper (XAUUSDm)
python scripts/run_gold_multi_scalper.py 300

# Grid & martingale basket bot
python scripts/run_grid_martingale_bot.py EURUSDm BUY

# Ultra tick scalper
python scripts/run_ultra_scalper.py

# Paper simulation (writes backend/data/paper_simulation_summary.json)
python scripts/run_paper_simulation.py

# One-shot demo scalp / demo order
python scripts/run_demo_scalper.py
python scripts/run_demo_trader.py
```

During a live gold session the bot accepts terminal commands:
`STOP` (disable new entries), `START` (resume), `STATUS` (print metrics), `TEST` (one test order).

> **Windows + MT5 required** for any `RealMT5Adapter` runner. Ensure "Algo Trading" is
> enabled in the MT5 toolbar, or orders return retcode `10027`.

---

## API Reference

Base URL: `http://localhost:8000` · Interactive docs: `/docs`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Service metadata (name, version, docs link, health) |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/market/symbols` | Available symbols |
| `GET` | `/api/market/candles` | OHLC candles (`symbol`, `timeframe`, `count`) |
| `GET` | `/api/market/status` | Market open/closed status |
| `GET` | `/api/structure/analyze` | Market-structure analysis (trend, swings, BOS/MSS) |
| `GET` | `/api/liquidity/levels` | Liquidity levels (PDH/PDL, sessions, equal highs/lows) |
| `GET` | `/api/strategy/patterns` | Detected ICT patterns (FVG, sweeps, order blocks) |
| `GET` | `/api/strategy/signals` | Current strategy signal + reasons |
| `GET` | `/api/risk/status` | Risk parameters & lock status |
| `POST` | `/api/risk/evaluate` | Evaluate a candidate trade against risk rules |
| `POST` | `/api/system/emergency-stop` | Trigger global emergency stop |
| `POST` | `/api/system/reset-emergency-stop` | Reset emergency stop |
| `POST` | `/api/backtest/run` | Run deterministic backtest |
| `POST` | `/api/backtest/monte-carlo` | Run Monte Carlo simulation |
| `GET` | `/api/execution/positions` | List open positions |
| `POST` | `/api/execution/orders` | Submit an order |
| `POST` | `/api/execution/positions/{position_id}/close` | Close one position |
| `POST` | `/api/execution/close-all` | Emergency close all positions |

```bash
curl http://localhost:8000/api/health
curl "http://localhost:8000/api/strategy/signals?symbol=XAUUSD"
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","timeframe":"M5","candle_count":500,"initial_balance":10000}'
```

---

## Web Dashboard

The Next.js dashboard (`frontend/`, port `3000`) mirrors the API. Every page is a
self-contained client component with a dark theme and a header badge that reflects
`/api/health` (e.g. **PAPER MODE** / **LIVE MODE**, plus **· SIMULATED** when a
`DEMO`/`LIVE` mode is running on the mock adapter).

| Route | Page | Data source |
|---|---|---|
| `/` | Dashboard — service health, DB, broker adapter, active strategy | `/api/health` (5s poll) |
| `/strategy` | Pattern monitor — trend regime, displacement, FVGs, sweeps, order blocks | `/api/strategy/patterns` |
| `/risk` | Risk panel — parameters, safety locks, emergency-stop toggle | `/api/risk/status`, `/api/system/*` |
| `/positions` | Live positions table — entry/current, SL/TP, floating PnL, R-multiple, close actions | `/api/execution/positions` (3s poll) |
| `/orders` | Signal log — status, direction, setup, RR, JSON reasons | `/api/strategy/signals` |
| `/backtest` | Backtest & Monte Carlo — net profit, win rate, profit factor, DD, expectancy, Sharpe/Sortino, prob-of-ruin | `/api/backtest/run`, `/api/backtest/monte-carlo` |

---

## Research Program

The `backend/app/research/` package implements a 27-phase quantitative research program
(Phases 15–41). Each phase produces machine-readable artifacts under `backend/data/` and
is reproducible via a runner in `backend/scripts/`.

| Phase | Focus |
|---|---|
| 16 | Empirical tick-distribution diagnostics (~4M raw ticks) |
| 17–18 | Multi-factor benchmark; probability calibration |
| 19–20 | Feature importance / decile analysis; three-system ablation benchmark |
| 21–22 | Adaptive targets & stops; independent setup-entry benchmark |
| 23–24 | Confluence ladder; combinatorial edge reconstruction (OOS ranking) |
| 25–26 | Multi-timeframe swing benchmark; methodology & data-quality audit |
| 27 | Data pipeline — ingestion, validation, candle rebuild, 60/20/20 split, SHA256 manifest |
| 28–30 | Research baseline rebuild; conditional-edge discovery; forensic audit |
| 31–33 | Feature discovery, microstructure/cross-asset, market-state classification |
| 34–35 | Volatility-compression confirmation (walk-forward/placebo/FDR); post-mortem |
| 36–37 | External data architecture & readiness; macro/futures-volume research |
| 38 | Unified signal schema + 6-stage signal-quality gate |
| 39 | Prospective forward (paper/demo) validation with frozen config hash |
| 40 | Adversarial failure-recovery & risk certification (circuit breakers) |
| 41 | Final production-readiness audit (7-pillar) |

**Key outcome:** across Phases 28–37, candidate edges did **not** survive out-of-sample
validation and multiple-testing correction. Several apparent discoveries were confirmed as
false positives by follow-up phases (e.g. Phase 33 → Phase 34). This is a deliberately
honest research posture — the platform's value today is in its infrastructure,
reproducibility, and risk controls.

Run the research scripts, e.g.:

```bash
cd backend
python scripts/run_phase28_benchmark.py
python scripts/run_final_research_audit.py
```

---

## Testing

The suite runs entirely on the **mock MT5 adapter** — no broker, no network, no Windows.

```bash
cd backend
pytest tests/ -v                       # full suite (323 tests)
pytest tests/test_risk_engine.py -v    # a single module
pytest tests/ -k phase41 -v            # by keyword
pytest tests/ --cov=app                # with coverage (if pytest-cov installed)
```

Layout: 76 test modules under `backend/tests/`, covering the API, execution lifecycle,
risk engine, all strategy engines, scalper bots, backtest/Monte Carlo/walk-forward, and
every research phase. Shared fixtures (mock adapter, in-memory async DB, async HTTP client)
live in `backend/tests/conftest.py`.

---

## Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request (all branches):

| Job | Runner | Steps |
|---|---|---|
| **Backend tests (pytest)** | ubuntu-latest | Python 3.12 → `pip install -r backend/requirements.txt` → `pytest tests/ -v` → API contract diff vs `docs/baseline/` |
| **Backend lint (ruff)** | ubuntu-latest | Python 3.12 → `pip install ruff==0.16.8` → `ruff check app scripts` |
| **Backend types (mypy, report-only)** | ubuntu-latest | `mypy app --ignore-missing-imports` (non-blocking) |
| **Compose smoke (build + health)** | ubuntu-latest | `docker compose up --build -d` → poll `GET /api/health` → `docker compose down` |
| **Frontend build (Next.js)** | ubuntu-latest | Node 20 → `npm ci` → `npm run build` (type-checks the app) |

Notes:
- `pytest-asyncio` is pinned to `<0.24` because `conftest.py` uses a session-scoped
  `event_loop` fixture (removed in pytest-asyncio 1.x).
- The API contract diff freezes the mock clock and exits non-zero on response drift.
- The frontend has no ESLint config yet, so `next build` serves as the quality gate.

---

## Safety Model

Safety is enforced structurally, not by documentation alone:

1. **Boot guard** — `Settings.validate_safety_flags()` raises at startup if
   `EXECUTION_MODE=LIVE` without both live-trading flags set to `true`.
2. **Default-deny** — the code default and Docker default are `PAPER` with live flags off.
3. **Destination-aware gate** — every order-sending path (the execution engine and all six
   direct `mt5.order_send` sites) calls `core/safety.ensure_trading_allowed` first.
   Mock/paper execution is allowed in every mode; **real broker sends are refused in
   `PAPER`/`BACKTEST`**, allowed in `DEMO` only onto a demo account (`trade_mode == 0`),
   and in `LIVE` only with both flags. Unknown modes/destinations fail closed. In `LIVE` a
   mock (simulated) adapter is refused outright, so a live process with no terminal never
   simulates a fill; `/api/health` reports `simulated_execution: true` if a `DEMO`/`LIVE`
   mode is running on the mock.
4. **Emergency stop, cross-process** — a stop triggered via the API is persisted to a
   sentinel file under `AUTOTRADER_STATE_DIR` that every process reads, so new entries are
   blocked in the API, `runner.py`, and the bot scripts alike; reset removes it. The stop
   blocks **new entries only** — close/reduce sends and bot-command closes still work, so
   de-risking is never trapped.
5. **Layered blocks** — idempotency (duplicate order IDs), broker position sync, risk
   approval, and the gate all precede order submission.
6. **Circuit breakers** — the Phase 40 engine can halt trading on disconnect, stale data,
   spread explosion, or repeated failure, independent of the strategy.
7. **Manual stop only** — the gold scalper trades continuously until the operator issues
   `STOP`; its risk metrics are displayed for *monitoring* and do not auto-halt entries
   (an explicit operational choice — pair it with account-level discipline).

> [!CAUTION]
> The MT5 bots (`app/scalper/*`) and `scripts/run_demo_trader.py` build real order requests,
> but the destination-aware gate permits them only in `DEMO` (demo account) or `LIVE` (both
> flags) and refuses real sends in `PAPER`/`BACKTEST`. Always verify the account in the
> terminal header before starting a bot, and prefer a demo account while validating.

---

## Contributing

Branch-and-PR workflow:

```bash
git checkout main
git pull
git checkout -b feature/your-feature

# ... make changes ...
pytest tests/ -v            # from backend/
npm run build               # from frontend/, if UI changed

git add -A
git commit -m "feat: concise description"
git push -u origin feature/your-feature
```

Then open a Pull Request into `main`. CI must be green before merge.

**Conventions**
- Python: type hints, dataclasses for records, `snake_case`, no dead code.
- Keep every limit configurable; use `0` to mean "disabled".
- Never hard-code broker aliases — use `symbol_mappings` / `InstrumentSpecification`.
- Any change to trading logic must include a regression test.

---

## Tech Stack

| Area | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic v2 |
| ORM / DB | SQLAlchemy 2 (async), AsyncPG, aiosqlite, Alembic |
| Trading | MetaTrader5 (Windows, optional), NumPy, pandas |
| Frontend | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, lucide-react |
| Testing | pytest, pytest-asyncio, httpx (ASGI transport), ruff |
| Infra | Docker, Docker Compose (Postgres 16), GitHub Actions |

---

## License

Released under the [MIT License](LICENSE). © 2026.

---

## Disclaimer

This software is provided for **research and educational purposes only** and is provided
"as is", without warranty of any kind. Algorithmic trading carries substantial risk of
loss. The research program contained herein did not demonstrate a robust, profitable edge;
past or simulated performance is not indicative of future results. You are solely
responsible for any trading decisions, orders, and losses incurred through the use of this
software. **Never trade money you cannot afford to lose.**
