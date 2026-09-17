# Phase 2 Re-Review (Post-Fix Verification)

> **Reviewer role:** independent adversarial reviewer (same reviewer as
> `docs/PHASE2_INDEPENDENT_REVIEW.md`).
> **Scope:** read-only verification of the fixes applied after Review 1
> (`PHASE2_INDEPENDENT_REVIEW.md`) and Review 2 (`PHASE2_INDEPENDENT_REVIEW2.md`),
> plus a hunt for issues missed the first time.
> **Branch:** `refactor/consolidation`. **Date:** 2026-09-17.
> **No source/config/history modified by this review;** the only file added is this document.
> **Fixes inspected:** commits `9edfec1`, `ab665a6`, `884b411`, `0e5399b`, `360e490`,
> `03f3247`, `02708f8`, `2c94d2f`, `8c894cc` (9 commits after the reviewed head `dc07cba`).

---

## 0. Status legend and instruction to the implementation session

Every finding below carries an explicit status tag. Use this legend:

| Tag | Meaning | Action for the implementation session |
|---|---|---|
| `[COMPLETED / FIXED]` | Verified fixed in the current tree | No action; keep the regression test |
| `[COMPLETED / FIXED — DIFFERENTLY]` | Resolved by a documented, acceptable alternative | No action; keep the documentation |
| `[PARTIAL — NEEDS FOLLOW-UP]` | Partly addressed; residual defect remains | Address the residual (see linked NEW item) |
| `[NOT COMPLETE — WILL FIX NEXT]` | New finding from this re-review, not yet fixed | **Fix in the next session** |
| `[OPEN — DEFERRED / OPTIONAL]` | Low-severity; acceptable to defer with documentation | Fix if cheap, else document |

### Implementation session action queue (the only open items)

| Priority | New ID | Status | One-line required change |
|---|---|---|---|
| 1 | NEW-01 | `[NOT COMPLETE — WILL FIX NEXT]` | Make DEMO/LIVE adapter fallback fail-closed or operator-visible; never return `EXECUTED` for a simulated fill in LIVE |
| 2 | NEW-02 | `[NOT COMPLETE — WILL FIX NEXT]` | Break-even offset must use `pip_size`, not `point_size`; assert the exact moved SL |
| 3 | NEW-03 | `[NOT COMPLETE — WILL FIX NEXT]` | Restore value-level contract checking for `/api/liquidity/levels` and `/api/strategy/patterns` (or add invariants) |
| 4 | NEW-04 | `[OPEN — DEFERRED / OPTIONAL]` | Use UTC date for daily counter rollover |
| 5 | NEW-05 | `[OPEN — DEFERRED / OPTIONAL]` | Disambiguate health `mt5_connected` vs active adapter |
| 6 | NEW-06 | `[OPEN — DEFERRED / OPTIONAL]` | Remove or wire `SECRET_KEY` (or document non-use) |
| 7 | NEW-07 | `[OPEN — DEFERRED / OPTIONAL]` | Make idempotency check-then-add atomic |
| 8 | NEW-08 | `[OPEN — DEFERRED / OPTIONAL]` | Remove trailing blank lines in `main.py` |

> Everything in section 3 is already `[COMPLETED / FIXED]` or `[COMPLETED / FIXED — DIFFERENTLY]`
> except the two `[PARTIAL — NEEDS FOLLOW-UP]` rows (L-6 and N2-M3), whose residual is folded into
> NEW-02. Section 4 lists the new open items.

---

## 1. Executive summary

All six must-fix items from the two reviews are `[COMPLETED / FIXED]`, and the branch now passes its
own quality gates that previously failed.

- `ruff check app scripts` → **All checks passed!** (was 120 errors).
- `pytest tests -q` → **316 passed, 1 warning** (was 263).
- `npm run build` → **passes**.
- `python docs/baseline/contract_diff.py` → **checked=19 diffs=0**, exits 0 (was 2 diffs, always exit 0).
- E-04 drill re-run → 25 checks including close-under-sentinel coverage.

