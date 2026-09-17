# Refactoring Tasks — Autonomous Trader

> Status: Phase 1 planning document, **REVISED** after independent review
> (`docs/REFACTORING_PLAN_REVIEW.md`). Companion to [`REFACTORING_PLAN.md`](REFACTORING_PLAN.md)
> and [`REFACTORING_ARCHITECTURE.md`](REFACTORING_ARCHITECTURE.md).
> **No source code has been modified.** All paths relative to repo root.
>
> **This revision:** 27 tasks (A-01…E-06, including new B-05 and C-07). Changes:
> B-01 requires explicit `RiskEngine` injection and states in-process scope; B-02
> absorbs instrument-spec reconciliation + characterization tests; B-03 reworked to
> mode × destination semantics with full 6-file/12-call coverage; C-01 owns
> `FAILED→502` exclusively and its file list is aligned; C-02 re-specified via
> `engine.last_trades`; C-04 uses `scripts/_bootstrap.py` and a lenient-default hash
> helper; D-01 drops the `FAILED→502` overlap; D-02/D-03/E-04/E-05 extended; rollback
> note added to every implementation task A–D (R-16).
>
> Conventions for the implementing agent:
> - One task = one (or a few small) commits on the `refactor/` branch; message prefix `refactor:`/`fix:`/`test:`/`chore:`.
> - Every task: run `pytest tests -q` (from `backend/`) before finishing; frontend tasks also run `npm run build` (from `frontend/`).
> - "Behavior preserved" sections are contractual: if you must deviate, stop and document why in the PR.
> - Every Phase A–D task lists a **Rollback** line: `git revert` of the task's commits restores the prior state; no task except D-06 introduces schema/data migrations. Phase E tasks are read-only verification drills and have no rollback by design.

---

## Phase A — Preparation

### A-01 Branch & commit baseline
- **Objective:** create the working branch and record planning artifacts.
- **Affected:** git only.
- **Change:** `git checkout -b refactor/consolidation` from `main`; commit the
  `docs/REFACTORING_*.md` files (including this revision).
- **Deps:** none. **Risk:** none. **Rollback:** delete branch / revert docs commit.
- **Verification:** `git status` clean; branch exists.
- **Done when:** branch exists (pushed or local) and docs committed.

### A-02 Capture behavioral baseline
- **Objective:** freeze current behavior as a comparison target.
- **Affected:** `docs/baseline/` (new), no source.
- **Change:** enumerate all routes programmatically (`app.routes`) — the README table
  lists 19 endpoints; capture JSON responses of every one into `docs/baseline/api_*.json`
  (discovered routes win over hand counts); save `pytest tests -q` output; run
  `npm run build` and save result.
- **Scope caveat (explicit):** the backend runs on the Mock adapter, so the baseline
  captures mock-driven responses only; it **cannot** capture real-broker behavior.
  It is valid for response-*shape* diffing, not live-broker ground truth.
- **Deps:** A-01. **Risk:** none (read-only against a local run). **Rollback:** revert
  docs commit.
- **Verification:** baseline files committed.
- **Done when:** every enumerated endpoint's sample + test output + build output exist.

