# Independent Phase 2 Implementation Review

> **Reviewer role:** independent adversarial reviewer (not the implementing agent).
> **Scope:** read-only review of branch `refactor/consolidation` vs `main`.
> **No source code, documentation, configuration, or Git history was modified by the reviewer.**
> The only file added by the reviewer is this review document.
> **Review date:** 2026-09-17.
> **Artifacts inspected:** AGENTS.md (does not exist), README.md, docs/REFACTORING_PLAN.md,
> docs/REFACTORING_ARCHITECTURE.md, docs/REFACTORING_TASKS.md, docs/REFACTORING_PLAN_REVIEW.md,
> PROFITABILITY_INVESTIGATION.md, the full `main...HEAD` diff, all new/changed safety and numeric
> modules, all 13 new test files, CI, compose, Alembic, frontend.

---

## 0. Handoff note for the fixing session

This document is the complete finding set. Work the sections in this order:

1. **Must-fix (blocking):** section 4 findings `C-1`, `H-1`, `H-2`.
2. **Strongly recommended:** `M-1` … `M-6`.
3. **Deferred/documentation:** `L-1` … `L-8`.

A compact action checklist with exact files is in section 11.

---

## 1. Executive summary

The Phase 2 work is substantial and mostly real. The safety spine (destination-aware gate,
cross-process sentinel, shared `RiskEngine` injection), the numeric corrections, the research
consolidation, and the frontend cleanup are present and largely behave as described. The headline
suite (`263 passed, 1 warning`) and the frontend build were independently reproduced, and the
197-file / +10,350 / −1,360 diff was independently confirmed.

It is **not ready for PR review** because:

1. **The branch fails its own newly-added CI lint gate.** `ruff check app scripts` (exactly what
   `.github/workflows/ci.yml` runs) reports **120 errors** on the committed tree — 88×F541,
   16×F401, 14×F841, 2×F821. D-04's done-condition ("CI green") is not met, and the report's
   limitation line ("Ruff could not run locally because of App Control; CI is authoritative") is
   misleading: ruff runs and the tree is red.
2. **The emergency-stop sentinel also blocks protective/close orders.** The gate is invoked before
   the bots' timeout-close, basket-stop, and close-all sends. When the sentinel is active those
   closes are refused, and the grid bot places orders with **no broker SL/TP**, so an operator
   hitting emergency stop can trap an uncapped losing basket. This contradicts ADR-8's claim that
   closing "remains a bot-command" operation.
3. **The API/backtest services now prefer the real MT5 adapter regardless of `EXECUTION_MODE`.**
   In the default `PAPER` mode on the intended Windows/MT5 machine, `deps.build_adapter()` returns
   `RealMT5Adapter`, the gate classifies destination `REAL`, and **every API order is refused** — a
   regression of the dashboard's paper workflow that ADR-3 explicitly promised to preserve.

These are fixable, but they block PR preparation as written.

---

## 2. Repository and Git verification

| Item | Reported | Verified | Verdict |
|---|---|---|---|
| Branch | `refactor/consolidation` | `git branch --show-current` = `refactor/consolidation` | Confirmed |
| Commit count | 35 | `git rev-list --count main..HEAD` = **34** | Inaccurate (off by one) |
| Diff scope | 197 files, ~+10,350/−1,360 | `197 files changed, 10350 insertions(+), 1360 deletions(-)` | Confirmed |
| Working tree | not stated | clean before and after review (`git status --short` empty) | Confirmed |
| `git diff --check main...HEAD` | not stated | clean (no whitespace errors) | Confirmed |
| HEAD | not stated | `dc07cba docs: record E-04 safety drill results` | Confirmed |
| Merge base | not stated | `3ebf3a8` (main merge tip) | Confirmed |

### Unexpected files / changes

- No `.env`, database file, key, `node_modules`, or `.next` committed.
- `backend/state/` is gitignored (verified) and not tracked.
- Added artifacts: planning docs, `docs/baseline/` samples/tooling, `PROFITABILITY_INVESTIGATION.md`,
  new source modules, new tests. No unrelated source changes detected.
- Root-level `app/` does **not** exist and nothing is tracked under it (`git ls-files app/` empty).

### Git cleanliness

- Clean. (The reviewer's `npm run build` produced an untracked `frontend/next-env.d.ts`; it was
  removed afterward to restore the tree. The reviewer made no commits.)

---

## 3. Task verification (A-01 … E-06)

Verdicts used: Verified · Partially verified · Not verified · Contradicted.