Two safety-spine fixes are real and well-tested: the kill switch no longer traps closes
(`intent="close"`), and API adapter selection is mode-aware so PAPER uses the mock adapter on any host.

However, the fixes introduced/left one genuine safety gap that neither earlier review caught, plus
two medium accuracy/verification gaps — all now labeled `[NOT COMPLETE — WILL FIX NEXT]`:

1. **NEW-01 (HIGH) `[NOT COMPLETE — WILL FIX NEXT]`: `build_adapter` silently falls back from
   DEMO/LIVE to the mock adapter** when the real terminal fails to connect. With the gate treating
   MOCK as always allowed, a LIVE-mode API whose terminal is down will *simulate* orders and return
   `EXECUTED`. This contradicts the stated property that the system cannot silently fall back from
   LIVE to MOCK, and the new test `test_demo_falls_back_to_mock_without_terminal` codifies it.
2. **NEW-02 (MEDIUM) `[NOT COMPLETE — WILL FIX NEXT]`: the break-even fix (N2-M3) uses point size
   where pip size is required**, so the configured `break_even_offset_pips` rounds away
   (`0.1 × 0.00001 = 1e-6` → 5-dp rounding yields no offset on EURUSD; `0.1 × 0.01 = 0.001` → no
   offset on 2-digit gold). The new test passes only because `pytest.approx` tolerates the missing
   offset.
3. **NEW-03 (MEDIUM) `[NOT COMPLETE — WILL FIX NEXT]`: `contract_diff.py` now exempts *all values*
   for `/api/liquidity/levels` and `/api/strategy/patterns`** via `KEYS_ONLY_PATHS`, weakening E-03:
   a value regression in those endpoints would pass CI.

Verdict: **Ready after targeted fixes.** The previously blocking defects are cleared; NEW-01 should
be fixed before PR, and NEW-02/NEW-03 are strongly recommended.

---

## 2. Repository and gate state

| Item | Before fixes | After fixes | Status |
|---|---|---|---|
| Commits vs `main` | 34 | **44** (`git rev-list --count main..HEAD`) | `[COMPLETED / FIXED]` |
| Diff scope | 197 files, +10,350/−1,360 | **219 files, +12,628/−1,504** | `[COMPLETED / FIXED]` |
| `ruff check app scripts` | 120 errors | **0 errors** | `[COMPLETED / FIXED]` |
| `pytest tests -q` | 263 passed | **316 passed, 1 warning** | `[COMPLETED / FIXED]` |
| `npm run build` | pass | **pass** | `[COMPLETED / FIXED]` |
| `contract_diff.py` | `diffs=2`, always exit 0 | **`diffs=0`**, exits non-zero on drift | `[COMPLETED / FIXED]` (but see NEW-03) |
| E-04 drill | 19 PASS | **25 PASS** (adds 2c close-allowed, 5b close intent) | `[COMPLETED / FIXED]` |
| `git status --short` | clean | **clean** | `[COMPLETED / FIXED]` |

New tests added: `test_bot_gate_control_flow.py`, `test_cost_analyzer.py`,
`test_direction_validation.py`, `test_execution_robustness.py`, `test_mode_aware_adapter.py`,
`test_risk_accounting.py` (+ modifications to 7 existing test files).

---

## 3. Verification of earlier findings

### 3.1 Review 1 findings

