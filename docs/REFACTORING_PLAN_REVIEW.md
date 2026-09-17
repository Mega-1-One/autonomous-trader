# Independent Review — Refactoring Plan, Architecture, and Task Sheet

> **Reviewer role:** independent senior architect (not the planning agent).
> **Scope:** read-only. No source code was modified. This document adds one file to `docs/`.
> **Evidence basis:** direct inspection of the repository, `git status`, and a full local
> run of the backend test suite on the review date.
> **Baseline verified:** `python -m pytest tests -q` from `backend/` → **165 passed, 1 warning in 4.82s** (Python 3.12.10). The plan's headline test claim is correct.
> **Git state verified:** only `docs/` and `PROFITABILITY_INVESTIGATION.md` are untracked; no source modified. The plan's "no source-code modifications" claim is correct.

---

## 1. Executive summary

**Verdict: Ready with required revisions — do not begin implementation until the revisions in §7 are applied and reviewed again.**

The plan is unusually strong for an AI-authored Phase 1: it is evidence-based, conservative, honest about non-goals, and the large majority of its critical/high findings are **confirmed by direct code inspection**. The reported 165 passing tests are real. The chosen direction (consolidate the modular monolith, DI, one safety gate, shared instrument math, dead-code removal, API hardening) is the correct one, and the explicit rejection of microservices/rewrite is well-justified.

However, three defects in the **core safety story are material**, and one task is **not implementable as written**:

1. **The emergency-stop fix does not reach the paths that actually trade.** `RiskEngine.emergency_stop_active` is in-memory and per-process. Even after B-01, the API process's emergency stop cannot affect `app/runner.py` or the bot scripts, which run as separate processes with their own engines. The plan claims "emergency stop finally blocks orders" without acknowledging this. (P-01 is real, but B-01 only fixes the API process.)
2. **The new safety gate is specified to *permit* real broker sends in PAPER/BACKTEST** ("Default configs are PAPER/DEMO → zero behavior change"). That is precisely the dangerous scenario the repo's own `PROFITABILITY_INVESTIGATION.md` (C5) and `README.md` (CAUTION) call out: bots send real orders regardless of `EXECUTION_MODE`. A gate that permits PAPER sends does not close P-02; it only re-checks the LIVE flags that `config.py` already enforces at import time. The eventual policy must distinguish legitimate PAPER execution through the mock adapter from a direct real-broker send; a blanket mode-only gate would risk blocking valid paper tests.
3. **The gate coverage list misses a real order-sending entry point.** There are **six direct order-path files** and **12 direct `mt5.order_send` calls** outside the adapter, not five bots. `backend/scripts/run_demo_trader.py:71` sends orders and is excluded from "the five bots."

Additionally, **C-02 (Monte Carlo) cannot be implemented as specified**: `BacktestMetricsReport` does not carry the trade list, so `/api/backtest/monte-carlo` cannot "pass `report.trades`." And **B-02/ADR-4 rest on two mutually inconsistent XAUUSD specifications already present in the repo**, so "XAUUSD preserved bit-for-bit" is not achievable without an explicit reconciliation decision.

None of these require reanalysis or a different architecture. They require targeted plan revisions. The rest of the task sheet is sound and can proceed largely as written once §7 is addressed.

---

## 2. Verification of original findings

Statuses: **Confirmed** · **Partially confirmed** · **Not confirmed** · **Requires further investigation**.