| Task | Claimed status | Evidence found | Missing or concerning details | Verdict |
|---|---|---|---|---|
| A-01 | complete | Branch exists; docs committed in `98eb4fe` | none | Verified |
| A-02 | complete | `docs/baseline/` with 19-endpoint manifest, pytest + npm baselines, capture tooling | baseline is mock-only (stated) | Verified |
| A-03 | complete | `backend/requirements.txt:13` `pytest-asyncio>=0.23.5,<0.24` | none | Verified |
| B-01 | complete | `deps.py` AppState + `init_app_state`; `ExecutionEngine(adapter, risk_engine)` injection; no module-level `MarketDataService(` | `build_adapter()` prefers Real regardless of mode; breaks PAPER API ordering when MT5 present; behavior-preservation claim not met | Partially verified |
| B-02 | complete | `core/pricing.py`; trailing-M fix `instrument.py:33-35`; characterization committed first (`82956f0`) then updated (`1e7cd32`) | none material | Verified |
| B-03 | complete | `core/safety.py` truth table; gate at all 12 direct sites + adapter | Gate applies to **closes**, not just entries; emergency stop can block protective closes (grid has no broker SL) | Partially verified |
| B-04 | complete | Deleted `fusion_2.0.py`, root `app/`, `scalper/config.py`, `intelligence/logger.py`; no references remain | none | Verified |
| B-05 | complete | `core/stop_state.py`; test spawns a real subprocess that reads the sentinel | write-failure degrades cross-process stop silently | Verified |
| C-01 | complete | Spec-based PnL in engine/position_manager/gold/cost_analyzer/adaptive_exit_v2; `FAILED→502`; `get_latest_price` | `cost_analyzer.py` numeric change has **no test**; FAILED→502 test has dead code | Partially verified |
| C-02 | complete | `last_trades`; deterministic IDs (`BT_{symbol}_{i}_{dir}`); seeded MC; contract test | none material | Verified |
| C-03 | complete | `scalper/mt5_orders.py`; bots + `run_demo_trader.py` use it; None-guards | close paths now gated (see B-03) | Partially verified |
| C-04 | complete | `research/common/*`; `scripts/_bootstrap.py`; 9 hash rewires; FDR/splits/ticks shared | only 5 scripts use `_bootstrap`; `common/metrics.py` unused in production; 10 `verify_dataset_hash` defs remain | Partially verified |
| C-05 | complete | `lib/api.ts`, token header, typed state, error banners, `window.confirm`, dynamic mode badge; no stray `localhost:8000` | none | Verified |
| C-06 | complete | `CORS_ORIGINS` wired in `main.py`; `.env.example`; Redis removed; Alembic creds replaced | README corrections from the task were not made (report admits; README no longer contains the cited bad text) | Partially verified |
| C-07 | complete | `mt5_real.py:192-194` honors `magic`/`comment`; tests | none | Verified |
| D-01 | complete | `api/deps.py` bearer gate; wired to all mutating endpoints; tests | non-constant-time compare; `NEXT_PUBLIC_API_TOKEN` is browser-visible (documented) | Verified |
| D-02 | complete | 13 new test files; run green | several assertions weak; some tests touch global `app.state` | Verified |
| D-03 | complete | No `except: pass`; log-instead-of-swallow; `order_send` None-guards on all sites | none material | Verified |
| D-04 | complete | CI jobs `backend-tests/lint/types/compose-smoke/frontend-build` added | **`ruff check app scripts` fails with 120 errors**; CI would be red | Contradicted |
| D-05 | complete | `risk/engine.py:87-98`; `config/risk.yaml` key default 0; tests | none | Verified |
| D-06 | complete | `alembic.ini` creds → `CHANGEME`; `env.py` reads `DATABASE_URL`; README documents `create_all` | **Not verified against a scratch Postgres** (report admits) | Partially verified |
| E-01 | complete | Reproduced `263 passed, 1 warning in 13.82s` | none | Verified |
| E-02 | complete | Reproduced `npm run build` success (9 routes) | manual 6-page walkthrough not independently verifiable | Partially verified |
| E-03 | complete | `contract_diff.py` runs: `checked=19 diffs=2` (matches report) | tool **always `sys.exit(0)`**, not in CI; two diffs asserted (not proven) to be wall-clock; normalization removes timestamps/IDs | Partially verified |
| E-04 | complete | `safety_drill_output.txt` | **19 PASS lines, not 20**; drill never tests close-blocking or bot loops | Partially verified |
| E-05 | complete | Greps: no `fusion_2.0`/root `app/`, no module-level `MarketDataService(`, no unseeded `np.random.choice`, no `uuid.uuid4` in backtest, no 2400 fallback in PnL | "single `verify_dataset_hash` definition" is false (10 defs); 16 F401 remain; ruff gate fails | Partially verified |
| E-06 | complete | Redis gone from compose; no code references | Docker/Postgres smoke not independently verifiable here | Not verified |

---

## 4. Critical findings

Each finding includes severity, file/line references, the problem, why it matters, reproduction,
recommended correction, and whether it blocks PR creation.

### [CRITICAL] C-1 — The new CI lint gate fails on the committed tree