| ID | Finding | Status | Evidence |
|---|---|---|---|
| C-1 | CI lint gate fails (120 errors) | `[COMPLETED / FIXED]` | `ruff check app scripts` = `All checks passed!` |
| H-1 | Sentinel blocks protective/basket closes; grid has no broker SL | `[COMPLETED / FIXED]` | `safety.py:38-100` adds `intent`; close calls in daemon:127, demo:117, ultra:123, gold:338, grid:227 use `intent="close"`; grid adds `protective_sl_pips` (`grid_martingale_bot.py:22,33-48,97,175`); `_close_all_grid_positions` now `continue`s (`:225-230`); `test_bot_gate_control_flow.py` drives every bot with a fake `mt5` |
| H-2 | Adapter selection ignores `EXECUTION_MODE` | `[COMPLETED / FIXED]` | `deps.py:54-73` mode-aware (PAPER/BACKTEST → mock); `test_mode_aware_adapter.py` incl. host-independent API PAPER test (residual: NEW-01 fallback) |
| M-1 | E-05 "single `verify_dataset_hash` definition" false | `[COMPLETED / FIXED — DIFFERENTLY]` | Criterion narrowed to "single implementation body" + 9 documented delegating wrappers, enforced by `test_research_common.py` (`REFACTORING_TASKS.md:541-546`). Still 10 `def` sites by grep. |
| M-2 | `cost_analyzer` change untested | `[COMPLETED / FIXED]` | `test_cost_analyzer.py` locks XAU/EURUSD/NAS100 values |
| M-3 | `_bootstrap` venv path precedence | `[COMPLETED / FIXED]` | `_bootstrap.py:20-51` restores insert-0 `[backend, venv, ...]` order |
| M-4 | `List` NameError in phase18/19 | `[COMPLETED / FIXED]` | `run_phase18_calibration.py:5` now `from typing import List` (same in phase19); ruff clean |
| M-5 | Contract diff always exits 0, not in CI | `[COMPLETED / FIXED]` | `contract_diff.py:105` `sys.exit(1 if diffs else 0)`; `ci.yml` runs it (residual: NEW-03) |
| M-6 | Adapter test host-dependent | `[COMPLETED / FIXED]` | Mode-aware `build_adapter` + `test_api_paper_order_host_independent` |
| L-1 | `is_active` docstring/inaccessible-dir fail-open | `[COMPLETED / FIXED]` | `stop_state.py:80-94` explicit `os.stat`; `FileNotFoundError` vs `OSError`; empty treated active; docstring aligned |
| L-2 | Silent sentinel persistence failure | `[COMPLETED / FIXED]` | `trigger/reset` return bool; `RiskEngine` returns it; `api/risk.py:81-107` appends warning to message |
| L-3 | Non-constant-time token compare | `[COMPLETED / FIXED]` | `hmac.compare_digest` (`deps.py:47`) |
| L-4 | `close-all` in-memory only | `[COMPLETED / FIXED — DIFFERENTLY]` | `api/execution.py:104-109` explicit docstring |
| L-5 | Test pollution / dead lines | `[COMPLETED / FIXED]` | dead `__wrapped__` lines removed; duplicate `ExecutionEngine` import removed (`test_safety_gate_truth_table.py` only line 22 remains) |
| L-6 | Weak numeric assertions | `[PARTIAL — NEEDS FOLLOW-UP]` | Break-even/position tests improved; some tolerances remain (e.g. `<5.0` price window in `test_position_price_update.py`); residual tracked under NEW-02 |
| L-7 | NAS100 ambiguity | `[COMPLETED / FIXED — DIFFERENTLY]` | Precedence resolution recorded (`REFACTORING_ARCHITECTURE.md:340-344`), both paths locked by tests |
| L-8 | Cosmetic (F541, blank lines) | `[PARTIAL — NEEDS FOLLOW-UP]` | F541 zero; `main.py:64-72` trailing blank lines remain — tracked as NEW-08 |

### 3.2 Review 2 findings

