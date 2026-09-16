# Refactoring Architecture — Autonomous Trader

> Status: Phase 1 planning document, **REVISED** after independent review
> (`docs/REFACTORING_PLAN_REVIEW.md`). Companion to [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md)
> and [`REFACTORING_TASKS.md`](REFACTORING_TASKS.md). No source code modified.
>
> **Revision log (this version):** ADR-2 states in-process scope and requires explicit
> `RiskEngine` injection; ADR-3 reworked to mode × destination truth-table semantics
> with full order-path coverage and emergency-stop integration; new ADR-8 defines the
> cross-process stop sentinel with explicit guarantees and limits; ADR-4 defines spec
> precedence and fixes the symbol-mangling issue; ADR-6 adds frontend token support;
> dependency rules name the gate's coverage.

---

## 1. Current architecture (as-built, verified)

### 1.1 Runtime topology

```
┌────────────────────────────┐
│ Next.js 14 dashboard       │  6 pages, hardcoded http://localhost:8000
└─────────────┬──────────────┘
              │ HTTP/JSON (CORS: allow_origins=["*"], allow_credentials=True)
┌─────────────▼──────────────────────────────────────────────────────────┐
│ FastAPI  app/main.py                                                   │
│   9 routers, each constructing its OWN singletons at import time:      │
│     market/structure/liquidity/setups/signals/risk/backtest/execution  │
│   • 8 × MarketDataService (each with its own MockMT5Adapter + cache)    │
│   • 2 × RiskEngine (risk router's, and execution engine's internal)    │
│   • ExecutionEngine (own RiskEngine inside)                            │
│   • health.py: RealMT5Adapter connect attempt at import time           │
└──────┬──────────────────────────────┬─────────────────────────────────┘
       │                              │
┌──────▼──────────┐        ┌──────────▼───────────────┐
│ strategy/        │        │ execution/ → risk/        │
│ (ICT/SMC engine) │        │ ExecutionEngine +         │
└──────┬──────────┘        │ RiskEngine + PositionRec  │
       │                   └──────────┬───────────────┘
┌──────▼──────────────────────────────▼───────────────┐
│ services/market_data.py → data/mt5_{interface,mock,real} │
└──────────────────────────────┬──────────────────────┘
                               │
        runner.py (autonomous loop; a THIRD instance set, separate process)
```

**Key fact:** the runtime is only `strategy/ + execution/ + risk/ + services/ + data/ +
core/ + models/ + api/`. Everything else is research-only (see 1.2).

### 1.2 Actual package classification (verified by import analysis)

| Package | Reachable from runtime? | Used by |
|---|---|---|
| `core/`, `data/`, `services/` | yes | everything |
| `strategy/` | yes (API + runner + backtest/engine) | runtime |
| `execution/`, `risk/` | yes (API + runner) | runtime |
| `models/` | created but **never written/read at runtime** | main.py create_all only |
| `backtest/` | via API (`/api/backtest/*`) | API + phase scripts |
| `scalper/` | partially: `instrument.py`, `features.py` used widely; bots standalone; `execution.py` used only by a test | mixed |
| `intelligence/` | **no** | phase 17–19 scripts + tests |
| `context/` | **no** | phase 20–25 scripts + tests |
| `regime/`, `fusion/` | **no** | `backtest/tick_backtest.py` + tests |
| `information/` | **no** | phase 36/41 tests |
| `swing/` | **no** | phase 25 script + test |
| `research/` | **no** | phase scripts + tests |

### 1.3 Dependency anomalies

- Inverted layering: `intelligence/*` and `context/*` (conceptually "high") import
  `app.scalper.features/instrument` (conceptually low) for their input types.
- Package-level cycle: `regime/engine.py → scalper.features` and
  `scalper/selector.py → regime.engine` (latent fragility, no runtime impact).
- **Six order-path files** are *outside* the safety architecture (12 direct
  `mt5.order_send` calls): the five `scalper/` bots plus `scripts/run_demo_trader.py`
  (whose `--enable-demo` flag sends a real order regardless of `EXECUTION_MODE`).
  Dead `settings`/`ExecutionMode` imports in all five bots prove the safety intent
  existed but was never wired.

### 1.4 Persistence