- **Files:** `.github/workflows/ci.yml:59` (does `ruff check app scripts`);
  `backend/pyproject.toml:5-12` (`select = ["F"]`).
  Representative failures:
  - `backend/app/api/backtest.py:69` — F841 unused `report`
  - `backend/app/backtest/engine.py:91` — F841 unused `close`
  - `backend/app/execution/engine.py:139` — F841 unused `order_send_start`
  - `backend/app/execution/engine.py:211` — F841 unused `tp`
  - `backend/app/core/config.py:1` — F401 unused `os`
  - `backend/app/backtest/tick_backtest.py:1` — F401 unused `time`
  - `backend/app/models/domain.py:1` — F401 unused `timezone`
  - `backend/app/regime/engine.py:31`, `backend/app/context/setup_classifier.py:33` — F841
  - `backend/app/research/data_pipeline/candle_builder.py:1`,
    `.../dataset_manifest.py:4` — F401 unused `dataclass`
  - `backend/app/scalper/autonomous_scalper_daemon.py:76,77` and ~85 more — F541
    f-string-without-placeholder
  - `backend/scripts/run_phase18_calibration.py:26` and
    `backend/scripts/run_phase19_edge_discovery.py:27` — F821 undefined `List`
- **What is wrong:** The exact CI command fails locally with `Found 120 errors`
  (88 F541, 16 F401, 14 F841, 2 F821).
- **Why it matters:** D-04's done-condition ("CI green on the refactor branch with the new jobs") is
  unmet. Pushing the branch makes CI red immediately. The report's limitation line implies ruff was
  unavailable, but the gate is objectively failing.
- **Reproduction:** `cd backend; python -m ruff check app scripts` (ruff 0.16.8) → `Found 120 errors`.
  Statistics: `python -m ruff check app scripts --statistics`.
- **Recommended correction:** Fix F401/F841/F821; either fix F541 or add `F541` to `ignore` in
  `pyproject.toml` with a documented reason, then re-run the exact CI command. Note that the sweep
  was also incomplete (it targeted unused imports yet left 16 F401).
- **Blocks PR creation:** **Yes.**

### [HIGH] H-1 — Emergency-stop sentinel blocks protective and basket closes

- **Files:**
  - `backend/app/core/safety.py:39-44` (sentinel check refuses all destinations)
  - `backend/app/scalper/grid_martingale_bot.py:164-170` (averaging refused → then attempts close-all)
  - `backend/app/scalper/grid_martingale_bot.py:189-213` (close gate; returns without closing)
  - `backend/app/scalper/autonomous_scalper_daemon.py:126-131`
  - `backend/app/scalper/ultra_tick_scalper.py:121-126`
  - `backend/app/scalper/demo_scalper_engine.py:116-121`
  - `backend/app/scalper/gold_multi_scalper.py:337-342`
  - `backend/app/scalper/mt5_orders.py:26-59` (grid orders omit SL/TP when `None`)
- **What is wrong:** `ensure_trading_allowed("REAL", …)` is called before *close* sends as well as
  entry sends. When the sentinel is active the gate raises and the bots `break`/`return`, leaving
  positions open. The grid bot builds its orders with no SL/TP, so its basket stop-loss and equity
  guard are the only protection, and both are blocked.
- **Why it matters:** This inverts kill-switch semantics. Instead of halting new risk while allowing
  de-risking, an emergency stop can trap an uncapped losing basket. It contradicts ADR-8's stated
  limit ("closing bot baskets remains a bot-command … operation") because the bot-command close is
  exactly what is refused. The safety drill never exercised this.
- **Reproduction:** In a scratch script, set `AUTOTRADER_STATE_DIR` to a temp dir, call
  `app.core.stop_state.trigger("x")`, then invoke
  `MT5GridMartingaleScalper._close_all_grid_positions([...])` with a stubbed `mt5`; observe
  `[SAFETY GATE REFUSED]` and no order sent.
- **Recommended correction:** Gate only risk-increasing sends; allow close/reduce sends regardless
  of sentinel (or add a distinct close path). Ensure every bot order carries a broker SL as
  defense-in-depth. Add a regression test (gate blocks entry, allows close, under sentinel).
- **Blocks PR creation:** **Yes** (safety-spine design decision).

### [HIGH] H-2 — API/backtest now prefer the real adapter; PAPER orders are refused when MT5 is present

- **Files:** `backend/app/api/deps.py:53-60` (`build_adapter` tries Real first),
  `backend/app/api/deps.py:63-74` (`init_app_state` wires it into market/execution/backtest),
  `backend/app/core/safety.py:56-61` (REAL refused in PAPER/BACKTEST),
  `backend/app/core/config.py:28` (`EXECUTION_MODE` default PAPER).