| Finding | Verification status | Evidence (verified in repo) | Severity assessment | Recommendation |
|---|---|---|---|---|
| **P-01** Two disconnected `RiskEngine` instances; emergency stop doesn't block execution | **Confirmed** | `app/api/risk.py:9` (instance A); `app/execution/engine.py:44` constructs its own (instance B); `app/api/execution.py:10` wires `execution_engine`; `evaluate_trade_risk` checks `emergency_stop_active` only on B. Runner builds a third in a separate process (`runner.py:42`). | **Critical** — justified. | Keep B-01, but add explicit `RiskEngine` injection into `ExecutionEngine.__init__` (see R-01, R-06) and address cross-process scope. |
| **P-02** MT5 bots bypass execution-mode model | **Partially confirmed** (understated) | Dead imports `settings`/`ExecutionMode` verified in all 5 bots (`scalper/*`: daemon:9, demo:7, ultra:8, gold:10, grid:8); zero uses (`Select-String settings\.` in `scalper/*` → none). **But there are 6 direct order-path files / 12 direct calls, not 5:** `scripts/run_demo_trader.py:71` also calls `mt5.order_send`. | **Critical** — justified, scope incomplete. | Keep B-03/C-03 but expand to every order-send site (R-03) and fix gate semantics (R-02). |
| **P-03** Monte Carlo endpoint always returns empty-trade result | **Confirmed** | `app/api/backtest.py:68` calls `simulator.run_simulation(req.initial_balance, [])` with a literal empty list; `BacktestEngine.run` result is discarded. Test `test_api_run_monte_carlo` only asserts `"simulation" in data`, so no test catches it. | **High** — justified. | Fix as planned, but the fix is **not implementable as written** — `BacktestMetricsReport` has no `trades` field (R-04). |
| **P-04** Hard-coded ×100 contract multiplier | **Partially confirmed** | `execution/engine.py:195,244`; `scalper/position_manager.py:59,94`; `gold_multi_scalper.py:152,158` all confirmed. `backtest/engine.py:47` heuristic confirmed. PnL paths hard-code ×100 rather than using `symbol_info["contract_size"]` (which the adapter already supplies). | **High** — justified. | Centralize as planned, but reconcile the *conflicting* XAUUSD specs first (R-05). |
| **P-05** Unauthenticated dangerous endpoints + wildcard CORS | **Confirmed** | `app/main.py:43-46` `allow_origins=["*"]` + `allow_credentials=True`; `grep Depends|api_key|security` in `app/api/*` finds only the DB dependency in `health.py`. Order/close/emergency endpoints unauthenticated. | **High** — justified. | Keep D-01; consider moving origin restriction earlier (R-13) and address frontend token gap (R-08). |
| **P-06** Dead/duplicated modules | **Confirmed** | `fusion_2.0.py` and `fusion_2_0.py` have **identical SHA-256** (verified). Root `app/scalper/position_manager.py` is tracked in git (`git ls-files app/`) and differs from the backend copy only in `typing` import ordering. `SmallAccountDemoConfig` (`scalper/config.py`) and `HistoricalSignalLogger` (`intelligence/logger.py`) have zero references. | **High** — justified. | Keep B-04. **Additional fact:** `intelligence/logger.py` cannot be imported at all (`NameError: name 'Optional' is not defined` at line 9) — the "wire it in" option is impossible without a fix (R-09). |
| **P-07** Module-level singletons / 7 `MarketDataService` | **Confirmed, count wrong** | Module-level instantiations exist in `market`, `structure`, `liquidity`, `setups`, `signals`, `risk`, `execution`, `backtest` → **8** `MarketDataService` instances (plan omits `structure.py:6`). `health.py:14-19` connects `RealMT5Adapter` at import time (verified). `monkeypatch` usage in tests = 0 (verified). | **High** — justified. | Correct the count; otherwise keep B-01. |
| **P-08** Research copy-paste | **Confirmed** (counts approximate) | 9 `def verify_dataset_hash` (verified); all 9 use `or data.get("version") == "2.0.0"` (verified). 2 `compute_fdr_correction` (statistical_testing.py:27, macro_futures_engine.py:85). Plan's "49 scripts" → actual 39 script `.py` files (44 files contain `sys.path.insert`); "6 site-packages injects" → 5 files; "45.7% line-identical" → measured ~42% line similarity. | **Medium** — justified. | Keep C-04; fix counts; resolve bootstrap circularity and tightening risk (R-11). |
| **P-09** Determinism gaps | **Confirmed** | `backtest/walk_forward.py:92` uses unseeded `np.random.choice` (verified). `backtest/engine.py:149` uses `uuid.uuid4()` (verified). `phase34_engine.py:123-124` is seeded via `np.random.seed(42)` as the plan states. | **Medium** — justified. | Keep C-02. Note E-05's grep scopes only `app/backtest/`, which is correct (phase34 is seeded). |
| **P-10** Frontend quality gaps | **Confirmed** | Hardcoded `localhost:8000` in all 6 pages (verified). `useState<any>` in backtest/orders/positions/risk/strategy (verified). POST actions (`risk/page.tsx:32`, `positions/page.tsx:30,35`) have no `res.ok` and no `confirm(` anywhere (verified). `recharts` in `package.json` but unused in `.tsx` (verified). Badge hardcoded `PAPER MODE` at `layout.tsx:39` (verified). | **Medium** — justified. | Keep C-05. |
| **P-11** Inverted/unclear research layering | **Confirmed** | `intelligence/*` and `context/*` import `app.scalper.features` / `app.scalper.instrument` (verified, e.g. cost_analyzer.py:4-5). Package cycle: `regime/engine.py:5 → app.scalper.features` and `scalper/selector.py:2 → app.regime.engine` (verified). No `api/`/`runner.py` imports of these packages (verified). | **Medium** — justified. | Keep the "document, don't move" approach. |
| **P-12** Config/infra inconsistencies | **Confirmed** | `.env.example:4` omits DEMO (verified; code has DEMO at `config.py:12`). Redis service in compose, 0 code references (verified). `database/alembic.ini:6` hardcodes Postgres credentials; `versions/` only `.gitkeep` (verified). `requirements.txt:13` allows pytest-asyncio 1.x while CI pins `<0.24` (verified). `strategy.yaml` htf M5/ltf M1 vs API `api/signals.py:14-15` H1/M5 (verified). | **Low** — justified. | Keep C-06. |
| **P-13** Silent exception swallowing | **Confirmed** | `intelligence/logger.py:19-20` `except Exception: pass` (verified). `execution/engine.py:213-216` silent parse-failure skip (verified). `grid_martingale_bot.py:92` dereferences `res_1.retcode` with no None-guard; `demo_scalper_engine.py:75` similarly dereferences `result.retcode` unguarded (verified). | **Low** — justified. | Keep D-03; add `demo_scalper_engine.py:75` to the guard list (R-14). |