- 12 SQLAlchemy entities defined (`models/domain.py`), tables created at startup and in
  tests, but **no repository layer and no writes anywhere** — the DB is currently a
  health-check target, not a system of record.
- Alembic fully scaffolded (async `env.py` targets `Base.metadata`) but `versions/` is
  empty; `alembic.ini` hardcodes credentials.
- The default `DATABASE_URL` is **in-memory SQLite**, which is *per-process* — a fact
  that constrains the cross-process stop design (ADR-8): a DB-backed sentinel would
  not cross processes under the default configuration.

### 1.5 Instrument-math status quo (verified)

Three competing XAUUSD "truths" exist today:
- `scalper/instrument.py:32-45` — digits=3, point=0.001, **pip_size=0.1**, contract=100
  (Exness-style 3-digit gold). Used by `strategy/engine.py` pip math.
- `data/mt5_mock.py:8-20` — digits=2, point=0.01, tick=0.01, contract=100 (mock
  environment; no `bid`/`ask` keys in the spec dict).
- `backtest/engine.py:44-51` — point-size heuristic (contract 100 vs 100000);
  `runner.py:11-20` derives pips from **digits**, not `pip_size`.

---

## 2. Proposed architecture (post-refactor)

### 2.1 Guiding principles

1. **One runtime, one state — per process.** All runtime engine state lives in a
   single application-state container per process; every consumer obtains services
   through FastAPI DI (API) or explicit construction (runner/scripts). **State that
   must cross process boundaries lives in the filesystem, not in memory** (ADR-8).
2. **One destination-aware safety gate.** Every code path that can send an order to a
   broker calls `core/safety.ensure_trading_allowed(destination, ...)` first — all six
   order-path files and the adapter. The gate consults execution mode, live flags, and
   the cross-process stop sentinel.
3. **One precedence-defined source of instrument truth.** Broker `symbol_info`
   overrides `InstrumentSpecification` for point/tick/contract/volume; `pip_size` is
   canonical in the spec; the mock adapter remains its own explicitly-labelled
   environment.
4. **Runtime/research boundary is explicit and documented.** No bulk package moves.
5. **No behavior change without a named defect.** Every deviation from current
   behavior traces to a problem ID in `REFACTORING_PLAN.md` §3, and is listed in the
   "intended behavior changes" register (§2.6).

### 2.2 Target topology

```
┌────────────────────────────────────────────────────────────────────────┐
│ FastAPI app/main.py                                                    │
│   lifespan: build AppState(adapter, market_data, execution_engine,     │
│             risk_engine, strategy_engine); store on app.state          │
│   routers:  service access via Depends(get_*_service)                  │
└────────────────────────────────────────────────────────────────────────┘
            │                                     │
   ┌────────▼─────────┐                 ┌─────────▼───────────────┐
   │ strategy/         │                 │ execution/               │
   │ StrategyEngine    │                 │ ExecutionEngine(         │
   └────────┬─────────┘                 │   adapter, risk_engine) ─┼──► risk/RiskEngine
            │                           └──────────┬──────────────┘    (the ONE instance
            │                                      │                    in this process)
   ┌────────▼──────────────────────────────────────▼───────────┐
   │ services/MarketDataService (single instance, shared cache,  │
   │             get_latest_price for position marking)          │
   │ data/ AbstractMT5Adapter → Mock | Real (send_order honors   │
   │       caller magic/comment)                                 │
   └───────────────────────────────────────────────────────────┘
            │
   ┌────────▼───────────────────────────────────────────────────┐
   │ core/: config · database · logging · pricing (NEW) ·        │
   │        stop_state (NEW: cross-process sentinel) ·           │
   │        safety (NEW: destination-aware gate)                 │
   └───────────────────────────────────────────────────────────┘
            ▲
            │ every process
   ┌────────┴───────────────────────────────────────────────────┐
   │ runner.py · 5 scalper bots · scripts/run_demo_trader.py     │
   │ (separate processes; construct engines explicitly; call the │
   │  gate before each order_send; stop-state shared via file)   │
   └───────────────────────────────────────────────────────────┘
```

Research packages (`intelligence/`, `context/`, `regime/`, `fusion/`, `information/`,
`swing/`, `research/`) remain exactly where they are, with a documented label
("research-only; not reachable from the API/runner"). Their consolidation happens via
`research/common/` + `scripts/_bootstrap.py`, not restructuring.