- **What is wrong:** Before the refactor, `api/execution.py` and `api/backtest.py` used
  `MarketDataService()` → `MockMT5Adapter` unconditionally (`git show main:backend/app/api/execution.py`
  shows `market_service = MarketDataService(); execution_engine = ExecutionEngine(adapter=market_service.adapter)`).
  Now, on the intended machine (MT5 installed/running), the shared adapter is `RealMT5Adapter`; with
  the default `EXECUTION_MODE=PAPER` the gate refuses every API order
  (`forbids real broker order submission`). Mock-paper flow is preserved only when no terminal is
  reachable — i.e., in CI, not on the target machine.
- **Why it matters:** Regression of the documented default paper workflow and contradiction of
  ADR-3's "mock/paper execution remains valid in `PAPER`/`BACKTEST`" and B-01's "mock-adapter default
  behavior" claim. The intended-change register (§2.6) does not list an adapter-selection change.
- **Reproduction:** On a host with `MetaTrader5` installed and a terminal available, run the API and
  `POST /api/execution/orders` in `PAPER`; expect `400 EXECUTION_MODE=PAPER forbids real broker order submission`,
  where pre-refactor it executed on the mock.
- **Recommended correction:** Make `build_adapter()`/state construction honor `EXECUTION_MODE`
  (mock for `PAPER`/`BACKTEST`), or explicitly document and surface the degradation. Add a test that
  the API order path works in `PAPER` independent of adapter availability.
- **Blocks PR creation:** **Yes** (functional regression + contradicts a safety contract).

---

## 5. Medium findings

### [MEDIUM] M-1 — E-05 "single `verify_dataset_hash` definition" is not met

- **Files:** 10 definitions: `backend/app/research/common/dataset_hash.py:31` plus delegating methods
  in `phase28_engine.py:37`, `phase29_conditional_engine.py:36`, `phase30_forensic_engine.py:40`,
  `phase34_engine.py:28`, `phase35_engine.py:26`, `phase36_external_engine.py:28`,
  `final_audit_engine.py:37`, `market_state/market_state_engine.py:85`,
  `macro_futures/macro_futures_engine.py:75`. Also `compute_fdr_correction` is defined 3×
  (`common/statistical_tests.py:12` + 2 delegators).
- **What is wrong:** The *logic* is shared, but the E-05 grep criterion ("single definition") is
  literally false.
- **Why it matters:** The stated acceptance criterion is falsifiable and false; future maintainers
  still see 10 same-named methods.
- **Recommended correction:** Either rename the delegators and update E-05 to "single implementation
  body", or call the canonical function directly from call sites and delete the wrappers.
- **Blocks PR creation:** No.

### [MEDIUM] M-2 — `cost_analyzer.py` numeric change is untested and can flip cost filters

- **Files:** `backend/app/intelligence/cost_analyzer.py:31,38,45,48`.
- **What is wrong:** The ×100 literal was replaced with `spec.contract_size`. This is
  behavior-changing for FX (~×1000) and indices (~×100) and gates `passed` on `total_cost_pips`. No
  test references `CostFilter`/`evaluate_cost` in `backend/tests`.
- **Why it matters:** C-01's numeric contract is only partially verified; research cost gating can
  change silently.
- **Recommended correction:** Add expected-value tests for cost math across XAU/EURUSD/NAS100.
- **Blocks PR creation:** No.

### [MEDIUM] M-3 — `_bootstrap` changes venv `sys.path` precedence

- **Files:** `backend/scripts/_bootstrap.py:28-32` (`sys.path.append` for venv site-packages) vs. the
  old `sys.path.insert(0, venv_site)` in `run_autonomous_scalper.py`, `run_grid_martingale_bot.py`,
  `run_ultra_scalper.py`.
- **What is wrong:** A globally installed package (e.g., `MetaTrader5`) can now shadow the venv copy
  where it previously could not.
- **Why it matters:** Standalone bot scripts are the live order paths; a wrong `MetaTrader5` build is
  a real operational hazard.
- **Recommended correction:** Restore insert-0 precedence for venv site-packages, or document/justify
  the change.
- **Blocks PR creation:** No.

### [MEDIUM] M-4 — Pre-existing `NameError` scripts are now caught by the new lint gate

- **Files:** `backend/scripts/run_phase18_calibration.py:26`,
  `backend/scripts/run_phase19_edge_discovery.py:27` (`-> List[...]` with no `List` import; F821).
- **What is wrong:** The scripts raise at definition time when run, and the new `ruff` job flags
  them. The sweep modified both files and left the defect.
- **Why it matters:** D-04 cannot be green without addressing them; the scripts are broken.
- **Recommended correction:** Add `from typing import List` (or `from __future__ import annotations`).
- **Blocks PR creation:** No (but part of the C-1 CI failure).

### [MEDIUM] M-5 — E-03 contract diff is not a reliable/enforced comparison

- **Files:** `docs/baseline/contract_diff.py:26-41` (aggressive normalization),
  `docs/baseline/contract_diff.py:90` (`sys.exit(0)` always).
