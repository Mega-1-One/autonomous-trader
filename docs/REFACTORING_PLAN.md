# Refactoring Plan — Autonomous Trader

> **Status: Phase 1 (analysis & planning), REVISED after independent review
> (`docs/REFACTORING_PLAN_REVIEW.md`). Awaiting re-review and approval. No source code
> has been modified.**
> Companion documents: [`REFACTORING_ARCHITECTURE.md`](REFACTORING_ARCHITECTURE.md),
> [`REFACTORING_TASKS.md`](REFACTORING_TASKS.md).
> Existing documents referenced, not replaced: `README.md`, `PROFITABILITY_INVESTIGATION.md`.
>
> **Revision log (this version):** applied review findings R-01…R-16. Major changes:
> cross-process emergency-stop sentinel added (B-05/ADR-8); safety-gate semantics
> redefined over *mode × destination* (ADR-3) instead of mode-only; order-path coverage
> corrected to 6 files / 12 direct `mt5.order_send` calls; Monte Carlo task re-specified
> around a non-breaking trades-access mechanism; XAUUSD spec conflict made explicit with
> a precedence decision; explicit `RiskEngine` injection into `ExecutionEngine`;
> counts corrected (8 market services, 39 scripts, 27 tasks); frontend token support
> added; CORS restriction moved earlier; per-task rollback notes added.

---

## 1. Executive summary

Autonomous Trader is a deterministic, research-driven algorithmic trading platform for
MetaTrader 5: a FastAPI backend (Python 3.12, SQLAlchemy async, ~220 Python files), a
Next.js 14 dashboard, a 27-phase quantitative research program, and a safety model that
defaults to paper execution. The codebase is **well-tested (165 tests, all passing on
the baseline runs of 2026-09-16/17) and honestly documented**, but it has accumulated
several structural defects:

1. **A broken safety-critical state model, within *and* across processes.**
   - In the API process, two disconnected `RiskEngine` instances mean an emergency stop
     triggered through the dashboard/API does **not** block order execution (P-01).
   - Across processes, `runner.py` and the bot scripts run with their own engines, so
     *no* API-triggered emergency stop can reach them at all. The revised plan adds an
     explicit cross-process stop sentinel (P-14, task B-05, ADR-8) and states its
     limits precisely.
2. **A structurally unsafe live-boting path.** **Six files containing 12 direct
   `mt5.order_send` calls** (five bots in `app/scalper/` plus
   `scripts/run_demo_trader.py`) bypass `ExecutionEngine`, `RiskEngine`, and the
   settings safety flags; one of them (`run_demo_trader.py --enable-demo`) sends a real
   broker order regardless of `EXECUTION_MODE` (P-02).
3. **Functional bugs**: the Monte Carlo endpoint always discards its own backtest
   results (P-03); PnL math hard-codes a ×100 contract multiplier that is wrong for
   forex instruments (P-04); the position price updater falls back to a hard-coded
   2400.0 because the mock symbol spec has no `bid` key (P-17).
4. **Insecure-by-construction API surface**: no authentication on order submission /
   emergency-stop / close-all endpoints combined with `allow_origins=["*"]` +
   `allow_credentials=True` CORS (P-05).
5. **Substantial duplication**: byte-identical dead module (`fusion_2.0.py`), an
   orphaned root-level `app/scalper/` package, 9 copy-pasted dataset-hash verifiers,
   two parallel fusion engines, ~42% line-identical phase engines, heavily copy-pasted
   runner scripts, and six order-path files each re-implementing broker plumbing.
6. **Two mutually inconsistent XAUUSD instrument specifications** already exist in the
   repo (`scalper/instrument.py` vs `data/mt5_mock.py`), so any "single source of
   instrument truth" must first define precedence and lock characterization tests
   (P-15). `InstrumentSpecification.get_default_spec` also mangles symbols by stripping
   every "M" character (P-18).
7. **`RealMT5Adapter.send_order` ignores the caller's `magic`/`comment`** and hard-codes
   `100001` (P-16) — per-strategy attribution is broken and any shared order-builder
   helper is cosmetic until this is fixed.
8. **Research/runtime layering is inverted and undocumented**: `intelligence/`,
   `context/`, `regime/`, `fusion/`, `information/`, `swing/` are *not reachable from
   the runtime at all* and depend backwards on the low-level `scalper` package (P-11).

**Proposed direction:** a *conservative consolidation* refactor of the existing modular
monolith — no rewrites, no microservices, no framework changes. Introduce a shared
application-state container (DI, **in-process only**) to unify engine instances, a
single destination-aware safety gate backed by a **cross-process stop sentinel file**,
and shared domain primitives (pip/contract/cost math). Remove dead/duplicate code.
Consolidate research copy-paste into shared helpers. Harden the API surface. The
research program's artifacts and honest "no edge" posture are preserved exactly as-is.