| ID | Finding | Status | Evidence |
|---|---|---|---|
| C-1 | CI lint gate | `[COMPLETED / FIXED]` | as above |
| H-1 | Sentinel traps closes; grid no SL; loop abandons basket | `[COMPLETED / FIXED]` | as above (continue + protective SL) |
| H-2 | Adapter ignores mode | `[COMPLETED / FIXED]` | as above (residual: NEW-01 fallback) |
| N2-H1 | Daily counters never updated | `[COMPLETED / FIXED]` | `risk/engine.py:46-71` record/rollover methods; `execution/engine.py:178,333`; `test_risk_accounting.py` |
| N2-H2 | Direction unvalidated | `[COMPLETED / FIXED]` | engine `:78-82`; API `Literal["LONG","SHORT"]` + case-normalizing validator → 422 (`api/execution.py:14-26`); `test_direction_validation.py` |
| N2-H3 | FAILED consumes idempotency ID | `[COMPLETED / FIXED]` | ID marked only on EXECUTED (`execution/engine.py:170-177`); `test_execution_robustness.py` |
| N2-M1 | Gate fail-open for unknown modes | `[COMPLETED / FIXED]` | explicit final `raise SafetyViolation` (`safety.py:97-100`) |
| N2-M2 | Backtest spread/asymmetric slippage | `[COMPLETED / FIXED — DIFFERENTLY]` | Documented fill methodology (`backtest/engine.py:14-28`) + explicit tests (`test_backtest_correctness.py`) |
| N2-M3 | Break-even fixed point 0.01 | `[PARTIAL — NEEDS FOLLOW-UP]` | Now per-symbol point/digits (`execution/engine.py:218-241,273-280`), but `offset = pips × point` is dimensionally wrong (should be `pip_size`); offset rounds to zero — **fix next as NEW-02** |
| N2-M4 | PositionManager omits broker info; NAS100 | `[COMPLETED / FIXED]` | `position_manager.py:38-106` accepts `symbol_info` map; NAS100 documented |
| N2-M5 | Inconsistent ruin thresholds | `[COMPLETED / FIXED — DIFFERENTLY]` | Distinct named constants (`monte_carlo.py:7-12`) + test |
| N2-M6 | Inaccessible state dir fails open | `[COMPLETED / FIXED]` | `stop_state.py:80-86` |
| N2-M7 | Close loop abandons; risk-evaluate max-open bypass | `[COMPLETED / FIXED]` | `continue` in grid loop; `api/risk.py:60-66` passes real open count; tests |
| N2-M8 | Side-agnostic marking | `[COMPLETED / FIXED]` | `get_latest_price(side=...)` (`market_data.py:42-75`); `api/execution.py:35-48`; sweep verified clean |
| N2-L1 | Minor items | `[PARTIAL — NEEDS FOLLOW-UP]` | engine None-guard fixed (`execution/engine.py:144-147`); token timing fixed; HTF/LTF documented (`backtest/engine.py:25-27`); close-all documented; drill noise removed. `SECRET_KEY` still unused — tracked as NEW-06 |

---

## 4. New findings (from this re-review) — all open

### `[NOT COMPLETE — WILL FIX NEXT]` [HIGH] NEW-01 — Silent DEMO/LIVE → MOCK fallback can simulate live orders

- **File:** `backend/app/api/deps.py:54-73`.
- **What is wrong:** For DEMO/LIVE, if `RealMT5Adapter.connect()` fails, `build_adapter()`
  silently returns `MockMT5Adapter`. Because `destination_for_adapter(MockMT5Adapter) == "MOCK"`
  and the gate allows MOCK in every mode (`safety.py:68-70`), a LIVE-mode API whose terminal is
  down will accept orders, run them on the simulator, and return `{"status": "EXECUTED"}`. The new
  test `test_demo_falls_back_to_mock_without_terminal` enshrines the fallback as intended, and the
  architecture text (`REFACTORING_ARCHITECTURE.md:306-309`) records it, but no operator-visible
  signal (health/response) distinguishes "live, actually sent" from "live, simulated".
- **Why it matters:** This is the "silent LIVE→MOCK fallback" the safety model claims cannot
  happen. An operator believing they are live could be trading a simulator.