### Findings **not** in the plan but confirmed during review (must be added)

| ID | Finding | Evidence | Severity |
|---|---|---|---|
| **N-01** | Sixth direct order path omitted from P-02/B-03 | `backend/scripts/run_demo_trader.py:71` calls `mt5.order_send` directly; its "safety lock" is bypassed whenever `--enable-demo` is passed, regardless of `EXECUTION_MODE`. | **High** |
| **N-02** | `RealMT5Adapter.send_order` discards the caller's `magic` and hard-codes `100001` | `app/data/mt5_real.py:192` (`"magic": 100001`); `order_request.get("magic")` never read. `ExecutionEngine` passes `magic` (`execution/engine.py:108`). Breaks per-strategy attribution and any magic-based filtering; it also makes the new shared `build_market_order(..., magic, ...)` helper ineffective on the adapter path. (M8 in `PROFITABILITY_INVESTIGATION.md`, absent from the refactoring plan.) | **Medium/High** |
| **N-03** | `BacktestMetricsReport` has no trades, so C-02's stated fix cannot compile | `app/backtest/metrics.py:34-59` (no trade list). `api/backtest.py:64-68` discards `report`. | **High** (plan blocker) |
| **N-04** | Two conflicting XAUUSD specs | `scalper/instrument.py:32-45` (digits=3, point=0.001, pip=0.1, contract=100) vs `data/mt5_mock.py:8-20` (digits=2, point=0.01, tick=0.01, contract=100). `backtest/engine.py:47` uses a third heuristic. | **High** (plan blocker for ADR-4) |
| **N-05** | `intelligence/logger.py` is not importable | `NameError: name 'Optional' is not defined` (uses `Optional` but imports only `Dict, Any`). | **Low** (makes B-04 decision unambiguous) |
| **N-06** | Position price update is effectively broken | `api/execution.py:30` `info.get("bid", 2400.0)`; `MockMT5Adapter.get_symbol_info` returns a spec dict with **no** `bid` key (`mt5_mock.py:87-88`), so every symbol updates at 2400.0. | **Medium** |
| **N-07** | `InstrumentSpecification.get_default_spec` strips all "M" characters | `scalper/instrument.py:30` `symbol.upper().replace("M", "")` (M4 in the profitability doc; the plan does not list it, though B-02 touches this file). | **Medium** |

---

## 3. Architecture review

### ADR-1 — Keep the modular monolith

- **Problem solved:** none; prevents scope explosion.
- **Strengths:** correct. MT5 is a local Windows resource; a single operator; the runtime surface is small (strategy + execution + risk + services + data).
- **Weaknesses:** none material.
- **Alternatives:** service decomposition (rejected correctly).
- **Recommendation:** **Approve.**

### ADR-2 — Application-state container + FastAPI DI

- **Problem solved:** P-01 (partially), P-07; removes import-time side effects; enables test injection.
- **Strengths:** standard FastAPI pattern, no new dependency, test-overridable. `conftest.py` already uses `dependency_overrides` (line 41), so the mechanism fits.
- **Weaknesses:**
  1. **In-process only.** The container lives in `main.py`'s lifespan; `runner.py` and the bot scripts are separate processes. Emergency stop cannot cross that boundary. The plan does not say so.
  2. **`ExecutionEngine` still self-constructs its `RiskEngine`** (`execution/engine.py:44`). B-01 says "single container holding … RiskEngine … constructed in lifespan," but never instructs changing `ExecutionEngine.__init__` to accept the shared engine. Without that change, P-01 remains even after "sharing" the container.
  3. **Test lifespan.** `httpx.ASGITransport` does not run lifespan events. Routers depending on `app.state` will fail in tests unless every dependent is overridden. B-01 mentions adding overrides, but D-02/B-01 must also ensure `test_health.py` (which asserts live DB/MT5 fields) is covered.
- **Alternatives:** global registry (keeps import-time side effects); DI library (needless dependency). Chosen option is best.
- **Recommendation:** **Approve with required changes R-01 (cross-process scope) and R-06 (explicit RiskEngine injection).**

### ADR-3 — Single structural safety gate

- **Problem solved:** P-02 (intended).
- **Strengths:** centralizes the mode decision; a single chokepoint is the right shape.
- **Weaknesses (material):**
   1. **Semantics contradiction.** ADR-3 says the gate "raises unless `EXECUTION_MODE` permits and (for LIVE) both flags are set," but also "Default configs are PAPER/DEMO → zero behavior change." Those two statements conflict for direct broker sends in PAPER. If PAPER permits direct sends, bots keep sending **real** orders in PAPER mode — the exact defect. If the gate blocks all PAPER execution, it also blocks legitimate mock-adapter paper tests. The design therefore needs an explicit execution context or broker-send policy, not a mode-only rule. The task sheet currently resolves the ambiguity incorrectly: B-03 verification says "proceeds in PAPER."
  2. **Redundancy with the boot guard.** `config.py:47-56` already raises at import when LIVE lacks flags, and every bot imports `app.core.config`. A gate that only re-checks the LIVE flags adds little; the real gap is PAPER/BACKTEST real sends.
  3. **No emergency-stop integration.** The gate checks mode flags only. It does not consult the emergency stop. E-04 step 3 ("all five bots call the gate") gives false assurance that emergency stop stops the bots.
  4. **Coverage.** Bare `mt5.order_send` calls bypass `ExecutionEngine`; the gate must be called before each of the 6 sites, and future scripts must be forced through a chokepoint.