- **What is wrong:** The tool always reports success, is not wired into CI, and normalizes away
  timestamps, IDs, latency, and equity-curve timestamps. The two remaining diffs
  (`/api/liquidity/levels`, `/api/strategy/patterns`) are *asserted* to be wall-clock drift. The
  corresponding routers only changed DI wiring (`api/liquidity.py`, `api/setups.py`), which supports
  the assertion, but it is not proven. `POST /api/backtest/run` contract is checked only against a
  re-run within the same process (`test_backtest_contract.py`), not against the committed baseline
  values.
- **Why it matters:** "17/19 identical" is a manual observation, not a gate; a real behavior change
  in the two volatile endpoints could hide behind the wall-clock explanation.
- **Recommended correction:** Make the tool exit non-zero on unexpected diffs, add it to CI, and
  either normalize wall-clock-derived values or record the two diffs as explicitly permitted with
  reasoning.
- **Blocks PR creation:** No.

### [MEDIUM] M-6 — Adapter selection makes the API test suite environment-dependent

- **Files:** `backend/tests/conftest.py:49-58` (ASGITransport; lifespan not run),
  `backend/app/api/deps.py:77-80` (`_ensure_state` lazily builds state).
- **What is wrong:** Tests pass only because `MetaTrader5` is absent; `_ensure_state` calls
  `build_adapter()` which would select the real adapter on a trading host. No test pins the API to
  the mock adapter in `PAPER`.
- **Why it matters:** The suite's meaning depends on the host; combined with H-2 it masks the paper
  regression.
- **Recommended correction:** Override the adapter dependency in tests, or make `build_adapter`
  mode-aware (see H-2).
- **Blocks PR creation:** No.

---

## 6. Low findings

### [LOW] L-1 — `stop_state.is_active()` docstring contradicts behavior; inaccessible state dir can fail open

- **File:** `backend/app/core/stop_state.py:62-85`.
- **Detail:** Docstring says a malformed file is "treated as active … unless it is empty," but an
  empty file raises `JSONDecodeError` (a `ValueError`) and is treated as active. `Path.is_file()`
  swallows `OSError` (returns `False`), so the outer "inaccessible → active" branch is effectively
  unreachable; an unreadable state directory yields `None` (not active).
- **Recommended correction:** Align docstring/code and use explicit `os.stat` error handling to
  distinguish missing from inaccessible.

### [LOW] L-2 — Sentinel write/reset failures silently degrade cross-process guarantees

- **Files:** `backend/app/core/stop_state.py:48-49,58-59`; caller `backend/app/risk/engine.py:204-217`.
- **Detail:** If the disk write fails, `trigger()` only logs while the API still returns
  `emergency_stop_active: true`; cross-process bots keep trading. A failed `reset()` leaves the
  sentinel while the API reports reset.
- **Recommended correction:** Surface write/remove failures in the API response, or fail the trigger.

### [LOW] L-3 — Token interface details

- **Files:** `backend/app/api/deps.py:44-50`; `frontend/lib/api.ts:8-24`.
- **Detail:** Token comparison uses `!=` (not constant-time); `NEXT_PUBLIC_API_TOKEN` is a
  browser-visible value (documented, but worth restating). Default behavior (dev open; production
  open if no token set) is intentional and documented.

### [LOW] L-4 — API `close-all` does not actually close broker positions

- **Files:** `backend/app/api/execution.py:82-94`; `backend/app/execution/engine.py:290-297`.
- **Detail:** `close_all_positions` only mutates in-memory `PositionRecord`s; it never sends a broker
  close. This is pre-existing, but E-04's "close-all ok" can mislead a reader into thinking it
  flattens real positions. Documentation should be explicit.

### [LOW] L-5 — Test pollution / dead code

- **File:** `backend/tests/test_execution_numeric_correctness.py:81-82` (dead
  `__wrapped__` lookup); `:71,85` mutate global `app.state.execution_engine`;
  `backend/tests/test_safety_gate_truth_table.py:154` re-imports `ExecutionEngine` locally (shadows
  the top-level import).

### [LOW] L-6 — Weak numeric assertions in tests

- **Files:** `backend/tests/test_position_price_update.py:30-32`
  (`abs(price - 1.0850) < 5.0`); `backend/tests/test_execution_numeric_correctness.py:31,39,47`
  use the implementation's own `pos.volume` rather than an independently derived volume.

### [LOW] L-7 — NAS100 contract ambiguity

- **Files:** `backend/app/scalper/instrument.py:58` (contract 1.0) vs
  `backend/app/data/mt5_mock.py:54` (contract 20.0); `backend/tests/test_execution_numeric_correctness.py:42-47`
  encodes 20 because broker info wins. C-01's stated expectation was "NAS100 contract=1".