- **Reproduction:** On a host without a running terminal, set `EXECUTION_MODE=LIVE` +
  `ENABLE_LIVE_TRADING=true` + `LIVE_TRADING_CONFIRMATION=true`, start the API, and
  `POST /api/execution/orders`; observe `EXECUTED` from the mock while `mt5_adapter` is
  `MockMT5Adapter`.
- **Recommended correction:** For LIVE (and optionally DEMO), fail closed when the real adapter is
  unavailable (raise at startup / reject orders), or expose an explicit degraded state
  (`adapter=mock`, order reason "simulated") in the health response and the order result; never
  return `EXECUTED` for a simulated fill in a real-money mode. Add a test that LIVE+no-terminal is
  refused rather than simulated.
- **Blocks PR creation:** Yes (safety-spine behavior).

### `[NOT COMPLETE — WILL FIX NEXT]` [MEDIUM] NEW-02 — Break-even offset uses point size instead of pip size (rounds to zero)

- **Files:** `backend/app/execution/engine.py:273-280`; test `backend/tests/test_execution_robustness.py:65-86`.
- **What is wrong:** `offset = self.break_even_offset_pips * sym_point`, but `sym_point` is
  `point_size`, not `pip_size`. For EURUSD (point 0.00001) the offset is `0.1 × 0.00001 = 1e-6`,
  which `round(..., 5)` discards → SL moves to entry with no buffer. For mock gold (2-digit,
  point 0.01) `0.1 × 0.01 = 0.001` → `round(..., 2)` discards. Verified numerically:
  `round(1.085 + 1e-6, 5) = 1.085`, `round(2400 + 0.001, 2) = 2400.0`.
- **Why it matters:** N2-M3 asked for a "per-symbol point/pip lookup"; the fix picked point. The
  core break-even (SL at entry) still works and the feature is disabled by default, but the new test
  only passes because `pytest.approx(1.085001)` tolerates the absent offset, so it does not prove
  the intended offset.
- **Reproduction:** `python -c "print(round(1.085 + 0.1*0.00001, 5))"` → `1.085`.
- **Recommended correction:** Use the canonical pip size (`app.core.pricing.pip_size`) for the
  offset and assert an exact moved stop distance (or widen precision) rather than an `approx` that
  the rounded value satisfies.
- **Blocks PR creation:** No (disabled by default), but strongly recommended.

### `[NOT COMPLETE — WILL FIX NEXT]` [MEDIUM] NEW-03 — Contract diff exempts all values for two endpoints

- **File:** `docs/baseline/contract_diff.py:49-51,91-95`.
- **What is wrong:** `KEYS_ONLY_PATHS = {"/api/liquidity/levels", "/api/strategy/patterns"}` now
  compares only response keys, not values, removing value-level regression detection for those
  endpoints from the CI gate.
- **Why it matters:** E-03's contract protection is weaker than implied; a genuine value regression
  (not wall-clock) in either endpoint would pass CI silently.
- **Recommended correction:** Normalize the genuinely volatile inputs (freeze/patch the mock clock
  in the capture, or exclude only the specific derived fields) rather than exempting the whole
  payload; or add invariant assertions (level count/ordering/types).
- **Blocks PR creation:** No.

### `[OPEN — DEFERRED / OPTIONAL]` [LOW] NEW-04 — Daily counter rollover uses local date, not UTC

- **File:** `backend/app/risk/engine.py:49,53-61`.
- **What is wrong:** `date.today()` is local time while the rest of the system uses UTC; daily
  counters/locks reset at local midnight.
- **Recommended correction:** Use `datetime.now(timezone.utc).date()` and document the boundary.

### `[OPEN — DEFERRED / OPTIONAL]` [LOW] NEW-05 — Health `mt5_connected` is always true in PAPER/BACKTEST

- **File:** `backend/app/api/health.py:27-38`; `backend/app/api/deps.py:64-67`.
- **What is wrong:** In PAPER/BACKTEST the selected adapter is always a connected mock, so
  `/api/health` reports `mt5_connected: true` (with `mt5_adapter: "MockMT5Adapter"`) even with no
  real terminal; a monitor keying on `mt5_connected` could misread readiness.