- **Alternatives:** (a) gate at a single wrapper that all scripts must use; (b) gate + persisted stop sentinel.
 - **Recommendation:** **Rework semantics before implementation (R-02, R-03).** Define a truth table over both execution mode and destination: mock/paper execution remains allowed in `PAPER`/`BACKTEST`; direct broker sends are refused in those modes; `DEMO` allows only the intended demo destination; `LIVE` requires both live flags. Pass an explicit adapter/broker context to the gate or place the gate at a wrapper that knows the destination. This is safer and matches the README/profitability intent without breaking legitimate paper tests.

### ADR-4 — `InstrumentSpecification` as single source of instrument truth

- **Problem solved:** P-04.
- **Strengths:** offline-testable, broker overridable, removes literals at call sites.
- **Weaknesses (material):**
  1. **Two authoritative XAU specs already disagree** (`instrument.py` vs `mt5_mock.py`; N-04). "Broker `symbol_info` overrides the static spec" hides which wins for pip-size and `digits`, and `runner.calculate_spread_in_pips` currently derives pips from `digits`, not `pip_size`.
  2. **"XAUUSD preserved bit-for-bit" is not achievable** without fixing precedence, because XAU spread/pip math changes if `pip_size=0.1` (instrument.py) replaces the `digits`-based rule used in `runner.py`/`tick_engine.py` for the mock (digits=2).
  3. **`get_default_spec` mangles symbols** by stripping "M" (N-07).
  4. The plan is inconsistent about which sites migrate: B-02 lists `intelligence/cost_analyzer.py`, `adaptive_exit_v2.py`, `runner.py`, but C-01's affected list and its acceptance grep do not.
- **Recommendation:** **Revise (R-05).** State precedence explicitly (broker `symbol_info` > static spec for `point/contract/tick`; define `pip_size` centrally and migrate `calculate_spread_in_pips`/`tick_engine` together), fix the "M" strip, and add characterization tests before changing numbers.

### ADR-5 — Research consolidation via `research/common/`

- **Problem solved:** P-08.
- **Strengths:** avoids churn; keeps artifacts reproducible; each rewire tested by an existing phase test. Correct.
- **Weaknesses:**
  1. **Bootstrap circularity.** Scripts must set `sys.path` before they can `from app.research.common.bootstrap import …`; a helper *inside* the package cannot provide the path setup that makes the package importable.
  2. **Hash tightening is a behavior change.** Removing `or version == "2.0.0"` will hard-fail any regenerated manifest with a different hash. The *current* `data/dataset_manifest.json` matches the target (verified `25833aa4…`), so tests pass now — but re-running the phase pipeline would not. This must be an explicit, documented decision (with a test/flag), not a silent tightening.
  3. Counts in P-08 are approximate; acceptable.
- **Recommendation:** **Approve with R-10/R-11.**

### ADR-6 — API hardening config-gated

- **Problem solved:** P-05.
- **Strengths:** preserves local dev; production gets protection; success shapes unchanged.
- **Weaknesses:**
  1. **Frontend token gap.** D-01 enforces a bearer token in production, but C-05's `lib/api.ts` has no auth-header handling. Enabling production mode would silently break the dashboard.
  2. **CORS remains wildcard for Phases B–C** while both routers are already unauthenticated. The origin restriction is a one-line, independent fix; deferring it to Phase D extends exposure for the entire refactor.
  3. Default `APP_ENV=development` means the token is effectively never on; acceptable for a local single-user tool, but should be stated plainly.
- **Recommendation:** **Approve with R-08/R-13.**

### ADR-7 — Alembic baseline decision

- **Problem solved:** P-12 ambiguity.
- **Strengths:** low risk; either branch (baseline migration or documented `create_all`) resolves the ambiguity.
- **Weaknesses:** none material; `versions/` is empty and `alembic.ini` hardcodes credentials (verified).
- **Recommendation:** **Approve.**

---

## 4. Task-plan review

There are **25** task entries in `REFACTORING_TASKS.md` (A-01…E-06), not 24 as stated in the brief. Legend: **OK** = approve as written · **Modify** = needs edits · **Split** · **Defer/optional**.

### Phase A

| Task | Verdict | Notes |
|---|---|---|
| A-01 Branch/docs | **OK** | `docs/` is currently untracked; the commit is required. |
| A-02 Baseline capture | **OK, scope caveat** | Baseline uses the Mock adapter (plan acknowledges). Response-shape diffing is valid, but it cannot capture real-broker behavior — say so. "19 endpoints" is not verified against the router set; enumerate them. |
| A-03 Pin `pytest-asyncio<0.24` | **OK** | Confirmed: installed 0.23.8, CI pins `<0.24`, `requirements.txt` does not. |