- **Detail:** Defensible under the precedence rule, but the plan and the test disagree; document the
  intended value.

### [LOW] L-8 — Cosmetic

- `backend/app/main.py:64-72` trailing blank lines; `scalper` bots now correctly None-guard
  `order_send` but several `f-string` prints without placeholders remain (F541).

---

## 7. Safety-spine review

- **Gate truth table (ADR-3):** Implemented in `backend/app/core/safety.py:33-78`.
  `MOCK` allowed in every mode; `REAL` refused in `PAPER`/`BACKTEST`; `DEMO` requires
  `account_trade_mode == 0`; `LIVE` requires both live flags; unknown destination refused
  (`:46-47`). All four enum members are covered, so the implicit fall-through (`:78`) is currently
  unreachable — but it is a fail-open pattern if a new mode is ever added; a final explicit
  `raise` is safer.
- **Emergency stop / sentinel:** `RiskEngine.trigger/reset` write/remove the sentinel
  (`risk/engine.py:204-217`); `evaluate_trade_risk` checks both the in-memory flag and the sentinel
  (`:110`); the gate checks the sentinel first (`safety.py:39-44`). Cross-process visibility is
  genuinely tested by spawning a subprocess (`test_stop_sentinel_cross_process.py:54-70`).
- **Sentinel edge cases:** Missing → not active; malformed/non-empty → active (fail-closed);
  trigger creates the directory. Inaccessible directory can fail open (L-1). Atomic replace via
  temp-file + `os.replace` is reasonable. `isolated_state_dir` (conftest) prevents test pollution.
- **Direct MT5 order paths:** Exactly 12 direct `mt5.order_send(...)` sites outside the adapter
  (run_demo_trader 1; ultra 2; demo 2; grid 3; gold 2; daemon 2) plus the adapter
  (`mt5_real.py:199`) = 13, matching the report. Every direct site is preceded by a gate call in the
  same function. The only `adapter.send_order` caller is `ExecutionEngine`
  (`execution/engine.py:140`), which is gated. No alternate/dynamic imports found.
- **Gate ordering:** In `execute_signal` the gate (`:90-101`) runs after idempotency/sync and before
  risk and send — correct. In bots it precedes each send — correct.
- **Fail-open vs fail-closed:** A gate exception is caught and converted to `REJECTED` in
  `ExecutionEngine` (fail-closed). Bots catch `SafetyViolation` and abort the send (fail-closed).
  Unknown adapter type → `REAL` → stricter (fail-closed). Main fail-open exposures: sentinel
  write-failure (L-2) and inaccessible state directory (L-1).
- **Close-all separation:** The API `close-all` is separated from new entries only in the sense that
  it never touches the broker (L-4). The bots' real close paths are gated and can be blocked (H-1).
- **Mode/destination:** Unsafe combinations (`PAPER`+`REAL`, `BACKTEST`+`REAL`, `DEMO`+non-demo) are
  refused consistently at the single gate. There is no silent LIVE→MOCK or REAL→PAPER fallback; if
  anything the fallback is the opposite (adapter prefers REAL, H-2). Boot validator
  (`config.py:61-70`) still refuses `LIVE` without both flags.
- **Config defaults:** `EXECUTION_MODE=PAPER`, both live flags false, `CORS_ORIGINS` localhost-only,
  token off unless production — safe defaults.
- **Documented limitation accuracy:** The drill states the sentinel blocks new entries and does not
  close open positions. That is accurate for API-created simulated positions, but it omits that the
  sentinel also blocks the bots' own protective closes (H-1).

---

## 8. Numerical and trading-logic review

- **PnL:** `backend/app/core/pricing.py:78-85` returns `price_diff × contract_size × volume`;
  contract precedence is broker `symbol_info` > static spec. `execution/engine.py:224,286` and
  `scalper/position_manager.py:60,95` use it. EURUSD/XAUUSD tests use independently computed
  expected values (`0.001×100000×vol`, `1.0×100×vol`). Correct.
- **NAS100:** see L-7.
- **Pip semantics:** `pricing.pip_size` uses spec pip (gold 0.1, 5-digit FX 0.0001, JPY 0.01,
  NAS 1.0) with a point×10 fallback. `mt5_orders.pip_scale_for` intentionally keeps the legacy
  0.10/0.0001 bot convention (documented). Two conventions coexist; acceptable but a maintenance
  trap.
- **Spread:** `pricing.spread_in_pips` keeps legacy digits rules when no symbol is supplied;
  symbol-aware calls use pip_size. Characterization tests document the mock-gold display change
  (5.0→0.5); the spread gate defaults off. Consistent with the plan.
- **Risk sizing:** `RiskEngine.calculate_position_size` uses `tick_size/tick_value` from
  `symbol_info`, which for the mock is internally consistent with contract_size (gold: price_risk×100;
  FX: price_risk×100000). D-05 guard is default-off and unit-tested. No ×10/×100/×1000 unit errors
  found in the touched paths.