- **Recommended correction:** Report the real terminal status separately from the active adapter,
  or rename/annotate the field.

### `[OPEN — DEFERRED / OPTIONAL]` [LOW] NEW-06 — `SECRET_KEY` remains defined but unused

- **File:** `backend/app/core/config.py:24` (only occurrence in `app/`).
- **Status:** carried over from N2-L1; not addressed. Cosmetic/informational.

### `[OPEN — DEFERRED / OPTIONAL]` [LOW] NEW-07 — Idempotency check has a concurrent double-submit race

- **File:** `backend/app/execution/engine.py:84-87,177`.
- **What is wrong:** The check-then-add is not atomic; two simultaneous requests with the same
  `client_signal_id` can both pass the check before either adds the ID. Pre-existing; unchanged.
- **Recommended correction:** Guard with a lock or reserve the ID before send and release on FAILED.

### `[OPEN — DEFERRED / OPTIONAL]` [LOW] NEW-08 — Cosmetic: trailing blank lines in `main.py`

- `backend/app/main.py:64-72`. Trivial.

---

## 5. Test-quality assessment of the new tests

Strengths `[COMPLETED / FIXED]`:
- `test_bot_gate_control_flow.py` drives the real bot methods with a stubbed `MetaTrader5` module and
  asserts actual `order_send` behavior (entry refused, close sent, loop continues, protective SL) —
  this directly replaces the earlier 45-line text-window weakness.
- `test_risk_accounting.py` proves the locks can actually fire and roll over.
- `test_direction_validation.py` covers engine and API (422) plus case normalization.
- `test_execution_robustness.py` covers retry-after-FAILED, duplicate-after-EXECUTED, adapter
  `None`, and break-even wiring.
- `test_cost_analyzer.py` locks XAU/EURUSD/NAS100 expected dollars.

Weaknesses `[NOT COMPLETE — WILL FIX NEXT]`:
- The break-even test's `pytest.approx` tolerance hides the rounded-away offset (NEW-02).
- Some tests still mutate global `app.state` directly and rely on cleanup; order-dependence risk.
- No test asserts LIVE + real-unavailable behavior (the crux of NEW-01).

---

## 6. Remaining risks and recommendations

**Must fix before PR** — `[NOT COMPLETE — WILL FIX NEXT]`
- NEW-01: make DEMO/LIVE adapter fallback fail-closed or operator-visible; never return `EXECUTED`
  for a simulated fill in LIVE.

**Strongly recommended before PR** — `[NOT COMPLETE — WILL FIX NEXT]`
- NEW-02: use `pip_size` for break-even offset and tighten the test to an exact expected SL.
- NEW-03: restore value-level contract checking for the two exempted endpoints (or add invariants).

**Can be deferred with explicit documentation** — `[OPEN — DEFERRED / OPTIONAL]`
- NEW-04 (UTC day boundary), NEW-05 (health `mt5_connected` semantics), NEW-06 (`SECRET_KEY`
  unused), NEW-07 (idempotency race), NEW-08 (cosmetic).
- Live-broker verification, Docker/Postgres smoke, D-06 scratch-Postgres (report's stated limits).

---

## 7. Verdict

**Ready after targeted fixes.**

Both reviews' must-fix items are `[COMPLETED / FIXED]` and independently verified: the lint gate is
green, closes are no longer trapped, PAPER is host-independent, risk accounting is live, direction
is validated, and FAILED retries work; the full suite (316) and frontend build pass, and the
contract diff is clean and now gates in CI.

Open items for the implementation session: **NEW-01 `[NOT COMPLETE — WILL FIX NEXT]`** (blocking),
and **NEW-02 / NEW-03 `[NOT COMPLETE — WILL FIX NEXT]`** (strongly recommended), plus optional
lows NEW-04…NEW-08 `[OPEN — DEFERRED / OPTIONAL]`.