**Not in scope (explicit non-goals):**
- Any change to strategy logic or research conclusions.
- Introducing new frameworks (no microservices, no event bus, no new ORM).
- Migrating away from SQLite/Postgres, or making Alembic mandatory (a baseline decision
  is included as a low-priority task).
- Achieving "profitability" — per `PROFITABILITY_INVESTIGATION.md`, that is a research
  problem, not an engineering one.
- **Explicit deferral (safety-relevant):** this refactor enforces the *execution-mode*
  model and cross-process stop propagation. It does **not** fix the operational-risk
  behaviors documented in `PROFITABILITY_INVESTIGATION.md`: unbounded concurrent
  position churn (C1), coin-flip entry logic (C2), or the disabled automatic circuit
  breakers ("MANUAL STOP ONLY", C4). Those are product/research decisions and remain
  deferred; this refactor does **not** make live trading safe.

---

## 2. Current architecture (verified)

Runtime signal path (the only path the API and runner exercise):

```
FastAPI (app/main.py)  ── routers (app/api/*, module-level singletons)
runner.py              ── StrategyEngine → ExecutionEngine → RiskEngine
                                 │                 │
                        services/market_data   data/mt5_{mock,real}
```

- **Persistence layer exists but is unused at runtime.** 12 SQLAlchemy entities
  (`app/models/domain.py`) are created at startup (`main.py:26-27`) but *nothing writes
  to them* — no repository, no API endpoint persists a signal/order/position.
- **Research-only packages** (`intelligence/`, `context/`, `regime/`, `fusion/`,
  `information/`, `swing/`, most of `backtest/`, all of `research/`) are exercised only
  by `scripts/run_phase*.py` and `tests/test_phase*.py`.