### 2.3 Module responsibilities (target)

| Module | Responsibility (target) | Change |
|---|---|---|
| `core/config.py` | Config + safety flags + `STATE_DIR` + `CORS_ORIGINS` + optional API token | extended |
| `core/safety.py` (NEW) | `ensure_trading_allowed(destination, account_trade_mode=None)` — ADR-3 truth table; consults stop sentinel | new |
| `core/stop_state.py` (NEW) | Cross-process sentinel: `trigger()/reset()/is_active()` over a file in `STATE_DIR` | new |
| `core/pricing.py` (NEW) | pip/PnL/cost/spread helpers delegating to the reconciled `InstrumentSpecification` with broker-`symbol_info` precedence | new |
| `data/` | MT5 adapter abstraction; `RealMT5Adapter.send_order` honors caller `magic`/`comment` | small fix |
| `services/` | MarketDataService — the single adapter owner in the API process; adds `get_latest_price` | wiring + small |
| `strategy/` | ICT/SMC signal generation | unchanged |
| `execution/` | Order lifecycle, idempotency, position management; receives the shared `RiskEngine`; calls the gate; spec-based PnL | math + DI |
| `risk/` | Position sizing, limits, emergency stop — one instance per process; trigger/reset also writes/removes the sentinel | wiring + sentinel |
| `scalper/` | Tick engines + 5 bots; NEW `mt5_orders.py` shared broker plumbing; bots call the gate before each send | consolidation |
| `backtest/` | Deterministic backtester (exposes `last_trades`), metrics, Monte Carlo, walk-forward | fixes + determinism |
| `research/` + `research/common/` (NEW), `scripts/_bootstrap.py` (NEW) | Phase engines + shared utilities | mechanical rewires |
| `intelligence/ context/ regime/ fusion/ information/ swing/` | Research analysis packages — **unchanged location** | documented as research-only |
| `models/`, `database/` | Domain schema + migrations | Alembic baseline decision (D-06) |
| `api/` | Routers: thin, DI-wired, unified error envelope, token-guarded mutating endpoints | DI + hardening |

### 2.4 Dependency rules (target)

1. `api/ → services/ → data/` — routers never build adapters; **no module-level engine
   instantiation in `app/api/`** (8 routers affected, including `structure.py`).
2. `execution/ → risk/` one-directional; **exactly one** `RiskEngine` instance per
   process; `ExecutionEngine` must **not** construct its own — it receives it
   (`ExecutionEngine.__init__(adapter=None, risk_engine=None)`; constructing a default
   remains allowed for standalone/test use, but the API and runner inject).
3. `core/` depends on nothing above it; `strategy/`, `execution/`, `scalper/`,
   `backtest/` may import `core/` (including `safety`, `stop_state`, `pricing`) and
   `scalper/instrument.py`.
4. Research packages may not be imported by `api/`, `runner.py`, `services/`, or
   `execution/` (enforced by review + grep check E-05).
5. **Gate coverage rule:** every `mt5.order_send` call in `app/` or `scripts/` is
   either inside `data/mt5_real.py` (the adapter) or immediately preceded by
   `ensure_trading_allowed(...)` — verified by the E-05 grep.
6. `scalper/mt5_orders.py` and `data/mt5_real.py` are the only places allowed to
   construct MT5 order/close request payloads.

### 2.5 Cross-process state model

| State | Scope | Mechanism |
|---|---|---|
| Risk limits, daily lock, trade counters | per process | in-memory (as today) |
| Emergency stop — API process order path | API process | shared `RiskEngine` via DI (B-01) |
| Emergency stop — **all processes' new orders** | cross-process | sentinel file in `STATE_DIR` (ADR-8) |
| Candle cache, executed-order IDs | per process | in-memory (as today) |

### 2.6 Intended behavior changes register (complete list)

Every change below is a *documented intent*, not an accident:

| # | Change | Justified by | Where |
|---|---|---|---|
| 1 | API emergency stop blocks API order submission | P-01 | B-01 |
| 2 | Sentinel blocks new orders in *all* gated processes once triggered | P-14 | B-03/B-05 |
| 3 | Direct real-broker sends refused in `PAPER`/`BACKTEST` (incl. `run_demo_trader.py --enable-demo`) | P-02, `PROFITABILITY_INVESTIGATION.md` C5 | B-03 |
| 4 | `DEMO` mode allows real sends only onto a demo account (`trade_mode == 0`) | P-02 | B-03 |
| 5 | Forex PnL/cost numbers corrected (~×1000 error removed) | P-04 | C-01 |
| 6 | Spread display semantics unified onto `pip_size` (mock-gold spread numbers change; spread gate is disabled by default → no trading-behavior change) | P-15 | B-02 |
| 7 | Mock position marking uses real adapter price / candle close instead of hard-coded 2400.0 | P-17 | C-01 |
| 8 | `POST /api/execution/orders` returns 502 on broker `FAILED` (failure path only) | P-04 scope / R-07 | C-01 |
| 9 | Monte Carlo endpoint returns a simulation over real trades | P-03 | C-02 |
| 10 | Walk-forward Monte Carlo seeded; backtest trade IDs deterministic | P-09 | C-02 |
| 11 | CORS origins restricted to `CORS_ORIGINS` (default `localhost:3000`); optional production token gate | P-05 | C-06/D-01 |
| 12 | `get_default_spec` strips only a trailing "M" | P-18 | B-02 |
| 13 | `RealMT5Adapter.send_order` uses caller's `magic`/`comment` | P-16 | C-07 |

---

## 3. Key architectural decisions (ADR-style)

### ADR-1 — Keep the modular monolith; no service decomposition

- **Current:** single FastAPI process; single operator; Windows/MT5 affinity (the real
  adapter requires a local terminal — a separate process/service cannot own it).
- **Problem addressed:** none — decomposition solves problems this system doesn't have
  while worsening its hardest constraint (MT5 is a local Windows resource).
- **Decision:** consolidate in place.
- **Trade-off:** the codebase keeps large research-only sections; accepted and
  documented rather than "solved" by extraction.
- **Review verdict:** approved unchanged.

### ADR-2 — Application-state container + FastAPI DI, with explicit RiskEngine injection

- **Current:** routers build their own singletons at import time; **8** market
  services; 2 risk engines; emergency stop doesn't propagate even in-process (P-01/P-07).
- **Alternatives:** global registry (keeps import-time side effects); DI library
  (needless dependency). **Chosen:** build state in `main.py` lifespan, expose via
  `app.state` + small `Depends` accessors; no new dependency; test-overridable via
  `dependency_overrides` (mechanism conftest.py already uses).
- **Scope — stated precisely:** the container is **in-process**. It fixes P-01's
  in-process half and P-07. Cross-process stop propagation is ADR-8's separate
  mechanism; DI does **not** claim to stop `runner.py` or bots.
- **Required detail (review R-06):** `ExecutionEngine.__init__(adapter=None,
  risk_engine=None)` accepts and reuses an injected `RiskEngine`; the container passes
  the single instance. A grep assertion (no `RiskEngine()` construction inside
  `ExecutionEngine`) verifies it.
- **Test-lifespan caveat (review §3):** `httpx.ASGITransport` does not run lifespan
  events. Every router depending on `app.state` must be exercised via
  `dependency_overrides` in conftest; `test_health.py` must be covered by overrides so
  health assertions keep working without lifespan.
- **Trade-offs:** every router changes (mechanical); import-time adapter connection
  moves into lifespan.
- **Risk/migration:** response shapes preserved; contract diff (E-03) guards drift.

### ADR-3 — Destination-aware safety gate (truth table over mode × destination)

- **Current:** boot guard in `config.py` + runtime flag check in `ExecutionEngine`
  cover only the runner/API path; six order-path files bypass everything (P-02). The
  original gate design ("mode-only; zero change in PAPER/DEMO") was **rejected by
  review** because it would leave real broker sends permitted in PAPER — the exact
  defect — while a blanket PAPER block would also break legitimate mock paper tests.