### Phase B

| Task | Verdict | Notes |
|---|---|---|
| B-01 Shared state + DI | **Modify** | Must (a) add `risk_engine` as an `ExecutionEngine` constructor dependency, (b) state in-process scope and the cross-process limitation, (c) enumerate all routers including `structure.py`. |
| B-02 Pricing primitives | **Modify** | Must reconcile XAU specs, define pip semantics, fix the "M" strip, and state precedence. Currently claims "bit-for-bit XAU" that the repo's own two specs contradict. |
| B-03 Safety gate | **Rework** | Fix PAPER/BACKTEST semantics; include `scripts/run_demo_trader.py`; decide whether the gate consults emergency-stop state. |
| B-04 Dead-code removal | **OK, clarify** | Delete-by-default is right; document that `intelligence/logger.py` cannot be imported, so "wiring" is not a drop-in option. |

### Phase C

| Task | Verdict | Notes |
|---|---|---|
| C-01 Execution/risk numeric correctness | **Modify + de-overlap** | Add `cost_analyzer.py`/`adaptive_exit_v2.py` to its edit list (B-02 says C-01 does them). Remove the `FAILED→502` item from D-01 or clearly assign one owner. Specify the price source for `api/execution.py:30` (no `bid` key exists on the mock spec). |
| C-02 Backtest correctness & determinism | **Blocked / must be revised** | `BacktestMetricsReport` has no trades. Add a mechanism to obtain trades (e.g., `BacktestEngine.run` returns `(report, trades)` or exposes `last_trades`) that does **not** change the `/api/backtest/run` response shape. Add a test asserting `probability_of_ruin`/`median_net_profit` respond to trades. |
| C-03 MT5 bot plumbing | **Modify** | Include `scripts/run_demo_trader.py`; include the `RealMT5Adapter.send_order` magic parameter (N-02) or the shared `magic`/`comment` plumbing is cosmetic. |
| C-04 Research common utilities | **Modify** | Resolve bootstrap import order; make hash tightening explicit; note tests (`test_phase31/32/36`) embed the same fallback. |
| C-05 Frontend cleanup | **OK, extend** | Add auth-header support if D-01 can enforce tokens (or document that production requires a reverse proxy). |
| C-06 Config/infra | **OK** | Confirmed items. Keep the README correction to `backend/app/research/` (README currently says `backend/research/`). |

### Phase D

| Task | Verdict | Notes |
|---|---|---|
| D-01 API hardening | **Modify** | Remove duplicated `FAILED→502` (owned by C-01). Address frontend token. Consider moving CORS restriction earlier. |
| D-02 Regression tests for new seams | **Modify** | Add: cross-process stop test or explicit exclusion; `ExecutionEngine` shared-risk injection test; instrument-spec characterization tests. |
| D-03 Error-handling sweep | **OK, extend** | Add `demo_scalper_engine.py:75` None-guard. |
| D-04 CI additions | **OK** | `ruff` only; `mypy` report-only is reasonable. |
| D-05 Min-lot over-risk (optional) | **OK** | Correctly gated and default-off. Note it is the only item touching the profitability-adjacent H3 issue; keep it optional. |
| D-06 Alembic decision | **OK** | Ambiguity is real; either branch acceptable. |

### Phase E

| Task | Verdict | Notes |
|---|---|---|
| E-01 Full suite | **OK** | Baseline verified at 165. |
| E-02 Frontend build/walkthrough | **OK** | Build not run in planning (plan admits); A-02 captures it. |
| E-03 API contract diff | **OK** | Must account for any new `/run` field if C-02 changes the report. |
| E-04 Safety drill | **Modify** | Step 3's "all five bots call the gate" must become "all order-send entry points"; the drill must state that runner/bot processes are not stopped by the API emergency stop unless R-01 is implemented. |
| E-05 Duplication/dead-code grep | **Modify** | Add a grep for `mt5.order_send(` across `app/` **and** `scripts/` to prove gate coverage. |
| E-06 Infra smoke | **OK** | Redis removal is safe (0 code references). |

**Missing tasks:**
- **M-01 (proposed):** Fix `RealMT5Adapter.send_order` to honor `magic`/`comment` (N-02).
- **M-02 (proposed):** Reconcile `InstrumentSpecification`, broker `symbol_info`, and backtest spec literals; fix `get_default_spec` "M" stripping (N-04, N-07).
- **M-03 (proposed):** Cross-process emergency-stop mechanism (sentinel file / DB flag) or an explicit decision to require manual runner/bot shutdown (R-01).
- **Rollback plan:** no per-task revert strategy is documented beyond "one task = one commit." Add a one-line rollback note per task (revert commit; no migrations are introduced by most tasks).