- **Six order-path files** bypass the safety architecture: five bot engines in
  `app/scalper/` and `scripts/run_demo_trader.py` — 12 direct `mt5.order_send` calls
  outside the adapter (13 including the adapter's own).
- Config: `.env` (pydantic-settings) + `config/{strategy,risk}.yaml` (loaded as opaque
  dicts, no validation) + code defaults.
- Tests: 52 modules, 165 tests, green on mock adapter; `pytest-asyncio<0.24` pinned in
  CI only (requirements.txt allows ≥0.23.5 which permits 1.x — mismatch).
- Infra: docker-compose (postgres used, **redis unused by any code**), GitHub Actions
  (pytest + next build; no lint, no type-check).

Full architecture description and proposed target: see
[`REFACTORING_ARCHITECTURE.md`](REFACTORING_ARCHITECTURE.md).

---

## 3. Confirmed problems (evidence-based)

Legend: **Priority** = critical / high / medium / low. **Size** = small / medium / large.
Category: [C] confirmed · [P] potential (needs investigation) · [O] optional/preference.
Review cross-references (R-xx / N-xx) cite `docs/REFACTORING_PLAN_REVIEW.md`.

### P-01 — Emergency stop does not block order execution, in-process or cross-process · [C] · critical · medium

- **Evidence:** `app/api/risk.py:9` creates `risk_engine = RiskEngine()`;
  `app/api/execution.py:9-10` creates `execution_engine = ExecutionEngine(...)`, whose
  `__init__` creates its **own** `RiskEngine()` (`app/execution/engine.py:44`).
  `POST /api/system/emergency-stop` sets `emergency_stop_active=True` only on the risk
  router's instance; `POST /api/execution/orders` → `execute_signal` →
  `self.risk_engine.evaluate_trade_risk` uses the execution engine's instance and still
  approves. A third instance set exists in `app/runner.py:40-42` — a **separate
  process** — and every bot/script process has its own engines.
- **Scope of the problem (two layers):**
  1. *In-process (API):* the two-instance defect above — fixable by DI.
  2. *Cross-process:* `emergency_stop_active` is plain in-memory state. Even after DI
     unification, an API-triggered stop cannot affect `runner.py`, any bot, or any
     script process. The original plan claimed "emergency stop finally blocks orders"
     without acknowledging this — **that claim is retracted**; see P-14 and ADR-8.
- **Why it matters:** the dashboard's emergency-stop button appears to work while live
  (or paper) order submission continues, in this process and others.
- **Fix:** (a) single shared engine container with explicit `RiskEngine` injection into
  `ExecutionEngine` (in-process); (b) a cross-process stop sentinel file read by every
  order-sending path (P-14/B-05/ADR-8).
- **Dependencies:** none (foundational).
- **Risk:** changes router wiring; must preserve endpoint response shapes (frontend and
  `test_risk_engine.py`, `test_execution.py` depend on them).

### P-02 — Direct MT5 order paths bypass the execution-mode safety model · [C] · critical · medium

- **Evidence (corrected count):** **6 files, 12 direct `mt5.order_send` calls** outside
  the adapter (verified by grep; 13 calls including `data/mt5_real.py:198`):
  - `scalper/autonomous_scalper_daemon.py` (L130, L166)
  - `scalper/demo_scalper_engine.py` (L73, L113)
  - `scalper/ultra_tick_scalper.py` (L86, L119)
  - `scalper/gold_multi_scalper.py` (L331, L440)
  - `scalper/grid_martingale_bot.py` (L92, L162, L200)
  - `scripts/run_demo_trader.py` (L71) — **the sixth path the original plan omitted**;
    its "SAFETY LOCK" message is bypassed entirely when `--enable-demo` is passed,
    sending a real 0.01-lot EURUSD order regardless of `EXECUTION_MODE`.
  Each bot imports `settings`/`ExecutionMode` but never references them (dead imports).
  README's own CAUTION admits bots send real orders "regardless of EXECUTION_MODE".
- **Why it matters:** the structural safety model ("live trading requires two flags")
  is unenforced for every path that actually talks to the broker. A misconfigured
  `.env` gives a false sense of safety.
- **Fix:** a destination-aware gate (`core/safety.py`) + cross-process sentinel; every
  order-send site routes through it (see ADR-3 truth table). Note this *is* an intended
  behavior change: real broker sends in `PAPER`/`BACKTEST` will be refused where they
  are currently permitted.
- **Risk:** medium — deliberate behavior change, documented; demo workflows require
  `EXECUTION_MODE=DEMO` (with a demo account) or `LIVE`+flags going forward.
- **Dependencies:** B-05 (sentinel) before the gate consumes it.

### P-03 — Monte Carlo endpoint always returns the empty-trade result · [C] · high · small

- **Evidence:** `app/api/backtest.py:66-68` — runs a full `BacktestEngine.run(...)`,
  then calls `simulator.run_simulation(req.initial_balance, [])` with an **empty list**,
  discarding the trades. `BacktestEngine.run` returns only a `BacktestMetricsReport`
  (`backtest/metrics.py:34-59`), which carries **no trade list**, so the original fix
  ("pass `report.trades`") is not implementable as written. The existing test
  (`test_api_run_monte_carlo`) asserts only key presence and cannot catch this.
- **Fix:** add a non-breaking trades-access mechanism — `BacktestEngine.run` sets
  `self.last_trades: List[BacktestTradeRecord]` (run signature and `/api/backtest/run`
  response shape unchanged) — and pass it to the simulator.
- **Risk:** minimal; add regression + determinism tests.

### P-04 — Hard-coded ×100 contract multiplier in PnL math · [C] · high · medium

- **Evidence:** `execution/engine.py:195,244`, `scalper/position_manager.py:59,94`,
  `gold_multi_scalper.py:152,158`, `intelligence/cost_analyzer.py:45,48`,
  `scalper/adaptive_exit_v2.py:34` all hard-code `100.0`;
  `backtest/engine.py:44-51` guesses contract size from point size (third spec source).
  The adapter already supplies `contract_size` in `symbol_info` but PnL paths never
  read it.
- **Why it matters:** XAUUSD contract size is 100, EURUSD is 100,000 — all forex PnL,
  slippage, and cost numbers produced by these paths are wrong by ~1000×.
- **Fix:** centralize on the instrument-spec precedence defined in P-15/ADR-4;
  delete local hard-codes.
- **Risk:** medium — changes numeric outputs for non-XAU instruments (intended).
  Characterization tests lock current values *before* changes (B-02).
- **Dependencies:** B-02 (spec reconciliation + primitives) must land first.

### P-05 — Unauthenticated dangerous endpoints + wildcard CORS · [C] · high · small

- **Evidence:** no auth anywhere in `app/api/*`. Dangerous endpoints:
  `POST /api/execution/orders`, `POST /api/execution/close-all`,
  `POST /api/execution/positions/{id}/close`, `POST /api/system/emergency-stop`,
  `POST /api/system/reset-emergency-stop`. `app/main.py:43-46` sets
  `allow_origins=["*"]` **and** `allow_credentials=True` (Starlette echoes any origin).
- **Why it matters:** any web page open in the operator's browser can reach
  `localhost:8000` and submit orders or close all positions.
- **Fix:** (a) restrict CORS origins via `CORS_ORIGINS` env (moved **early**, into
  C-06, per review R-13); (b) optional bearer token enforced on mutating endpoints in
  production (D-01), with **frontend token support added in C-05** so enabling the
  token cannot silently break the dashboard (review R-08).
- **Risk:** low; default dev flow unchanged.

### P-06 — Dead and duplicated modules · [C] · high · small

- **Evidence:**
  - `app/intelligence/fusion_2.0.py` is **byte-identical** to
    `app/intelligence/fusion_2_0.py` (identical SHA-256; the dotted name is not even
    importable as a module path). Only `fusion_2_0` is imported (3 phase scripts).
  - Root-level `app/scalper/position_manager.py` (outside `backend/`, tracked in git)
    is a near-verbatim duplicate of `backend/app/scalper/position_manager.py`.
  - `app/intelligence/logger.py`: zero references **and not importable** — it uses
    `Optional` without importing it (`NameError` at line 9). Deletion is the only
    realistic option; "wiring it in" would require fixing it first (review N-05, R-09).
  - `app/scalper/config.py` (`SmallAccountDemoConfig`): zero references; it is the only
    config artifact that disables every risk limit.
- **Fix:** delete all four (default decision); no "wire-in" option for the logger.
- **Risk:** trivial; verify no test references (verified by import search).

### P-07 — API dependency wiring: 8 MarketDataService instances, module-level singletons · [C] · high · medium

- **Evidence (corrected count):** module-level `MarketDataService()` instances in **8**
  routers (`execution.py:9`, `backtest.py:10`, `market.py:6`, `liquidity.py:7`,
  `setups.py:11`, `risk.py:10`, `signals.py:6`, `structure.py:6` — the original plan
  omitted `structure.py`), each with its own `MockMT5Adapter` and candle cache.
  `health.py:14-19` connects to MT5 at **import time**. Consequences: (a) dashboard
  execution path is always mock even when a real terminal is attached; (b) cache state
  is per-router; (c) tests cannot inject mocks into the API (0 uses of `monkeypatch`).
- **Fix:** single app-state container created in `main.py` lifespan; routers receive
  services via FastAPI `Depends`. Preserve all response shapes.
- **Risk:** medium — touches every router; tests updated via `dependency_overrides`.
- **Dependencies:** P-01 in-process fix is part of this (B-01), **including** explicit
  `risk_engine` injection into `ExecutionEngine` (review R-06).

### P-08 — Research machinery copy-paste · [C] · medium · large (but low urgency)

- **Evidence (counts corrected per review R-12):** `verify_dataset_hash()` copy-pasted
  in **9 engines** (all with the weakening `or data.get("version") == "2.0.0"`
  fallback; the same fallback is also embedded in 3 phase tests: `test_phase31`,
  `test_phase32`, `test_phase36`); Benjamini-Hochberg FDR duplicated
  (`research/feature_discovery/statistical_testing.py:27` vs
  `research/macro_futures/macro_futures_engine.py:85`); ≥6 distinct walk-forward/split
  implementations; two metrics calculators + ≥7 inline recomputations;
  `phase28`↔`phase29` engines ~42% line-similar; `fetch_real_ticks` duplicated in ~12
  scripts; **39** script `.py` files (44 files contain `sys.path.insert`), with
  **5** runner scripts injecting venv site-packages; tick window
  `datetime(2026,8,10)–(2026,8,18)` hard-coded in ~12 scripts.
- **Why it matters:** correctness risk (a bug fix must be applied 9×; the version-
  fallback weakens every hash check) and high maintenance cost. Urgency is low — the
  research program is dormant — but any future phase inherits the debt.
- **Fix:** shared `research/common/` module (dataset-hash verification with an
  explicit strict/lenient decision, FDR, splits, metrics, tick fetch) and a
  **`scripts/_bootstrap.py` path-setup helper placed outside the package** so it can
  be imported before `app.*` is importable (review R-10). Hash-check tightening is a
  separate, explicit decision — not a silent side effect (review R-11).
- **Risk:** medium — touching research code risks breaking published-artifact
  reproducibility; each rewire verified by that phase's existing test.

### P-09 — Determinism gaps contradicting the README claim · [C] · medium · small

- **Evidence:** `backtest/walk_forward.py:92` — unseeded `np.random.choice(...)`;
  `backtest/engine.py:149` uses `uuid.uuid4()` for trade IDs; seeded sites exist
  (`monte_carlo.py:53` seed=42, `phase34_engine.py:123`).
- **Fix:** seed the walk-forward simulator; deterministic trade IDs.
- **Risk:** small; verify downstream tests don't rely on randomness.

### P-10 — Frontend quality gaps · [C] · medium · medium

- **Evidence:** hardcoded `http://localhost:8000` in all 6 pages; `useState<any>` in 5
  of 6 pages; POST actions (emergency stop, close-all, close position) have no
  `res.ok` check and no confirmation dialog (`risk/page.tsx:32`,
  `positions/page.tsx:30,35`); 5 of 6 pages swallow fetch errors to `console.error`;
  "PAPER MODE" badge hardcoded in `layout.tsx:39`; `recharts` declared but unused.
- **Fix:** shared API client module + typed responses + error surfaces + confirmation
  for destructive actions + dynamic mode badge + **optional `Authorization` header
  support** (`NEXT_PUBLIC_API_TOKEN`) so D-01's token gate cannot break the dashboard
  (review R-08). Keep visual design unchanged.
- **Risk:** low-medium; UI regression risk handled by keeping JSX structure intact.

### P-11 — Inverted/unclear layering of research packages · [C] · medium · large (can be deferred)

- **Evidence:** `intelligence/*`, `context/*` depend on `app.scalper.features` /
  `app.scalper.instrument` for input types; `regime/engine.py` ↔ `scalper/selector.py`
  form a package-level cycle; nothing in `api/*` or `runner.py` imports any of these
  packages, despite the README presenting them as live architecture layers.
- **Fix (minimal):** document the actual boundary (runtime vs research); extract shared
  input dataclasses only if a task requires it. **Do not** move packages in bulk.
- **Risk:** low if deferred; medium if executed (import churn across ~30 files).

### P-12 — Config and infra inconsistencies · [C] · low · small

- **Evidence:**
  - `.env.example:4` omits `DEMO` mode (exists in `config.py:12`).
  - `docker-compose.yml` includes a Redis service no code references; backend depends
    on its healthcheck.
  - `database/alembic.ini:6` hardcodes Postgres credentials; `versions/` contains only
    `.gitkeep` — Alembic is scaffolded but never used.
  - `requirements.txt` allows `pytest-asyncio>=0.23.5` (incl. 1.x) while CI pins
    `<0.24` and `conftest.py` uses the removed session-scoped `event_loop` pattern.
  - `config/strategy.yaml` timeframes (`htf: M5, ltf: M1`) are not what the API uses
    (`api/signals.py:14-15` fetches H1/M5).
  - README (L109, L133) presents research packages as live architecture layers; actual
    runtime is strategy+execution+services only; README L468 also says
    `backend/research/` where the package is `backend/app/research/`.
- **Fix:** small corrections + a README accuracy pass; CORS via env (early, C-06);
  Alembic baseline decision (D-06); pin pytest-asyncio (A-03).

### P-13 — Silent exception swallowing / unguarded broker responses · [C] · low · small

- **Evidence:** `intelligence/logger.py:19-20` (`except Exception: pass` — dead code
  anyway, see P-06); `scalper/gold_multi_scalper.py:115-116` (command-listener loop
  swallows everything); `execution/engine.py:213-216` (silent skip of max-holding-time
  on parse failure); **unguarded `order_send` result dereferences**:
  `scalper/grid_martingale_bot.py:92`, `scalper/demo_scalper_engine.py:75`,
  `scalper/ultra_tick_scalper.py` (result fields read without None-checks) —
  `mt5.order_send` returning `None` raises `AttributeError` instead of a clean failure.
- **Fix:** log-and-continue (or fail loudly) at these sites; None-guard every
  `mt5.order_send` result at all 12 direct call sites.

### P-14 — Emergency stop cannot cross process boundaries · [C] · critical · medium *(new; review N/A→R-01, M-03)*

- **Evidence:** `RiskEngine.emergency_stop_active` is an instance attribute; every
  process (`uvicorn` API, `runner.py`, each bot/script) constructs its own engines.
  There is no file/DB/IPC mechanism for stop state.
- **Why it matters:** even with B-01, an operator's emergency stop stops only the API
  process's order path. The runner and bots — the paths most likely to be actually
  trading — remain unstoppable via the API.
- **Design decision (ADR-8):** a **stop-sentinel file** in a gitignored state directory
  (`STATE_DIR`, default `backend/state/`), written on trigger, removed on reset, and
  checked by `core/safety.ensure_trading_allowed()` and by `RiskEngine` evaluation in
  every process. Chosen over a DB flag because the default `DATABASE_URL` is
  **in-memory SQLite** (per-process), so a DB sentinel would not cross processes
  either.
- **Precise guarantees and limits (stated honestly):**
  - ✔ Blocks **new order submissions** in all processes that use the gate or adapter
    once the file exists; survives process restarts.
  - ✔ Cross-process **reset** works the same way (file removal).
  - ✘ Does **not** close already-open positions in bot processes — closing bot baskets
    remains a bot-command (`STOP`/manual) or MT5-terminal operation.
  - ✘ Does not stop bot event loops; it makes their order sends fail fast with a
    clear reason.
- **Fix:** B-05 implements the sentinel; the gate (B-03) and engines consume it; E-04
  drills it.

### P-15 — Two conflicting XAUUSD instrument specifications · [C] · high · medium *(new; review N-04/R-05)*

- **Evidence:** `scalper/instrument.py:32-45` defines XAUUSD as digits=3, point=0.001,
  pip_size=0.1, contract=100 (Exness-style 3-digit gold); `data/mt5_mock.py:8-20`
  defines XAUUSD as digits=2, point=0.01, tick_size=0.01, contract=100;
  `backtest/engine.py:47` invents a third heuristic (contract 100 vs 100000 by point
  size). `runner.calculate_spread_in_pips` derives pips from **digits**, while
  `strategy/engine.py:60-64` uses the spec's `pip_size` — two different pip semantics
  coexist.
- **Why it matters:** "single source of instrument truth" (ADR-4) is meaningless until
  precedence is defined; the original plan's "XAUUSD preserved bit-for-bit" claim is
  not well-defined across these environments.
- **Fix (B-02):** explicit precedence — broker `symbol_info` overrides the static spec
  for point/tick/contract/volume limits; `pip_size` is taken from
  `InstrumentSpecification` (canonical: gold 0.1, 5-digit FX 0.0001) with a
  digits-derived fallback only when no spec exists; `get_default_spec` no longer
  strips "M" (P-18). **Characterization tests are locked against current numeric
  outputs before any edit.** Trading-level math (SL/TP distances) already flows
  through the spec, so it is preserved bit-for-bit; the digits-based spread
  calculation in `runner.py`/`tick_engine.py` is unified onto pip semantics, which is
  a documented change to *displayed spread values* in the mock environment (spread
  gate defaults to disabled, so no trading-behavior change).

### P-16 — `RealMT5Adapter.send_order` discards caller's `magic`/`comment` · [C] · medium · small *(new; review N-02)*

- **Evidence:** `data/mt5_real.py:192` hard-codes `"magic": 100001`;
  `order_request.get("magic")` is never read, although `ExecutionEngine` (engine.py:108)
  and every bot pass one (888888, 777111, 999111, ...). `comment` is accepted but the
  bots' inline requests also hard-code their own.
- **Why it matters:** per-strategy attribution on the broker side is broken; a shared
  order-builder helper (C-03) is ineffective for the adapter path until fixed.
- **Fix:** `send_order` reads `magic`/`comment` from the request (default 100001 /
  existing default comment). Task C-07.

### P-17 — Position price update uses hard-coded fallback price · [C] · medium · small *(new; review N-06)*

- **Evidence:** `api/execution.py:30` uses `info.get("bid", 2400.0)`;
  `MockMT5Adapter.get_symbol_info` returns the spec dict which has **no `bid` key**
  (`mt5_mock.py:87-88`), so every position is marked to 2400.0 regardless of symbol.
- **Fix:** `MarketDataService.get_latest_price(symbol)` preferring adapter
  bid/ask, falling back to the last cached candle close (never a hard-coded constant).

### P-18 — `InstrumentSpecification.get_default_spec` mangles symbols · [C] · medium · small *(new; review N-07)*

- **Evidence:** `scalper/instrument.py:30` does `symbol.upper().replace("M", "")`,
  stripping *every* "M" (e.g., "XAUUSDm"→"XAUUSD" works by luck; "M100"→"100";
  symbols containing M elsewhere are mangled).
- **Fix:** strip only a **trailing** "M"/"m" suffix (`removesuffix("M")`), in B-02.

### Potential problems requiring further investigation (not acted on in this plan)

- **Min-lot clamp over-risk on small accounts** (`RiskEngine.calculate_position_size`
  clamps up to `min_volume`) — flagged in `PROFITABILITY_INVESTIGATION.md` (H3).
  Fix changes live sizing behavior — kept as an optional, config-gated task (D-05)
  requiring owner sign-off.
- **`config/risk.yaml` sets all circuit breakers to 0 (disabled)** — a documented
  decision ("MANUAL STOP ONLY", commit `ba0e9bb`). Preserved as-is by this refactor;
  explicitly *not* restored (see non-goals / R-15 note).
- **`context/timeframe_engine` includes the forming candle** in downstream bias
  inputs (research-only path; document, don't change).
- **165-test count vs CI environment parity:** verified locally (Python 3.12.10,
  Windows); CI runs ubuntu — should hold, not re-verified there.
- **Real-broker behavior coverage:** the A-02 baseline uses the mock adapter and
  therefore **cannot** capture real-broker behavior; endpoint contract diffing is
  valid only for mock-driven responses. Stated explicitly so nobody mistakes the
  baseline for live-broker ground truth.

### Explicitly *not* problems (considered and rejected)

- **"Rewrite the backend as a service-oriented architecture"** — unjustified: the
  runtime path is small, single-user, single-machine; MT5 is a local Windows resource.
- **Replacing the mock adapter pattern** — good design; enables the broker-free suite.
- **Removing the 5 MT5 bots or the demo trader script** — product features; the fix is
  gating + de-duplicated plumbing, not deletion.
- **Bulk-renaming research packages** — churn without payoff (P-11).
- **Adding a task queue / Celery / Redis** — nothing needs it; Redis in compose is
  unused and should be removed.

---

## 4. Prioritized implementation plan

27 tasks across five phases (A-01…E-06 including B-05 and C-07). Phases are
dependency-ordered; each task has a full entry (with rollback note) in
[`REFACTORING_TASKS.md`](REFACTORING_TASKS.md).

### Phase A — Preparation (small)

| Task | Description | Size |
|---|---|---|
| A-01 | Create `refactor/` working branch off `main`; commit planning docs; agree commit conventions. | small |
| A-02 | Baseline capture: pytest output, `npm run build` result, enumerated endpoint response samples (captured via `app.routes`, not a hand count) into `docs/baseline/`. Note: mock-adapter data only; real-broker behavior is not capturable in a baseline. | small |
| A-03 | Tooling: pin `pytest-asyncio<0.24` in `requirements.txt`; add ruff config (report-only until Phase D). | small |

### Phase B — Foundational refactoring

| Task | Addresses | Size |
|---|---|---|
| B-01 | **Shared application state + DI + explicit RiskEngine injection** (P-01 in-process, P-07): container in `main.py` lifespan; `ExecutionEngine.__init__(adapter, risk_engine=None)` accepts the shared instance; routers use `Depends`. In-process scope only — cross-process is B-05. | medium |
| B-02 | **Instrument-spec reconciliation + pricing primitives** (P-04 foundation, P-15, P-18): precedence rule, `M`-suffix fix, canonical `pip_size`, characterization tests locked before edits, `core/pricing.py` helpers, migrate `runner.calculate_spread_in_pips` + `tick_engine` pip math in the same task. | medium |
| B-03 | **Destination-aware safety gate** (P-02): `core/safety.py` with the ADR-3 truth table (mode × destination × sentinel); wired into `ExecutionEngine` and **all 6 order-path files / 12 call sites**. Intended behavior change documented. | medium |
| B-04 | **Dead-code removal** (P-06): delete `fusion_2.0.py`, root `app/`, `scalper/config.py`, `intelligence/logger.py` (unimportable — no wire-in option). | small |
| B-05 | **Cross-process stop sentinel** (P-14): `core/stop_state.py`; sentinel file under gitignored `STATE_DIR`; written by `RiskEngine.trigger/reset`; read by gate and engines. | small |

### Phase C — Module and feature refactoring

| Task | Addresses | Size |
|---|---|---|
| C-01 | Execution/risk numeric correctness (P-04, P-17): spec-based PnL in `execution/engine.py`, `scalper/position_manager.py`, `gold_multi_scalper.py` (+ `cost_analyzer.py`, `adaptive_exit_v2.py`); `backtest/engine.py` symbol-info from spec; `get_latest_price` fix; broker `FAILED` → HTTP 502 (**owned by C-01 only**, review R-07). | medium |
| C-02 | Backtest correctness & determinism (P-03, P-09): `engine.last_trades` mechanism; Monte Carlo endpoint passes real trades; seed `TickMonteCarloSimulator`; deterministic trade IDs. **Sequenced after C-01 only to avoid conflicting edits to `backtest/engine.py`/`api/backtest.py`; otherwise independent.** | small |
| C-03 | MT5 bot plumbing consolidation (P-13): `scalper/mt5_orders.py` shared order/close builders + retcode hints + pip-scale resolution; None-guards at every `mt5.order_send` result. Includes `scripts/run_demo_trader.py`. | medium |
| C-04 | Research common utilities (P-08, first tranche): `research/common/` + `scripts/_bootstrap.py` (import-order-safe); hash helper keeps lenient default with explicit `strict` option (documented decision); FDR; shared tick fetch. Rewire 9 engines + ~12 scripts mechanically. | medium |
| C-05 | Frontend cleanup (P-10): `lib/api.ts` client with `NEXT_PUBLIC_API_URL` + optional `NEXT_PUBLIC_API_TOKEN` Authorization header (pairs with D-01); typed models; error banners; destructive-action confirmations; mode badge from `/api/health`. | medium |
| C-06 | Config/infra consistency (P-12, R-13): **CORS origin restriction lands here** (`CORS_ORIGINS` env, default `http://localhost:3000`); `.env.example` DEMO + `AUTOMATION_API_TOKEN`/`STATE_DIR` entries; remove Redis service; README corrections (runtime layers, `backend/app/research/` path, timeframes). | small |
| C-07 | Adapter order-request fidelity (P-16): `RealMT5Adapter.send_order` honors caller `magic`/`comment`. | small |

### Phase D — Quality improvements

| Task | Addresses | Size |
|---|---|---|
| D-01 | API token hardening (P-05): optional bearer token on mutating endpoints when `APP_ENV=production` and `AUTOMATION_API_TOKEN` set; frontend compatibility relies on C-05's header support; unified error envelope for 4xx/5xx (success shapes unchanged; `FAILED→502` is owned by C-01, **not** here). | small |
| D-02 | Regression tests for new seams: emergency-stop propagation (in-process); cross-process sentinel simulation (file written "by another process" → gate refuses); injected-RiskEngine wiring test; gate truth-table tests (mode × destination); instrument characterization tests; Monte Carlo responsiveness/determinism; `/run` contract test; magic-propagation test; position-price test. | medium |
| D-03 | Error-handling sweep (P-13): log-instead-of-swallow at cited sites; None-guards for any `order_send` sites not already covered by C-03 (e.g., `demo_scalper_engine.py:75` if not restructured there). | small |
| D-04 | CI additions: ruff check; report-only mypy trial; docker-compose smoke test (build + health). | small |
| D-05 | Optional (owner sign-off): min-lot over-risk guard, config-gated, default off. | small |
| D-06 | Alembic decision: baseline migration **or** documented `create_all` + credential removal from `alembic.ini`. | small |

### Phase E — Final verification

| Task | Description |
|---|---|
| E-01 | `pytest tests -q` — 165 prior tests pass (updated only where an intended change is documented) + new D-02 tests pass. |
| E-02 | `npm run build` + manual walkthrough of all 6 dashboard pages against a locally running backend. |
| E-03 | API contract diff vs `docs/baseline/` for every endpoint captured in A-02. Permitted diffs only: Monte Carlo simulation content (C-02), failure-path status codes (C-01), security/CORS headers. `/api/backtest/run` JSON must be **unchanged** (contract test). |
| E-04 | Safety drill: (1) API emergency stop → `POST /api/execution/orders` rejected; (2) **sentinel written independently ("another process") → all gated paths refuse, including a simulated bot call and `ExecutionEngine`**; (3) reset → paths re-enabled; (4) every order-send entry point calls the gate (unit-verified per path, 6 files); (5) explicit statement in the drill output that the sentinel blocks *new entries* only — open bot positions still require bot-command/manual closure. |
| E-05 | Grep audits: single `verify_dataset_hash` definition; single `compute_fdr`; no `fusion_2.0`/root `app/` references; no module-level `MarketDataService(` in `app/api/`; no unseeded `np.random.choice` in `app/backtest/`; no hard-coded contract literals in PnL paths; **`mt5.order_send` audit across `app/` and `scripts/`: every occurrence is inside `data/mt5_real.py` or immediately preceded by the gate**. |
| E-06 | `docker compose up --build` smoke test; confirm Redis removal didn't break startup. |

---

## 5. Risks and mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| Response-shape drift breaking dashboard/tests | Medium | Phase-A baseline capture (via `app.routes` enumeration); contract diff in E-03; tests updated only where a change is documented |
| PnL-math change altering backtest numbers | High (intended) | Scope documented (P-04); characterization tests locked first (B-02); XAUUSD trading-level math preserved; forex outputs corrected |
| XAUUSD spec conflict causing silent spread/pip drift | Medium | Explicit precedence (ADR-4); pip migration of `runner`/`tick_engine` in one task (B-02) with before/after characterization tests |
| Emergency-stop false confidence | Medium | Honest scoping: B-01 fixes API process; B-05 sentinel fixes new-order blocking cross-process; E-04 drills both; limits (open positions not force-closed) documented in ADR-8 |
| Safety-gate breaking legitimate paper workflows | Medium | Truth-table tests prove mock execution stays valid in PAPER/BACKTEST; only real-broker sends are restricted |
| Research artifact reproducibility broken by consolidation | Medium | Per-phase test after each rewire; hash helper defaults to lenient semantics (strict opt-in, documented) |
| pytest-asyncio/fixture breakage | Low | Pin <0.24 first (A-03) |
| Scope creep into strategy/research logic | Medium | Hard boundary declared in §1; every task's "behavior preserved" section enforced in review |
| Production dashboard outage when token enabled | Low | C-05 ships token header support before D-01 can enforce; limitation documented |
| Single-commit-everything mega PR | Medium | Per-task commits on `refactor/` branch; CI green per commit; each task carries a rollback note |

## 6. What was and wasn't inspected

- **Directly read & verified:** `core/`, `models/`, `api/` (all 9 routers), `execution/`,
  `risk/`, `data/`, `services/`, `strategy/engine.py`, `runner.py`, `main.py`,
  `backtest/engine.py`, `backtest/walk_forward.py`, `backtest/metrics.py`,
  `scalper/{instrument,position_manager,demo_scalper_engine}.py`,
  `intelligence/logger.py`, `scripts/run_demo_trader.py`, conftest and representative
  tests, config files, CI, compose, README, PROFITABILITY_INVESTIGATION.md.
- **Agent deep-dived (all files read; key claims spot-checked):** `intelligence/`,
  `context/`, `fusion/`, `regime/`, `information/`, `scalper/` (remaining files),
  `swing/`, `backtest/` (remaining), `research/`, all 39 scripts.
- **Verified for this revision:** 6 order-path files / 12 direct `mt5.order_send`
  calls; 8 `MarketDataService` instantiations in `app/api/`; `BacktestMetricsReport`
  field list; the XAUUSD spec conflict (`instrument.py` vs `mt5_mock.py`);
  `run_demo_trader.py`'s `--enable-demo` bypass; `logger.py` `NameError`; the
  `"M"`-strip; the 3 phase tests embedding the hash fallback; 39 script files;
  `walk_forward.py:92` unseeded RNG.
- **Not verified line-by-line:** every script's full body (structural sampling), and
  each of the 52 test files in full. Affected tasks (C-03, C-04) include
  "confirm-before-edit" steps.
- **Not executed:** `npm run build`, docker compose, any live MT5 operation.
  Task A-02 captures these baselines before implementation.