- **Decision:** `ensure_trading_allowed(destination: "MOCK"|"REAL",
  *, account_trade_mode: int | None = None)`. Destination is derived from the adapter
  type (`MockMT5Adapter` → MOCK; anything constructing requests against the real
  `mt5` API → REAL). Truth table:

  | Execution mode | Destination = MOCK (paper sim / mock adapter) | Destination = REAL broker |
  |---|---|---|
  | `BACKTEST` | allowed | **refused** |
  | `PAPER` | allowed | **refused** |
  | `DEMO` | allowed | allowed **only if** `account_trade_mode == 0` (demo account) |
  | `LIVE` | allowed | allowed **only if** both live flags set (also enforced at boot) |
  | any, with sentinel present | **refused** | **refused** |

- **Emergency-stop integration:** the gate reads `core/stop_state.is_active()` first —
  a triggered stop blocks gated order paths in every process, not just the API.
- **Coverage (all direct order-send sites, verified by grep):**
  `scalper/autonomous_scalper_daemon.py`, `scalper/demo_scalper_engine.py`,
  `scalper/ultra_tick_scalper.py`, `scalper/gold_multi_scalper.py`,
  `scalper/grid_martingale_bot.py`, `scripts/run_demo_trader.py` — the gate is called
  before each first send (and before re-sends/close loops where cheap to add).
- **Trade-offs:** intended behavior change register §2.6 #3/#4 (real sends in
  PAPER/BACKTEST were previously possible and are now refused). Mock paper flows are
  explicitly preserved by the table. Future scripts are forced through the chokepoint
  by rule 5 + E-05 grep.
- **What the gate does *not* do (explicit):** it does not cap concurrent positions,
  restore daily-loss circuit breakers, or stop bot event loops — see the deferral note
  in the plan's non-goals (R-15).

### ADR-4 — Instrument truth: explicit precedence + canonical pip size

- **Current:** three competing spec sources (§1.5); ×100 literals at ≥8 sites (P-04);
  `get_default_spec` strips every "M" (P-18).
- **Alternatives:** (a) always require live `symbol_info` — breaks offline testability;
  (b) keep per-module constants — status quo defect; (c) **chosen:** precedence chain
  **broker `symbol_info` > `InstrumentSpecification` static spec**, with `pip_size`
  defined canonically in the spec (gold 0.1, 5-digit FX 0.0001, JPY 0.01) and a
  digits-derived fallback only for unknown symbols.