### A-03 Align tooling pins
- **Objective:** eliminate the pytest-asyncio version trap before any other change.
- **Affected:** `backend/requirements.txt`.
- **Change:** `pytest-asyncio>=0.23.5` → `pytest-asyncio>=0.23.5,<0.24` (aligns with
  CI's runtime pin).
- **Preserved:** all test behavior. **Deps:** none. **Risk:** none.
- **Rollback:** revert requirements change.
- **Verification:** `pytest tests -q` → 165 passed.
- **Done when:** CI pin and requirements pin agree.

---

## Phase B — Foundational

### B-01 Shared application state + DI + explicit RiskEngine injection
- **Objective:** one `RiskEngine`, one `MarketDataService`, one `ExecutionEngine` per
  **API process**; routers receive services via `Depends`; the API emergency stop
  blocks the API order path.
- **Scope (precise):** in-process only. `runner.py` and bot scripts are separate
  processes and are **not** affected by API-triggered stops — that gap is B-05/ADR-8,
  not this task.
- **Affected:** `backend/app/main.py` (lifespan builds `AppState` on `app.state`),
  new accessors (e.g. `app/core/state.py` or `app/api/deps.py`: `get_execution_engine`,
  `get_risk_engine`, `get_market_service`), **all 8 routers with module-level
  `MarketDataService()`** (`execution.py`, `backtest.py`, `market.py`, `liquidity.py`,
  `setups.py`, `risk.py`, `signals.py`, `structure.py`) plus `signals.py`'s
  `StrategyEngine` and `health.py`'s import-time adapter connect,
  `backend/app/execution/engine.py` (**`__init__(self, adapter=None, risk_engine=None)`
  — reuses the injected engine; only builds a default when none is provided**),
  `backend/app/runner.py` (inject the same shared instance it builds), `backend/tests/conftest.py`
  (dependency overrides for every accessor), `backend/tests/test_health.py`,
  `backend/tests/test_risk_engine.py`, `backend/tests/test_execution.py`.
- **Behavior preserved:** every endpoint's success-path response shape and semantics;
  mock-adapter default behavior; health endpoint content; `ExecutionEngine` standalone
  construction still works for direct-instantiation tests.
- **Intended change:** `POST /api/system/emergency-stop` affects the engine used by
  `POST /api/execution/orders` (regression test in D-02). MT5 connection attempt moves
  from `health.py` import time into lifespan.
- **Deps:** A-02, A-03.
- **Risks:** import-time side effects move to lifespan — verify `test_health.py`
  (ASGITransport does not run lifespan; overrides required); router tests that
  imported singletons directly must switch to overrides.
- **Rollback:** revert the task's commits; singletons reappear; no data migration.
- **Verification:** pytest green; new propagation test (D-02); manual drill (E-04).
- **Done when:** grep finds **no** module-level `MarketDataService(` instantiation in
  `app/api/` (8 routers verified) and no `RiskEngine()` construction inside
  `ExecutionEngine`; emergency-stop propagation test passes.

### B-02 Instrument-spec reconciliation + pricing primitives
- **Objective:** one precedence-defined source of instrument math, with current
  behavior locked by characterization tests before anything changes (P-04, P-15, P-18).
- **Step 1 — characterization (before any edit):** add tests asserting the **current**
  numeric outputs of: `runner.calculate_spread_in_pips` (gold digits-3 rule and
  digits-5 rule), `strategy/engine._scalp_levels` for XAUUSD/EURUSD, mock-adapter
  spread path, and `backtest/engine` contract heuristic. These tests define the
  before-state.
- **Step 2 — reconciliation:**
  - `backend/app/scalper/instrument.py`: fix `get_default_spec` to strip only a
    **trailing** "M"/"m" (`removesuffix`), not all "M" characters (P-18).
  - Document the precedence rule (ADR-4): broker `symbol_info` overrides the static
    spec for point/tick/contract/volume; `pip_size` is canonical from the spec
    (gold 0.1, 5-digit FX 0.0001, JPY FX 0.01); digits-derived fallback only for
    unknown symbols. The mock adapter's digits=2 XAU spec remains the mock
    environment; it is *not* silently rewritten.
  - `backend/app/core/pricing.py` (new): `pip_size(symbol, point_size=None)`,
    `pnl(price_diff, volume, spec_or_info)`, `pips_to_price(pips, spec)`,
    `spread_in_pips(bid, ask, spec)` — helpers only; **no consumer changes in this
    task except the two pip-math sites below**, so the change is reviewable.
  - Migrate `app/runner.py:11-20` (`calculate_spread_in_pips`) and the pip-scale
    logic in `app/scalper/tick_engine.py` onto the shared helper **in this task** so
    pip semantics change exactly once, together (review R-05).
- **Behavior preserved:** XAUUSD *trading-level* SL/TP math (already spec-driven)
  bit-for-bit; all public signatures; mock environment spec values unchanged.
- **Intended change (documented):** displayed spread values in the mock-gold
  environment may change (digits-based → pip_size-based); spread gate is disabled by
  default, so no trading-behavior change. Characterization tests updated *in the same
  commit* with the reason.
- **Deps:** A-02 (baseline for diffing). Independent of B-01.
- **Risks:** silent pip/spread drift — mitigated by the Step-1 lock and same-commit
  test updates.
- **Rollback:** revert commits; helpers removed; no data migration.
- **Verification:** pytest green; characterization tests exist and either match
  current output or document the deliberate change; EURUSD/NAS100 expected values
  asserted exactly.
- **Done when:** helpers exist with tests; precedence documented in code + ADR-4;
  `replace("M", "")` gone from `instrument.py`.

### B-03 Destination-aware safety gate
- **Objective:** every order-sending path enforces the mode × destination model
  (ADR-3 truth table) and the cross-process stop sentinel (P-02, P-14).
- **Affected (new):** `backend/app/core/safety.py` —
  `ensure_trading_allowed(destination: str, *, account_trade_mode: int | None = None, intent: str = "entry") -> None`
  raising `SafetyViolation`; consults `core/stop_state.is_active()` first for
  entries. Close/reduce sends pass `intent="close"` and bypass only the
  sentinel check (Phase 2 fix H-1); unknown modes/destinations/intents fail
  closed (N2-M1).
- **Affected (edit):** `backend/app/execution/engine.py` (gate call inside
  `execute_signal`, replacing the inline LIVE check; sentinel read as
  defense-in-depth); and **all six order-path files / twelve `mt5.order_send` call
  sites** (verified by grep), gate called before the first send of each run:
  `scalper/autonomous_scalper_daemon.py` (L130, L166), `scalper/demo_scalper_engine.py`
  (L73, L113), `scalper/ultra_tick_scalper.py` (L86, L119),
  `scalper/gold_multi_scalper.py` (L331, L440), `scalper/grid_martingale_bot.py`
  (L92, L162, L200), `scripts/run_demo_trader.py` (L71 — its `--enable-demo` path
  requires `EXECUTION_MODE=DEMO` + demo account, or `LIVE`+flags, going forward).
  Line numbers are current-tree references — **re-confirm each site at edit time**.
- **Behavior preserved:** mock/paper execution via `MockMT5Adapter` remains fully
  allowed in `PAPER`, `BACKTEST`, `DEMO`, `LIVE` (truth table); bot strategy logic
  untouched; `config.py` boot validator unchanged.
- **Intended behavior changes (documented, §2.6 register):** direct real-broker sends
  refused in `PAPER`/`BACKTEST`; `DEMO` real sends require `account_trade_mode == 0`
  (bots/`run_demo_trader.py` pass `adapter.get_account_info().get("trade_mode")` when
  available); sentinel blocks gated *entries* when triggered while close/reduce
  sends stay allowed (§2.6 #14); grid orders carry a wide broker disaster stop
  (§2.6 #15); the API adapter is mode-aware (§2.6 #20).
- **Deps:** B-05 (sentinel exists before the gate consumes it).
- **Risks:** breaking legitimate paper tests — mitigated by the truth table (mock is
  always allowed) and explicit tests.
- **Rollback:** revert commits; bots return to ungated behavior (unsafe; do not deploy
  reverted state to live without re-assessment — note this in the rollback itself).
- **Verification:** new tests: truth table per cell; every order-path file refuses in
  illegal mode/destination combos; mock PAPER execution remains valid; sentinel-blocked
  path returns a clear rejection.
- **Done when:** gate tests pass; E-05 grep shows every `mt5.order_send` site in
  `app/`+`scripts/` is inside `data/mt5_real.py` or gate-preceded.

### B-04 Dead-code removal
- **Objective:** remove verified-dead duplicates (P-06).
- **Affected (delete):** `backend/app/intelligence/fusion_2.0.py` (byte-identical to
  `fusion_2_0.py`), root-level `app/` (orphan package, tracked in git),
  `backend/app/scalper/config.py` (zero references),
  `backend/app/intelligence/logger.py` — **delete by default**: it has zero references
  *and is not importable* (`NameError: Optional` at line 9), so the original "wire it
  in" alternative is not a drop-in option and is **removed from this task** (review
  R-09). If anyone wants signal logging later, it must be built fresh with proper
  error handling.
- **Behavior preserved:** everything (no live references — verified by import search;
  re-verify before deleting).
- **Deps:** A-01. **Risk:** trivial. **Rollback:** revert commit (files restored).
- **Verification:** pytest green; `git grep -n "fusion_2\.0\|SmallAccountDemoConfig\|HistoricalSignalLogger"`
  empty; `pytest --collect-only` succeeds (import-collection check).
- **Done when:** files gone; grep clean; README project-structure section updated if it
  lists removed items.

### B-05 Cross-process stop sentinel
- **Objective:** make emergency stop effective across processes (P-14, ADR-8).
- **Affected (new):** `backend/app/core/stop_state.py` —
  `trigger(reason: str)`, `reset()`, `is_active() -> str | None` over
  `STATE_DIR/EMERGENCY_STOP.json`; `STATE_DIR` added to `config.py`
  (env `AUTOTRADER_STATE_DIR`, default `<repo>/backend/state`), gitignored, created on
  demand.
- **Affected (edit):** `backend/app/risk/engine.py` — `trigger_emergency_stop` /
  `reset_emergency_stop` also call `stop_state.trigger/reset` (in-memory flags and all
  response shapes unchanged); `.gitignore` for the state dir; `.env.example` entry.
- **Guarantees/limits:** per ADR-8 — blocks new gated orders in all processes; does
  not close open bot positions or terminate loops; persists across restarts.
- **Deps:** none (before B-03, which consumes it).
- **Risks:** file-permission/AV quirks on Windows — use plain write/rename with
  explicit error logging; missing dir handled.
- **Rollback:** revert commits; sentinel file may remain on disk (delete manually).
- **Verification:** tests: trigger → `is_active()` returns reason; reset → `None`;
  a *fresh* `RiskEngine` in a new interpreter sees the sentinel (cross-process
  simulation); sentinel blocks a simulated order path (with B-03's test).
- **Done when:** `RiskEngine` writes/removes the sentinel; tests prove cross-process
  visibility.

---

## Phase C — Module and feature refactoring

### C-01 Execution & risk numeric correctness
- **Objective:** remove hard-coded ×100 contract multiplier and the fallback-price bug
  (P-04, P-15, P-17); own the `FAILED→502` change exclusively (review R-07).
- **Affected:** `backend/app/execution/engine.py` (PnL at ~L195, ~L244),
  `backend/app/scalper/position_manager.py` (L59, L94),
  `backend/app/scalper/gold_multi_scalper.py` (L152, L158),
  `backend/app/intelligence/cost_analyzer.py` (L45, L48),
  `backend/app/scalper/adaptive_exit_v2.py` (L34),
  `backend/app/backtest/engine.py` (symbol-info heuristic at L44-51 → spec/precedence),
  `backend/app/api/backtest.py` (passes spec-derived info),
  `backend/app/services/market_data.py` (new `get_latest_price`), and
  `backend/app/api/execution.py` (L30 uses `get_latest_price` instead of
  `info.get("bid", 2400.0)`; broker `FAILED` status → `HTTPException 502` — **this
  task is the single owner of that change; D-01 must not repeat it**).
- **Behavior preserved:** XAUUSD results identical (asserted by characterization tests
  from B-02); all endpoint success shapes; signal generation untouched.
- **Intended change:** forex PnL/cost numbers corrected (~×1000); mock position
  marking uses real/candle prices (§2.6 #5/#7/#8).
- **Deps:** B-02 (helpers + characterization). **Risks:** test expectations on forex
  PnL; mock adapter specs are XAU-shaped — forex tests must use EURUSD specs
  explicitly.
- **Rollback:** revert commits; numeric behavior returns to prior (documented-defect)
  state.
- **Verification:** new tests: EURUSD PnL = `diff × 100000 × vol`; NAS100 contract=1;
  XAUUSD regression unchanged; `POST /api/execution/orders` with a broker `FAILED`
  response returns 502; position endpoint returns non-2400 prices for EURUSD (N-06).
- **Done when:** `grep -rn "100\.0 \* (pos\.)?volume\|price_diff \* 100"` returns no
  hits in `app/` (all such sites converted, XAU included); suite green.

### C-02 Backtest correctness & determinism
- **Objective:** fix Monte Carlo endpoint (P-03) and determinism gaps (P-09) via the
  non-breaking trades-access mechanism (ADR-5b).
- **Affected:** `backend/app/backtest/engine.py` (`run` sets
  `self.last_trades: List[BacktestTradeRecord]`; no signature/return change; trade IDs
  deterministic — e.g. `f"BT_{symbol}_{i}_{direction}"`),
  `backend/app/api/backtest.py` (monte-carlo endpoint passes
  `engine.last_trades` → `BacktestTradeRecord`s into `MonteCarloSimulator`;
  `POST /api/backtest/run` handler untouched), `backend/app/backtest/walk_forward.py`
  (L92: `run_monte_carlo(..., seed: int = 42)`; use
  `np.random.default_rng(seed).choice`).
- **Behavior preserved:** `/api/backtest/run` response JSON **byte-identical except**
  trade IDs (P-09 change) — add a contract test; metrics math unchanged.
- **Intended change:** monte-carlo endpoint returns a simulation over actual trades;
  walk-forward reproducible (§2.6 #9/#10).
- **Deps:** C-01 — **sequencing reason:** both edit `backtest/engine.py`/`api/backtest.py`;
  the Monte Carlo fix is otherwise independent of C-01's substance (review §4).
- **Risks:** low; mock candles are deterministic, making responsiveness assertable.
- **Rollback:** revert commits; endpoint returns empty-trade simulation again
  (documented defect returns).
- **Verification:** new tests: (a) `/run` JSON unchanged except `trade_id` values;
  (b) monte-carlo over a trade-producing backtest yields nonzero/consistent
  `median_net_profit` and `probability_of_ruin` responding to trade content;
  (c) two consecutive walk-forward simulations produce identical output.
- **Done when:** all three tests pass; baseline diff shows only permitted changes.

### C-03 MT5 bot plumbing consolidation
- **Objective:** stop six-fold duplication of broker plumbing while keeping each bot's
  strategy intact (P-13 scope).
- **Affected (new):** `backend/app/scalper/mt5_orders.py` —
  `build_market_order(...)`, `build_close_request(...)`, `pip_scale_for(symbol)`,
  `broker_reject_hint(retcode)`; all delegating `magic`/`comment` through
  (paired with C-07 so the adapter honors them).
- **Affected (edit):** the five `scalper/` bots' order/close-request blocks (current
  sites: daemon L117-129/L130, demo L100-112/L73+L113, ultra L106-118/L86+L119, gold
  L318-330/L331+L440, grid L187-199/L92+L162+L200; pip-scale sites daemon L70, demo
  L49, ultra L36, gold L235, grid L53) **and `scripts/run_demo_trader.py`** (request
  at L56-69); None-guard every `mt5.order_send` result.
- **Behavior preserved:** each bot's entry/exit logic, magic numbers, defaults,
  command-listener UX, output format; identical request payloads.
- **Intended change:** identical payloads produced via shared helpers; gate calls from
  B-03 remain in place.
- **Deps:** B-03 (gate already wired), A-02.
- **Risks:** subtle payload differences between bots (deviation 10 vs 20, filling
  mode) — parameterize rather than unify silently; **confirm per-bot payload equality
  with a quick golden-dict test before deleting duplicated code** (some bots were
  edited after the copy; `run_demo_trader.py` uses deviation 20).
- **Rollback:** revert commits; bots return to inline plumbing.
- **Verification:** per-bot golden request test asserting the same dict the old inline
  code produced; all bot tests green; `run_demo_trader.py` gated + None-guarded.
- **Done when:** duplicated blocks removed; all bot tests green; `run_demo_trader.py`
  covered by the gate (verified in E-05 audit).

### C-04 Research common utilities (first tranche)
- **Objective:** single implementations of the most-duplicated research helpers (P-08),
  with import-order and hash-semantics issues resolved (review R-10/R-11).
- **Affected (new):** `backend/app/research/common/__init__.py`, `dataset_hash.py`
  (`verify_dataset_hash(data, strict: bool = False)` — **default keeps the current
  lenient version-"2.0.0" fallback; strict is opt-in and the tightening decision is
  recorded explicitly, not applied silently**), `statistical_tests.py`
  (`compute_fdr_correction`), `splits.py`, `metrics.py`, `mt5_ticks.py`
  (`fetch_real_ticks`), and **`backend/scripts/_bootstrap.py`** — a thin module at
  `scripts/` level that performs the `sys.path` insert (and optional venv
  site-packages injection) *before* any `app.*` import; scripts import it first. This
  avoids the circularity of a bootstrap helper living inside the package it must make
  importable.
- **Affected (edit):** 9 engines' `verify_dataset_hash` (phase28/29/30/34/35/36,
  final_audit, market_state, macro_futures), `feature_discovery/statistical_testing.py`,
  `macro_futures/macro_futures_engine.py`, ~12 scripts' `fetch_real_ticks`, the
  5 venv-injecting runner scripts. **Note:** tests `test_phase31`, `test_phase32`,
  `test_phase36` embed the same fallback — leave them passing under the lenient
  default (no test edits required for this tranche).
- **Behavior preserved:** every phase engine's outputs identical where inputs
  identical (lenient default); artifact files untouched; scripts still runnable via
  `python scripts/run_phaseNN*.py` from `backend/`.
- **Deps:** B-04 (greps clean).
- **Risks:** reproducibility of published artifacts — each engine rewired in its own
  commit, verified by that phase's existing test; bootstrap must run before imports.
- **Rollback:** revert commits per rewire.
- **Verification:** full suite after each rewire; at least one script demonstrably
  uses `_bootstrap.py` and runs green; final greps: exactly one
  `verify_dataset_hash` definition, one `compute_fdr_correction` definition.
- **Done when:** phase tests green and duplication greps clean; strict-mode decision
  documented in the task's commit message.
- **Note (deferred):** consolidating the ≥6 split implementations into one
  configurable function is follow-up material; this tranche covers
  hash/FDR/ticks/bootstrap/metrics only.

### C-05 Frontend cleanup
- **Objective:** config-driven API base, typed responses, visible errors, confirmation
  on destructive actions, honest mode badge, **and optional auth-header support**
  (P-10; pairs with D-01, review R-08).
- **Affected:** `frontend/lib/api.ts` (new), all 6 pages in `frontend/app/`,
  `frontend/package.json` (remove `recharts` only after grep confirms unused).
- **Behavior preserved:** visual layout, polling intervals, route structure, all
  current features.
- **Intended change:** `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`);
  `NEXT_PUBLIC_API_TOKEN` — when set, `lib/api.ts` sends `Authorization: Bearer …`
  on every request (satisfies D-01's token gate); minimal response types replace
  `useState<any>`; error banners replace console-only swallowing; `confirm()`-style
  guard before emergency-stop, close-all, close-position; header badge reflects
  `/api/health.execution_mode`.
- **Deps:** A-02 (baseline build). **Risks:** UI regressions — keep JSX structure;
  build type-checks.
- **Rollback:** revert commits; pages return to prior behavior.
- **Verification:** `npm run build`; manual walkthrough of 6 pages; with a token set
  on the backend (dev simulation), dashboard requests succeed with the header.
- **Done when:** no hardcoded `localhost:8000` outside `lib/api.ts`; no destructive
  POST without confirmation; token header wired; build green.

### C-06 Config/infra consistency (CORS restriction lands here — review R-13)
- **Objective:** reconcile documented-vs-actual config (P-12) and close the
  wildcard-CORS exposure window early rather than in Phase D.
- **Affected:** `backend/app/core/config.py` (add `CORS_ORIGINS: str =
  "http://localhost:3000"`, `STATE_DIR: Path`, `AUTOMATION_API_TOKEN: Optional[str]`),
  `backend/app/main.py` (CORS from `settings.CORS_ORIGINS`, comma-split — replaces
  `allow_origins=["*"]` **in this task, not D-01**),
  `.env.example` (DEMO mode choice; new vars), `docker-compose.yml` (remove unused
  Redis service + dependency condition; pass `CORS_ORIGINS` env), README corrections
  (runtime layer table, `backend/app/research/` path at L468, `backend/app/api/`
  router count, timeframe note for `/api/strategy/signals` H1/M5 vs yaml M5/M1).
- **Behavior preserved:** all trading behavior; local dev flow (default origin
  includes `localhost:3000`).
- **Intended change:** wildcard-with-credentials eliminated at this point (§2.6 #11).
- **Deps:** none. **Risk:** low — a same-machine browser page from another origin
  could no longer call the API (that is the point).
- **Rollback:** revert commits; wildcard CORS returns (flag as unsafe in the revert).
- **Verification:** test asserting CORS headers echo a configured origin and never
  `*` with credentials; `docker compose config` parses.
- **Done when:** `.env.example`, compose, config, and README agree; CORS test green.

### C-07 Adapter order-request fidelity (magic/comment)
- **Objective:** `RealMT5Adapter.send_order` honors the caller's `magic`/`comment`
  (P-16; review N-02) so per-strategy attribution works and C-03's shared builder is
  effective on the adapter path.
- **Affected:** `backend/app/data/mt5_real.py` (`send_order`: read
  `order_request.get("magic", 100001)` and `comment` passthrough),
  `backend/app/execution/engine.py` (no change needed — it already passes `magic`).
- **Behavior preserved:** default magic `100001` when none supplied; all other request
  fields; retcode semantics.
- **Intended change:** supplied `magic`/`comment` now reach the broker request
  (§2.6 #13).
- **Deps:** none (independent). Pair with C-03 review to confirm the combined payload
  path is coherent.
- **Risk:** low. **Rollback:** revert commit.
- **Verification:** new test: a request with `magic=888888, comment="X"` reaches
  `mt5.order_send` with those values (mock the module or stub the adapter boundary);
  default path unchanged.
- **Done when:** test passes; `grep "magic": 100001` shows only the default fallback.

---

## Phase D — Quality improvements

### D-01 API token hardening
- **Objective:** optional production token gate on dangerous endpoints (P-05; review
  R-08). CORS is **already** restricted by C-06; this task adds the token only.
- **Affected:** new `backend/app/api/deps.py` (bearer-token dependency; enforced only
  when `APP_ENV=production` **and** `AUTOMATION_API_TOKEN` set), applied to `POST`
  endpoints in `execution.py` and `risk.py` (`emergency-stop`,
  `reset-emergency-stop`, `orders`, `close-all`, `positions/{id}/close`).
  README Safety Model section updated; **explicit note** that the bundled dashboard
  supports the token via `NEXT_PUBLIC_API_TOKEN` (C-05), and that production
  deployments without the token configured must document a reverse proxy or accept
  the exposure in writing.
- **Behavior preserved:** all success-path response shapes; local dev defaults open.
- **Non-scope:** the `FAILED→502` change belongs to C-01 (R-07) — not here.
- **Deps:** B-01 (router wiring), C-05 (frontend header support), C-06 (env entries).
- **Risk:** low; production misconfig could lock the dashboard out — mitigated by the
  C-05 header and the documented workflow.
- **Rollback:** revert commits; endpoints return to unauthenticated (flag in revert).
- **Verification:** tests: token enforced when prod+token set (with and without the
  header); open in dev; C-05's end-to-end check covers dashboard parity.
- **Done when:** tests pass; README Safety Model section describes the gate and the
  token/proxy decision.

### D-02 Regression tests for the new seams
- **Objective:** make the fixed failure modes permanently visible (review §5 list).
- **Affected (new/updated) in `backend/tests/`:**
  `test_emergency_stop_propagation.py` (API stop → `/api/execution/orders` rejected —
  P-01 in-process); `test_stop_sentinel_cross_process.py` (write sentinel "from
  another process" → fresh gate/engine refuses); `test_safety_gate_truth_table.py`
  (mode × destination per ADR-3, including `run_demo_trader`-style REAL-with-PAPER
  refusal and mock-PAPER allowance); `test_pricing_characterization.py` (from B-02:
  XAU/EURUSD/NAS100 exact values); `test_execution_engine_shared_risk.py`
  (injected `RiskEngine` is the one consulted — R-06); `test_backtest_contract.py`
  (`/run` JSON unchanged; `last_trades` populated); `test_monte_carlo_responsiveness.py`
  + determinism; `test_magic_propagation.py` (C-07); `test_position_price_update.py`
  (N-06); DI-override updates where singletons were removed (B-01).
- **Explicit exclusions (stated):** no test can drive a real bot process against real
  MT5 in CI; cross-process behavior is tested via the file-sentinel mechanism
  (documented in ADR-8), not by spawning MT5.
- **Behavior preserved:** existing 165 tests keep passing (updates only where an
  intended change is documented).
- **Deps:** B-01…B-05, C-01, C-02, C-07 as respective.
- **Risk:** low. **Rollback:** revert test commits.
- **Verification/Done:** suite green including all new tests; no regression — DI
  overrides used where engines are replaced.

### D-03 Error-handling sweep
- **Objective:** no silent exception swallowing; no unguarded broker responses (P-13).
- **Affected:** `backend/app/execution/engine.py` L213-216 (log skipped
  max-holding-time enforcement), `backend/app/scalper/gold_multi_scalper.py` L115-116
  (log command-listener exceptions), and **None-guards on `mt5.order_send` results**
  at: `scalper/grid_martingale_bot.py` (L92, L162, L200),
  `scalper/demo_scalper_engine.py` (L73, L113 — incl. the review-cited L75),
  `scalper/ultra_tick_scalper.py` (L86, L119), `scalper/gold_multi_scalper.py`
  (L331, L440), `scalper/autonomous_scalper_daemon.py` (L130, L166),
  `scripts/run_demo_trader.py` (L71) — most land via C-03's shared helpers; this task
  catches any remainder. (`intelligence/logger.py` resolved by deletion in B-04.)
- **Behavior preserved:** control flow on the happy path.
- **Deps:** B-04, C-03. **Risk:** low. **Rollback:** revert commits.
- **Verification:** grep audit (no `except.*:\s*pass` outside abstract methods) + suite.
- **Done when:** each site logs with sufficient context; every `order_send` result is
  None-guarded.

### D-04 CI additions
- **Objective:** lint gate + compose smoke.
- **Affected:** `.github/workflows/ci.yml` (add `ruff check backend/app
  backend/scripts`, report-only `mypy` job with `continue-on-error: true`, docker
  compose build+health smoke), `pyproject.toml` (ruff config: line-length 100,
  correctness-rule subset).
- **Preserved:** existing jobs. **Deps:** C-06 (compose cleanup done first so smoke
  passes). **Risk:** CI flakiness — keep smoke minimal (build + `GET /api/health`).
- **Rollback:** revert workflow/config commits.
- **Done when:** CI green on the refactor branch with the new jobs.

### D-05 Optional — min-lot over-risk guard (needs owner sign-off)
- **Objective:** stop silently over-risking small accounts when sizing clamps up to
  `min_volume` (`PROFITABILITY_INVESTIGATION.md` H3).
- **Affected:** `backend/app/risk/engine.py`, `config/risk.yaml` (new opt-in key,
  e.g. `reject_when_clamped_over_risk_multiple: 0` = disabled default).
- **Behavior preserved:** default config = current behavior exactly (0 = disabled).
- **Deps:** B-02. **Risk:** behavior change only when enabled — documented
  prominently. **Rollback:** revert; or set the key to 0 (no code revert needed).
- **Verification:** unit tests for enabled/disabled paths.
- **Done when:** decision recorded (implemented or explicitly declined) in README.

### D-06 Alembic baseline decision
- **Objective:** resolve the "scaffolded but unused" ambiguity (P-12).
- **Affected:** `database/alembic.ini` (read URL from env instead of hardcoded creds),
  optionally the first autogenerated migration in `database/migrations/versions/`.
- **Behavior preserved:** dev `create_all` flow continues to work.
- **Deps:** none. **Risk:** low. **Rollback:** revert commits; baseline migration
  removal (no deployed DBs exist to downgrade).
- **Verification:** if baseline chosen: `alembic upgrade head` against a scratch
  Postgres; suite green either way.
- **Done when:** baseline migration exists and passes, **or** README documents
  `create_all` as official and `alembic.ini` no longer hardcodes credentials.

---

## Phase E — Final verification

### E-01 Full backend suite
`pytest tests -q` from `backend/` — all 165 prior tests pass (updates only where an
intended change is documented) + new D-02 tests pass; record count delta.

### E-02 Frontend build & walkthrough
`npm run build`; manual pass over `/`, `/strategy`, `/risk`, `/positions`, `/orders`,
`/backtest` against a locally running backend.

### E-03 API contract diff
Compare every endpoint enumerated in A-02 against `docs/baseline/` samples. Permitted
diffs only: Monte Carlo simulation content (C-02), failure-path status codes (C-01),
security/CORS headers (C-06/D-01), position price values (C-01, N-06). Everything
else must match — notably `POST /api/backtest/run` must be unchanged.
`docs/baseline/contract_diff.py` exits non-zero on drift and runs in CI (M-5);
liquidity/patterns endpoints compare keys only (wall-clock mock data).
The orders/close-all samples were re-captured with valid `LONG` direction after
N2-H2 (the A-02 samples used `"BUY"`, which the fixed code rejects).

### E-04 Safety drill (paper mode; runs against the mock adapter)
1. `POST /api/system/emergency-stop` → `POST /api/execution/orders` must be rejected
   (P-01 in-process proof).
2. **Cross-process proof:** write the sentinel file directly (simulating a trigger
   from another process), then verify both the API order path and a unit-driven
   `ExecutionEngine`/bot-path call refuse.
3. `POST /api/system/reset-emergency-stop` → paths re-enabled.
4. `POST /api/execution/close-all` → positions closed.
5. Unit-verified: **all six order-path files** (five bots + `run_demo_trader.py`)
   call `ensure_trading_allowed`.
6. LIVE-without-flags simulation → gate raises in every path; PAPER/BACKTEST +
   REAL-destination → refused; PAPER + MOCK-destination → allowed (paper workflows
   preserved).
7. **Explicit limitation stated in the drill report:** the sentinel blocks *new
   entries* cross-process; bot-command closes stay allowed (`intent="close"`,
   H-1) but the sentinel itself never closes positions (ADR-8 limits).
8. Close-under-sentinel proven per bot via stubbed-`mt5` control-flow tests
   (`test_bot_gate_control_flow.py`), not only the textual gate audit.

### E-05 Duplication/dead-code/coverage grep audit
- Single `verify_dataset_hash` *implementation body* (`research/common/dataset_hash.py`;
  the 9 engine methods are two-line delegating wrappers kept as the engines'
  public interface — enforced by `test_research_common.py`), single
  `compute_fdr_correction` implementation (`research/common/statistical_tests.py`;
  2 delegating methods).
- No `fusion_2.0` references; root `app/` gone.
- No module-level `MarketDataService(` instantiations in `app/api/` (8 routers).
- No unseeded `np.random.choice` in `app/backtest/`.
- No hard-coded contract-size literals in PnL paths.
- **Order-path audit:** grep `mt5\.order_send` across `backend/app` and
  `backend/scripts` — every occurrence is inside `data/mt5_real.py` or immediately
  preceded by `ensure_trading_allowed`.

### E-06 Infra smoke
`docker compose up --build` (Redis removed): backend healthy, `GET /api/health` 200,
then `docker compose down`.

---

## Dependency graph (summary)

```
A-01 ─┬─► A-02 ─┬─► B-01 ─┬─► D-01 ─► D-04
A-03 ─┘         │        ├─► D-02
                ├─► B-02 ─┬─► C-01 ─┬─► C-02 ─► E-03
                │         │         └─► (C-07 may be paired with C-01 review)
                │         ├─► C-03 ─► D-03
                │         └─► D-05 (optional)
                ├─► B-05 ─────► B-03 ─► (C-03 consumes gate context)
                ├─► B-04 ─────► C-04
                ├─► C-05 ─────► D-01
                └─► C-06 ─────► D-04 ─► E-06
C-07: independent (pairs with C-03 for payload coherence)
All ─► E-01..E-05
```

Cross-process note: the sentinel (B-05) precedes the gate (B-03); both precede
C-03's bot rewiring and E-04's drill.

## Task metadata table (27 tasks)

| ID | Priority | Size | Depends on | Key risk |
|---|---|---|---|---|
| A-01 | high | small | — | none |
| A-02 | high | small | A-01 | none (read-only) |
| A-03 | high | small | — | none |
| B-01 | critical | medium | A-02, A-03 | router/test wiring churn |
| B-02 | high | medium | A-02 | pip/spread drift (mitigated: characterization) |
| B-03 | critical | medium | B-05 | paper-workflow breakage (mitigated: truth table) |
| B-04 | high | small | A-01 | trivial |
| B-05 | critical | small | — | low |
| C-01 | high | medium | B-02 | numeric-output change (intended) |
| C-02 | high | small | C-01 (sequencing only) | low |
| C-03 | medium | medium | B-03 | per-bot payload differences |
| C-04 | medium | medium | B-04 | artifact reproducibility |
| C-05 | medium | medium | A-02 | UI regressions |
| C-06 | high | small | — | CORS tighter defaults (intended) |
| C-07 | medium | small | — | low |
| D-01 | high | small | B-01, C-05, C-06 | production misconfig lockout (documented) |
| D-02 | high | medium | B-01..C-02, C-07 | low |
| D-03 | low | small | B-04, C-03 | low |
| D-04 | medium | small | C-06 | CI flakiness |
| D-05 | low | small | B-02 | behavior change when enabled |
| D-06 | low | small | — | low |
| E-01…E-06 | high | small | all above | none |