**Incorrect/ambiguous dependencies:**
- C-02 depends on C-01 only to avoid `api/backtest.py` conflicts; the Monte Carlo fix is otherwise independent. Keep the order but state the real reason.
- D-01 depends on C-06 and B-01 — correct. But D-01's `FAILED→502` overlaps C-01 and should be removed.
- The graph omits M-03 (cross-process state) and its consumers (B-03, E-04).

---

## 5. Testing and verification gaps

Verified as **present today:** 165 tests pass; `test_emergency_stop_blocking` tests the engine in isolation; `test_api_emergency_stop_trigger` tests the endpoint and reset; `test_api_run_monte_carlo` asserts only key presence; `test_execution.py` covers idempotency/close-all via the mock adapter; `test_health.py` covers health/root.

Verified as **absent / insufficient** (recommend adding):

1. **Emergency-stop propagation (P-01):** no test drives `/api/system/emergency-stop` then asserts `/api/execution/orders` is rejected. (D-02 proposes it — keep.)
2. **Cross-process emergency stop:** no test or mechanism verifying runner/bots stop. (Missing entirely.)
3. **Safety-gate enforcement per entry point:** no test asserts each order-send script refuses in illegal mode. Add one per path, including `run_demo_trader.py`.
4. **Gate semantics:** no test asserts PAPER/BACKTEST behavior. **Decide and test explicitly.**
5. **PnL across instruments:** no test asserts `price_diff × contract_size × volume` for EURUSD; existing tests are XAU-shaped and use `vol in [0.01, 0.05]` (loose). Add exact EURUSD, XAUUSD, NAS100 cases and an XAUUSD bit-for-bit regression.
6. **Monte Carlo correctness/reproducibility:** no test asserts non-degenerate output when trades exist, nor determinism across runs.
7. **Backtest output compatibility:** adding trades to the report would change `/run` unless excluded — add a contract test.
8. **Authentication/authorization:** no test for token enforcement or CORS headers. D-01 proposes them — keep.
9. **CORS behavior:** no test asserts `allow-origin` is not `*` with credentials.
10. **Shared-state lifecycle/DI:** no test asserts a single engine instance and injected-risk wiring; add an override-based test.
11. **Research reproducibility after C-04:** no test that a regenerated but version-2.0.0 manifest is handled per the tightened rule.
12. **Regression after dead-code removal:** E-05 greps proposed; add an import-collection test (`pytest --collect-only`) plus a `grep` that no live module imports removed paths.
13. **Position price update:** no test for `api/execution.py` returning non-default prices for EURUSD (N-06).
14. **`magic` propagation:** no test that a requested magic reaches the broker request (N-02).

---

## 6. Risk assessment

| Area | Risk | Assessment |
|---|---|---|
| **Live trading safety** | **High** | P-01 is real. B-01 fixes the API process, but runner/bots are separate processes — emergency stop will *still* not stop them. The gate (B-03) permits PAPER sends as specified and misses one order path. As written, the plan **reduces but does not eliminate** the false sense of safety. |
| **Numerical correctness** | **Medium-High** | The ×100 fix is correct, but the XAU spec conflict means the "bit-for-bit XAU" promise is unverifiable until precedence is fixed. Forex PnL becomes correct only if `contract_size=100000` is consistently applied (adapter spec already agrees). Risk of silent pip/spread changes in filters. |
| **API security** | **Medium** | CORS restriction + optional token is reasonable for a single-operator local tool. Residual: token only in production; frontend has no token support; CORS deferred to Phase D. |
| **Regression risk** | **Medium** | DI touches all 8 routers and `conftest.py`; B-02/C-01 change numbers; C-04 touches 9 engines and scripts. Baseline capture (A-02) and contract diff (E-03) are the right mitigations. |
| **Research reproducibility** | **Medium** | Removing the hash fallback is a behavior change; re-runs on regenerated datasets may fail. Current manifest matches, so tests stay green. Needs an explicit decision + test. |
| **Migration/rollback** | **Low-Medium** | Greenfield branch, per-task commits, no schema migrations introduced by most tasks (D-06 optional). Missing an explicit rollback note per task. |

**Scope observation:** `PROFITABILITY_INVESTIGATION.md` documents materially dangerous behaviors — unbounded position churn (C1), coin-flip entries (C2), disabled circuit breakers (C4) — that the refactoring plan classifies as "profitability" and excludes. C1/C4 are **operational risk**, not just strategy performance. The plan should add an explicit deferral note: "the safety gate enforces the *mode* model only; it does not cap concurrent positions or restore circuit breakers; those are product/research decisions tracked in `PROFITABILITY_INVESTIGATION.md`." Without that note, a reader may believe the refactor makes live trading safe when it does not.

---

## 7. Required revisions (prioritized)