- **XAUUSD reconciliation (review R-05):** the mock adapter's digits=2/point=0.01 spec
  describes the *mock environment* and stays; `InstrumentSpecification`'s digits=3/
  pip=0.1 is the *trading-level* truth. Consequence: spread computations migrate from
  digits-based division to `pip_size` (runner `calculate_spread_in_pips`,
  `tick_engine` pip scale) **in the same task (B-02)**, with characterization tests
  locked before the change. Trading-level SL/TP math already flows through the spec
  and is preserved bit-for-bit; displayed spread values in the mock environment may
  change (documented, §2.6 #6).
- **Symbol-name fix:** `get_default_spec` normalizes with a trailing-suffix rule
  (`removesuffix("M")`) instead of stripping all "M" characters.

### ADR-5 — Research consolidation via `research/common/` + `scripts/_bootstrap.py`

- **Current:** 9× duplicated hash verifier (all with a version-fallback weakening, the
  same fallback also embedded in 3 tests), verbatim FDR duplicate, ≥6 split
  implementations, ~42% line-similar phase engines, heavily copy-pasted scripts.
- **Decision:** extract shared functions into `research/common/`; rewire engines and
  scripts mechanically; place the path-setup helper at **`scripts/_bootstrap.py`**
  (outside the package) so it can set `sys.path` before any `app.*` import — the
  original "helper inside the package" design was circular (review R-10). Do not move
  packages; do not rewrite engine logic.
- **Hash semantics (review R-11):** the shared `verify_dataset_hash(data, strict=False)`
  **defaults to the current lenient behavior** (accepts version "2.0.0" fallback) so
  nothing silently changes; `strict=True` is opt-in and documented. Whether to tighten
  is recorded as an explicit decision in the task, not smuggled in. The 3 tests that
  embed the fallback keep passing under the default.

### ADR-5b — Backtest trades access without changing the `/run` contract

- **Current:** `BacktestEngine.run()` returns `BacktestMetricsReport`, which carries no
  trade list; `/api/backtest/monte-carlo` therefore cannot obtain trades from the
  report (review R-04/N-03).
- **Alternatives:** add `trades` to `BacktestMetricsReport` — changes the
  `/api/backtest/run` JSON shape (rejected); return a tuple from `run()` — changes a
  public signature used elsewhere; **chosen:** `BacktestEngine.run` stores
  `self.last_trades: List[BacktestTradeRecord]` (public attribute set during `run`);
  the endpoint reads it. Zero shape/signature change; covered by a `/run` contract
  test.

### ADR-6 — API surface hardening is config-gated, with frontend parity

- **Current:** wildcard CORS + zero auth on dangerous endpoints (P-05).
- **Decision:** CORS origins from `CORS_ORIGINS` env (default
  `http://localhost:3000`) — moved early into C-06 (review R-13); bearer token check
  active only when `APP_ENV=production` **and** `AUTOMATION_API_TOKEN` is set, and the
  bundled dashboard gains optional `Authorization`-header support in **C-05** so
  enabling the token cannot silently break the dashboard (review R-08). If neither
  token nor reverse proxy is configured in production, D-01's task text requires the
  deployment documentation to say so explicitly.
- **Trade-off:** slightly less permissive defaults; production gets real protection
  without local-dev friction.

### ADR-7 — Alembic: generate a baseline; stop duplicating credentials

- **Current:** scaffolded-but-unused Alembic + `create_all` at startup (P-12).
- **Decision (D-06):** generate an initial autogenerate-baseline migration so future
  schema changes are possible on existing DBs; read the URL from settings instead of
  hardcoding. Fallback decision: document `create_all` as official and remove the
  hardcoded credentials. Either resolves the ambiguity.

### ADR-8 — Cross-process stop sentinel (NEW; review R-01/M-03)

- **Current:** `emergency_stop_active` is per-instance, per-process. API stop cannot
  reach `runner.py`, bots, or scripts (P-14). The default DB (`:memory:` SQLite) is
  per-process, so a DB flag would not cross processes either.
- **Decision:** a sentinel **file** in a gitignored state directory
  (`STATE_DIR`, env-configurable, default `<repo>/backend/state/`; file
  `EMERGENCY_STOP.json` containing `{"reason", "triggered_at"}`):
  - `RiskEngine.trigger_emergency_stop()` writes it (in addition to its in-memory flag,
    preserving all existing response semantics);
  - `RiskEngine.reset_emergency_stop()` removes it (cross-process reset works);
  - `core/stop_state.is_active()` does a stat/read (cheap, no polling loop);
  - `ensure_trading_allowed()` consults it first (ADR-3);
  - `ExecutionEngine.execute_signal` consults it directly as defense-in-depth.
- **Guarantees (precise):** blocks **new order submissions** in every process that
  routes through the gate or `ExecutionEngine`; persists across process restarts
  (closing the previously-noted restart gap); reset works from any process.
- **Limits (precise, no overclaiming):** does **not** close already-open positions in
  bot processes; does **not** terminate bot loops — sends fail fast with a clear
  reason; processes that write `mt5.order_send` without the gate (none after B-03, by
  E-05 audit) would bypass it.
- **Alternatives:** (a) DB row — rejected because the default DB is per-process
  in-memory SQLite; (b) TCP/IPC daemon — rejected as over-engineering for a
  single-operator tool; (c) documented API-only scope — rejected by review as
  misleading since bots are the paths most likely to be trading.
- **Trade-offs:** a new runtime file dependency and one more gitignored directory;
  negligible complexity vs. the safety gain.

---

## 4. What this architecture deliberately does *not* change

- Strategy logic, signal schemas, the 6-stage quality gate, research phase engines'
  logic and outputs, the mock-adapter test approach, YAML/`.env` config split,
  docker/Postgres stack, MIT licensing, and the honest "edge not validated" posture.
- The five MT5 bots remain independent strategies with their own loops — they share
  plumbing and the safety gate, not a common engine class.
- The "MANUAL STOP ONLY" risk-limit philosophy (`config/risk.yaml` zeros) is untouched;
  the gate enforces the *mode/destination model*, not per-day limits. Position churn
  (C1) and disabled circuit breakers (C4) are explicitly deferred — see plan non-goals.