- **Backtest:** deterministic trade IDs (`engine.py:168`), no `uuid`, no new look-ahead beyond the
  pre-existing `candles[:i+1]` slice (a design choice, unchanged). Commission is deducted per trade.
  Contracts now resolved by symbol. `/run` shape unchanged and covered by a contract test.
- **Monte Carlo:** Both `MonteCarloSimulator` (`monte_carlo.py:53`, seed 42) and
  `TickMonteCarloSimulator` (`walk_forward.py:91`, seed 42) use `default_rng`; reproducibility and
  trade-responsiveness are tested. The endpoint now passes `engine.last_trades`
  (`api/backtest.py:73`) instead of `[]`. Correct fix for P-03.
- **Time handling:** Candles/timestamps normalized to UTC; `now` uses `timezone.utc`. No new
  timezone regressions in touched code.
- **Not verified:** Real-broker tick values, `trade_contract_size`, and fee/slippage against a live
  broker (the report states this limitation honestly).

---

## 9. API, security, and deployment review

- **Auth:** `require_api_token` (`deps.py:31-50`) is enforced only when `APP_ENV=production` **and**
  `AUTOMATION_API_TOKEN` is set; missing/wrong/empty tokens → 401; dev stays open. Applied to
  `POST /orders`, `/close`, `/close-all`, `/emergency-stop`, `/reset-emergency-stop`. Read endpoints
  stay open. Tests cover all cases and pass. Comparison is not constant-time (L-3).
- **CORS:** `main.py:46-53` uses explicit origins from `CORS_ORIGINS` (default `localhost:3000`),
  `allow_credentials=True`; wildcard+credentials eliminated. Tests confirm a configured origin is
  echoed and `*` is never returned.
- **API contract:** see M-5. `contract_diff.py` → `checked=19 diffs=2`; routers only DI-changed.
- **Input/authorization:** Order submission validates via Pydantic; `direction` is not validated
  against `{LONG,SHORT}` (anything non-`LONG` is treated as SELL at `engine.py:135`), pre-existing.
  No new injection surface.
- **DB:** `create_all` remains official; `alembic.ini` no longer stores real credentials
  (placeholder `CHANGEME`); `env.py` prefers `DATABASE_URL`.
- **Redis:** Removed from compose and no code references (only an unrelated `typesMap.json` in
  `node_modules`).
- **Docker/Postgres:** `docker-compose.yml` is coherent (Redis gone, Postgres healthcheck intact,
  CORS set, `EXECUTION_MODE=PAPER`). Docker smoke (E-06) was not independently reproducible here.
- **Secrets:** No secrets committed; `.gitignore` covers `.env*`, keys, SQLite files, and
  `backend/state/`.

---

## 10. Test adequacy review

- **Quantity:** 98 new tests (263 − 165), and the suite passes reproduced in this environment.
- **Strong spots:** cross-process sentinel truly exercised via subprocess; API emergency-stop
  propagation tested; gate truth table parametrized; characterization tests committed before the
  reconciliation; Monte Carlo determinism/responsiveness with injected trades; `magic`/`comment`
  propagation stubs the `mt5` boundary; D-05 default-off/on; CORS and token matrices.
- **Weak spots / missing tests that matter:**
  1. **Gate placement test is a text window** (`test_safety_gate_truth_table.py:196-217`): it only
     searches 45 lines before `mt5.order_send(`. It cannot detect a dead-branch gate and cannot
     detect that closes are blocked. A fake-`mt5` control-flow test per bot is needed.
  2. **No test for the sentinel's effect on close paths** — the H-1 defect.
  3. **Adapter selection is environment-dependent** — M-6.
  4. **`/run` contract test re-runs in-process** instead of diffing committed baseline values.
  5. **`test_broker_failed_maps_to_502`** mutates global `app.state` and has dead lines
     (`:81-82`).
  6. **Weak numeric assertions** — L-6.
  7. **No test for `cost_analyzer`** (M-2), no independent spread cross-check, no sentinel
     write-failure test.
  8. **No concurrent trigger/reset or permission-denied sentinel tests.**
- **Mock usage:** Moderate and mostly appropriate (MT5 boundary).

---

## 11. Action checklist for the fixing session

**Must fix (blocking)**
- [ ] C-1: `cd backend && python -m ruff check app scripts` must return 0 errors (fix F401/F841/F821;
      decide F541). Files listed in C-1.
- [ ] H-1: Stop gating reduce/close sends behind the emergency sentinel; or add a separate
      close-allowed path. Ensure grid orders carry a broker SL. Files:
      `core/safety.py`, `scalper/grid_martingale_bot.py`, `scalper/autonomous_scalper_daemon.py`,
      `scalper/ultra_tick_scalper.py`, `scalper/demo_scalper_engine.py`,
      `scalper/gold_multi_scalper.py`, `scalper/mt5_orders.py`.