| Revision ID | Problem | Required change | Affected document(s) | Reason | Acceptance criteria |
|---|---|---|---|---|---|
| **R-01** | Emergency stop is per-process; B-01 only unifies the API process, so `runner.py` and bot scripts remain unstoppable via the API. | Add an explicit decision and design: either (a) a cross-process sentinel (file/DB row) read by `ensure_trading_allowed` and `ExecutionEngine`, or (b) a documented statement that emergency stop is API-process-scoped and runner/bots must be stopped manually. Add a task (M-03) and an E-04 drill step. | `REFACTORING_PLAN.md` (P-01, §4/§5), `REFACTORING_ARCHITECTURE.md` (ADR-2/3), `REFACTORING_TASKS.md` (B-01, B-03, D-02, E-04) | The headline safety fix is otherwise incomplete and misleading. | A named mechanism (or explicit scope statement) is documented; a test proves the API emergency stop (a) blocks the API order path and (b) either blocks a simulated runner path or is explicitly out of scope. |
| **R-02** | Gate semantics permit real broker sends in PAPER/BACKTEST ("zero behavior change"), leaving P-02's dangerous case open; a blanket PAPER block could also break valid mock execution. | Define concrete semantics over **mode and destination**: mock/paper execution remains allowed in `PAPER`/`BACKTEST`; direct real-broker sends are refused in those modes; `DEMO` allows only the intended demo destination; `LIVE` requires both live flags. Pass an explicit adapter/broker context or gate at a destination-aware wrapper. Update B-03's "behavior preserved" and verification accordingly. | `REFACTORING_PLAN.md` (P-02, ADR-3), `REFACTORING_TASKS.md` (B-03) | The current text contradicts itself and does not fix the actual defect; a mode-only gate is insufficient. | A truth table covers mode × destination; tests prove mock PAPER execution remains valid and every direct broker path is rejected in PAPER/BACKTEST, allowed only under intended DEMO/LIVE conditions. |
| **R-03** | "Five MT5 bots" omits `scripts/run_demo_trader.py:71`; direct sends bypass the adapter. | Enumerate **all** direct `mt5.order_send` sites (**6 files / 12 calls verified**) and require the gate at each, or route them through one destination-aware wrapper. Update B-03/C-03/E-04/E-05. | `REFACTORING_PLAN.md` (P-02), `REFACTORING_TASKS.md` (B-03, C-03, E-04, E-05) | Coverage gap leaves a real order path ungated. | `rg "mt5\.order_send" backend/app backend/scripts` returns only sites that are preceded by the gate (or the adapter); E-05 grep proves it. |
| **R-04** | C-02's Monte Carlo fix cannot be implemented: `BacktestMetricsReport` carries no trades. | Specify a trades-access mechanism that does not change `/api/backtest/run`'s response shape (e.g., `run()` returns `(report, trades)` or stores `engine.last_trades`); add a test where trades>0 yields a non-empty simulation. | `REFACTORING_TASKS.md` (C-02, D-02), `REFACTORING_PLAN.md` (P-03) | Task as written is not implementable and would confuse the implementer. | A concrete mechanism is named; test asserts `total`/`median` reflect actual trades and that `POST /api/backtest/run` JSON is unchanged except if explicitly documented. |
| **R-05** | ADR-4/B-02 rest on conflicting XAUUSD specs; "bit-for-bit XAU" is not achievable as stated. | State precedence (broker `info` overrides static spec for point/contract/tick; single central `pip_size`), fix `get_default_spec` "M" stripping, and migrate `calculate_spread_in_pips`/`tick_engine` in the same task. Add characterization tests before changing numbers. | `REFACTORING_ARCHITECTURE.md` (ADR-4), `REFACTORING_TASKS.md` (B-02, C-01, D-02) | Without this, the numeric refactor is undefined and regressions are likely. | Precedence rule documented; XAUUSD characterization test locked before edits; EURUSD/NAS100 expected values asserted exactly. |
| **R-06** | B-01 does not require `ExecutionEngine` to accept the shared `RiskEngine`; without it P-01 persists. | Explicitly change `ExecutionEngine.__init__(adapter, risk_engine=None)` to accept and reuse an injected `RiskEngine`; container passes the single instance. | `REFACTORING_TASKS.md` (B-01, D-02) | The DI design is incomplete as written. | `grep` shows `ExecutionEngine` no longer creates its own `RiskEngine`; propagation test passes. |
| **R-07** | C-01/D-01 duplicate the `FAILED→502` change; C-01's edit/done lists are inconsistent. | Assign `FAILED→502` to C-01 only; align C-01's affected list (`cost_analyzer.py`, `adaptive_exit_v2.py`, `runner.py`, `api/backtest.py`, `backtest/engine.py`) with its acceptance grep. | `REFACTORING_TASKS.md` (C-01, D-01, B-02) | Overlapping edits to the same file/behavior cause churn and conflict. | Only one task owns the `FAILED→502` change; C-01's file list matches its done-when grep. |
| **R-08** | D-01's production token gate would break the dashboard (frontend sends no token). | Either add `Authorization` header support to `lib/api.ts` + `NEXT_PUBLIC_API_TOKEN`, or document that production deployments front the API with a proxy and the token is not used by the bundled dashboard. | `REFACTORING_TASKS.md` (D-01, C-05), `REFACTORING_PLAN.md` (P-05) | Avoid a production-only outage. | A test or documented workflow proves the dashboard works with the token enabled (or the limitation is explicit). |
| **R-09** | B-04 offers "wire `intelligence/logger.py`" although the module cannot be imported. | Remove the "wire it in" option or add a prerequisite fix; state deletion is the default because import fails (`Optional` undefined). | `REFACTORING_TASKS.md` (B-04) | Prevents an implementer from wasting time or crashing runtime. | Task states the import error and the chosen action. |
| **R-10** | C-04's `bootstrap.py` cannot set the path it needs to be imported. | Make bootstrap importable without prior path setup (e.g., a thin `scripts/_bootstrap.py`, or keep a minimal `sys.path.insert` before importing the helper). | `REFACTORING_TASKS.md` (C-04) | Chicken-and-egg blocks the script rewire. | At least one script uses the new bootstrap and runs green. |
| **R-11** | C-04 hash tightening may break re-runs on regenerated datasets. | Make the tightening explicit and testable (e.g., a `strict` flag defaulting to current behavior, or an explicit documented decision). Note current manifest matches the target. | `REFACTORING_TASKS.md` (C-04), `REFACTORING_PLAN.md` (P-08) | Silent behavior change in research gating. | Decision documented; phase tests pass; regenerated-manifest behavior is stated. |
| **R-12** | Count inaccuracies: 8 (not 7) `MarketDataService`; 39 (not 49) scripts; 6 (not 5) order-send paths; 25 (not 24) tasks. | Correct the counts and include `structure.py`. | all three planning docs | Accuracy; the plan's credibility rests on precise evidence. | Counts match a reproducible grep. |
| **R-13** | CORS restriction deferred to Phase D although it is a trivial, high-value fix and the routers are unauthenticated throughout B–C. | Move the CORS-origin restriction (`CORS_ORIGINS` env, default `http://localhost:3000`) into Phase B/C as an independent commit; keep token enforcement in D-01. | `REFACTORING_TASKS.md` (C-06, D-01) | Reduces exposure window. | Wildcard-with-credentials no longer present after the earlier task; test asserts non-`*` origin. |
| **R-14** | Missing tasks and guards: N-01 (script path), N-02 (`magic`), N-04/N-07 (spec reconciliation), `demo_scalper_engine.py:75` None-guard. | Add tasks M-01/M-02/M-03; extend D-03's guard list. | `REFACTORING_TASKS.md` | Gaps in safety/attribution. | Each new task has objective, files, deps, verification, done-when. |
| **R-15** | No explicit deferral note that C1/C4 in `PROFITABILITY_INVESTIGATION.md` (position churn, disabled circuit breakers) are out of refactoring scope. | Add a short "explicitly deferred, not fixed by this refactor" note referencing C1/C4. | `REFACTORING_PLAN.md` (non-goals) | Prevent a false impression of trading safety. | Note present and unambiguous. |
| **R-16** | Missing rollback guidance per task. | Add one line per task: revert commit; no schema/data migration introduced. | `REFACTORING_TASKS.md` | Operational safety during refactor. | Every task has a rollback line. |