- [ ] H-2: Make `api/deps.py:build_adapter` mode-aware (mock for PAPER/BACKTEST) or document/repair
      the paper-flow regression; add an API PAPER test. Files: `api/deps.py`, `core/config.py`,
      `core/safety.py`; reconcile with `docs/REFACTORING_ARCHITECTURE.md` ADR-3 and register §2.6.

**Strongly recommended**
- [ ] M-1: Rename delegators or narrow the E-05 criterion; delete/repoint `compute_fdr_correction`
      duplicates.
- [ ] M-2: Add expected-value tests for `cost_analyzer.py`.
- [ ] M-3: Restore insert-0 venv path precedence in `scripts/_bootstrap.py`.
- [ ] M-4: Add `from typing import List` to `run_phase18_calibration.py` /
      `run_phase19_edge_discovery.py`.
- [ ] M-5: Make `contract_diff.py` exit non-zero; add to CI; record permitted diffs.
- [ ] M-6: Pin the API test adapter to mock (dependency override or mode-aware build).
- [ ] Add the missing regression tests (close-under-sentinel, per-bot gate control flow).

**Defer with explicit documentation**
- [ ] L-1 … L-8 as documented.
- [ ] Live-broker verification, Docker/Postgres smoke (E-06), D-06 scratch Postgres.
- [ ] Correct the implementation report's inaccuracies: commit count (34, not 35), E-04 check count
      (19, not 20), ruff statement.

---

## 12. Claims from the implementation report

| Claim | Evidence | Assessment |
|---|---|---|
| Branch `refactor/consolidation` | `git branch --show-current` | Confirmed |
| 35 commits | `git rev-list --count main..HEAD` = 34 | Misleading/inaccurate (off by one) |
| All 27 tasks A-01–E-06 complete | Task-by-task inspection | Confirmed but limited (D-04 fails; C-01/C-04/C-06 partial) |
| 197 files, +10,350/−1,360 | `git diff --shortstat main...HEAD` | Confirmed |
| Backend 263 passed, 1 warning | Reproduced `263 passed, 1 warning in 13.82s` | Confirmed |
| Frontend `npm run build` passed | Reproduced (9 routes) | Confirmed |
| Docker smoke: backend healthy with Postgres; Redis removed | Redis removal confirmed in repo; Docker run not reproducible here | Not independently verified (Redis removal confirmed) |
| E-04 all 20 checks passed | `safety_drill_output.txt` has 19 PASS lines | Misleading (19, not 20) |
| 13 `mt5.order_send` sites; all direct sites gate-preceded | 12 direct + 1 adapter; all direct sites gate-preceded in source | Confirmed |
| API token gate verified | `test_api_token.py` passes; code inspected | Confirmed |
| CORS credentials config verified | `test_cors_policy.py` passes; `main.py` inspected | Confirmed |
| API contract 17/19 identical; 2 diffs = wall-clock | `contract_diff.py` → `checked=19 diffs=2`; routers only DI-changed | Confirmed but limited (tool exits 0, not proven, not in CI) |
| Forex PnL correction | `core/pricing.py`, engine/position_manager; tests | Confirmed |
| Mock-gold spread rescaling | `pricing.spread_in_pips`; characterization tests | Confirmed |
| Mock marking based on candle closes | `market_data.get_latest_price` | Confirmed |
| Monte Carlo endpoint simulates real trades | `api/backtest.py:73`; tests | Confirmed |
| Deterministic trade IDs | `backtest/engine.py:168`; tests | Confirmed |
| Seeded walk-forward behavior | `walk_forward.py:91`; tests | Confirmed |
| Ruff could not run locally due to App Control; CI authoritative | Ruff runs here; `ruff check app scripts` = 120 errors | Misleading/inaccurate |
| Real MT5 behavior tested only with mocks/stubs | No live MT5 in tests; report states it | Confirmed |
| README corrections on another branch | README diff only adds warnings/DB section | Confirmed but C-06 README scope incomplete |
| Import sweep initially corrupted imports; tree restored | Diff inspection found no malformed imports; one substantive numeric change is C-01, not the sweep; sweep incomplete (16 F401 remain) | Confirmed by repository evidence |

---

## 13. Final verdict

**Not ready for PR review**

The branch contains genuine, largely correct work, and the headline test/build numbers reproduce.
But it fails its own newly-added CI lint gate with 120 errors, its emergency-stop design can prevent
bots from de-risking (with the grid bot holding positions that have no broker stop-loss), and it
introduces an undocumented adapter-selection change that breaks the default paper workflow on the
intended MT5 host. These are targeted but material fixes; until they are made and CI is green on the
exact gate the branch added, PR preparation would be premature. After the must-fix items, a focused
re-review should be sufficient.