---

## 8. Final recommendation

**Revise the plan and review again before Phase 2.** Do not approve as-is and do not begin implementation.

The plan's direction, evidence, and 80% of its tasks are sound and should be preserved. The blocking issues are concentrated in the safety spine (R-01, R-02, R-03, R-06), one unimplementable task (R-04), and one undefined numeric contract (R-05). These are plan-document fixes, not a return to analysis — the relevant code has already been inspected and the correct decisions are identifiable. No architectural rework (no microservices, no rewrite) is warranted.

**Most important findings:**
1. **Emergency stop still won't stop the things that trade** unless a cross-process mechanism is added; B-01 only unifies the API process.
2. **The safety gate as specified leaves PAPER real-order sending enabled** and misses a sixth order path (`scripts/run_demo_trader.py`).
3. **C-02 cannot be implemented** because the backtest report discards its trades.
4. **ADR-4's "single source of instrument truth" is contradicted by two present XAUUSD specs**, so "bit-for-bit XAUUSD" is undefined.
5. Everything else (dead code, duplication, CORS/auth, frontend, config) verifies cleanly and can proceed.

**Exact document revisions required before Phase 2:**
- `docs/REFACTORING_PLAN.md`: revise P-01 (cross-process scope), P-02 (6 paths), P-04 (spec precedence), P-07 (8 services), P-08 (counts), add N-02/N-03/N-04/N-06/N-07 to the problem list, and add the deferred C1/C4 note (R-15). Update §4 task summaries and §5 risks to match.
- `docs/REFACTORING_ARCHITECTURE.md`: revise ADR-2 (in-process scope + explicit `RiskEngine` injection), ADR-3 (truth-table semantics + emergency-stop integration + all order paths), ADR-4 (spec precedence, "M" strip fix), ADR-6 (frontend token), and the module/dependency rules to name the gate's coverage.
- `docs/REFACTORING_TASKS.md`: update B-01, B-02, B-03, C-01, C-02, C-03, C-04, D-01, D-02, D-03, E-04, E-05; add M-01/M-02/M-03; correct task count to 25; add rollback lines (R-16); resolve C-01/D-01 overlap; correct the dependency graph.

Once these revisions are applied, a short second review should suffice to approve Phase 2.
