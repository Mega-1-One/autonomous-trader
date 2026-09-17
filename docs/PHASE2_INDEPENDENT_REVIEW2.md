# Independent Phase 2 Implementation Review

> Second independent review (Review 2), now including the **post-fix re-review**.
> Read-only review of branch `refactor/consolidation` vs `main`. No source, config,
> or Git history modified by the reviewer; only this document is updated.
> Original review date (UTC): 2026-09-17. Post-fix re-review: 2026-09-17 (later session).
> Review 1 (`docs/PHASE2_INDEPENDENT_REVIEW.md`) was consulted only after independent
> findings were formed. A third re-review from another session
> (`docs/PHASE2_RE_REVIEW.md`) was independently checked; agreements/disagreements
> are recorded below. `AGENTS.md` does not exist.

## Status legend (post-fix re-review)

| Tag | Meaning |
|---|---|
| `[FIXED/COMPLETED]` | Verified fixed in the current tree by this reviewer |
| `[FIXED/COMPLETED — DIFFERENTLY]` | Resolved by a documented, acceptable alternative |
| `[PARTIAL — NOT FINISHED]` | Partly addressed; residual defect remains |
| `[NOT FIXED — WILL COMPLETE NEXT]` | Still open; fix in the next session |
| `[OPEN — DEFERRED]` | Low severity; acceptable to defer with documentation |

---

# Part 1 — Original Review 2 (pre-fix), findings with current status

## Executive summary (original)

Large and largely genuine implementation; suite reproduced (was 263 passed), diff
confirmed (197 files, +10350/−1360). Verdict was **not ready for PR review** due to
three Review 1 blockers plus six new blockers found here. All of those are now
addressed — see the post-fix re-review below for the verification evidence.

## Repository and Git verification (original)

Branch `refactor/consolidation` confirmed; commit count was 34 (reported 35, off by
one); diff `197 files, +10350/−1360` confirmed; tree clean; no secrets/artifacts
tracked. `[FIXED/COMPLETED]` — now 44 commits, tree clean.

## Task verification (original; statuses current)

| Task | Original verdict | Current status |
|---|---|---|
| A-01/A-02/A-03 | Verified | `[FIXED/COMPLETED]` (no change needed) |
| B-01 | Partially verified | `[FIXED/COMPLETED]` (mode-aware adapter, host-independent test) |
| B-02 | Verified | `[FIXED/COMPLETED]` |
| B-03 | Partially verified | `[FIXED/COMPLETED]` (close intent + fail-closed fall-through) |
| B-04 | Verified | `[FIXED/COMPLETED]` |
| B-05 | Partially verified | `[FIXED/COMPLETED]` (stat fail-closed, surfaced persistence) |
| C-01 | Partially verified | `[FIXED/COMPLETED]` (cost tests; NAS100 documented; break-even per-symbol — residual NEW-02) |
| C-02 | Partially verified | `[FIXED/COMPLETED — DIFFERENTLY]` (fill methodology documented + tests) |
| C-03 | Partially verified | `[FIXED/COMPLETED]` (close intent, continue loop, protective SL) |
| C-04 | Partially verified | `[FIXED/COMPLETED — DIFFERENTLY]` (criterion narrowed to single implementation body + wrappers documented/enforced) |
| C-05 | Verified | `[FIXED/COMPLETED]` |
| C-06 | Partially verified | `[FIXED/COMPLETED — DIFFERENTLY]` (README scope kept minimal; documented) |
| C-07 | Verified | `[FIXED/COMPLETED]` |
| D-01 | Verified | `[FIXED/COMPLETED]` (now `hmac.compare_digest`) |
| D-02 | Partially verified | `[FIXED/COMPLETED]` (control-flow bot tests replace text window) |
| D-03 | Partially verified | `[FIXED/COMPLETED]` (engine None-guard added) |
| D-04 | Contradicted | `[FIXED/COMPLETED]` (`ruff check app scripts` = 0 errors, re-run independently) |
| D-05 | Partially verified | `[FIXED/COMPLETED]` (counters live; guard now reachable) |
| D-06 | Partially verified | `[OPEN — DEFERRED]` (no scratch-Postgres run; documented) |
| E-01 | Verified | `[FIXED/COMPLETED]` (now 316 passed, re-run) |
| E-02 | Partially verified | `[FIXED/COMPLETED]` (build passes) |
| E-03 | Partially verified | `[FIXED/COMPLETED]` (exit code gated in CI; re-baselined; residual NEW-03) |
| E-04 | Partially verified | `[FIXED/COMPLETED]` (25 checks incl. close-under-sentinel) |
| E-05 | Partially verified | `[FIXED/COMPLETED — DIFFERENTLY]` (single-implementation criterion) |
| E-06 | Not verified | `[OPEN — DEFERRED]` (Docker smoke not independently run) |

## Critical findings (original) — statuses

- **[CRITICAL] C-1 — CI lint gate failed (120 errors)** — `[FIXED/COMPLETED]`.
  Independently re-run: `ruff check app scripts` → All checks passed (exit 0).
- **[HIGH] H-1 — Sentinel blocked protective closes; grid had no broker SL; close
  loop abandoned basket** — `[FIXED/COMPLETED]`. Gate now takes `intent="close"`
  which bypasses only the sentinel (mode rules still enforced) (`safety.py:38-100`);
  all five bot close sites pass `intent="close"`; grid orders carry a
  `protective_sl_pips` disaster stop (`grid_martingale_bot.py:22,41-48,97,175`);
  close loop `continue`s per ticket (`:228-230`); `test_bot_gate_control_flow.py`
  drives real bot methods against a stubbed `mt5` (entry refused, close sent);
  drill now has 25 checks including close-under-sentinel.
- **[HIGH] H-2 — Adapter ignored EXECUTION_MODE** — `[FIXED/COMPLETED]` with
  residual: `build_adapter()` is mode-aware (PAPER/BACKTEST → mock always,
  `deps.py:63-67`); host-independent API PAPER test passes. Residual = NEW-01
  (DEMO/LIVE fallback) below.
- **[HIGH] N2-H1 — Daily counters never updated** — `[FIXED/COMPLETED]`.
  `record_executed_trade`/`record_closed_trade` called on fill/close
  (`execution/engine.py:178,333`); `_maybe_rollover` also runs in
  `evaluate_trade_risk` (`risk/engine.py:134`) — no stale-lock deadlock;
  `test_risk_accounting.py` proves locks fire and roll over.
- **[HIGH] N2-H2 — Direction unvalidated, non-LONG became SELL** —
  `[FIXED/COMPLETED]`. Engine rejects non-LONG/SHORT (`execution/engine.py:78-82`);
  API uses `Literal["LONG","SHORT"]` + case-normalizing validator → 422
  (`api/execution.py:14-26`); `test_direction_validation.py`.
- **[HIGH] N2-H3 — FAILED consumed idempotency ID** — `[FIXED/COMPLETED]`.
  ID marked only on EXECUTED (`execution/engine.py:170-177`); retry test passes.
  Residual race (check-then-add not atomic) = NEW-07, deferred.

## Medium findings (original) — statuses

- **N2-M1 Gate fail-open unknown modes** — `[FIXED/COMPLETED]` (explicit final
  `raise SafetyViolation`, `safety.py:97-100`).
- **N2-M2 Backtest spread/asymmetric slippage** — `[FIXED/COMPLETED — DIFFERENTLY]`
  (documented fill methodology in `backtest/engine.py:14-28` + characterization
  tests; accepted as intentional).
- **N2-M3 Break-even fixed point 0.01** — `[PARTIAL — NOT FINISHED]` → tracked as
  **NEW-02**: per-symbol point is now used, but the offset multiplies *point size*
  where *pip size* is required; offset rounds to zero (verified numerically:
  `round(1.085 + 0.1×0.00001, 5) = 1.085`; `round(2400.0 + 0.1×0.01, 2) = 2400.0`).
  The new test passes only because `pytest.approx` tolerates the missing offset.
- **N2-M4 PositionManager omits broker info; NAS100 split** —
  `[FIXED/COMPLETED]` (`position_manager.py` accepts `symbol_info`; NAS100
  precedence documented in ADR text and locked by tests).
- **N2-M5 Ruin thresholds inconsistent** — `[FIXED/COMPLETED — DIFFERENTLY]`
  (distinct named constants `MONTE_CARLO_RUIN_THRESHOLD_PERCENT=50.0` and the
  walk-forward 20% variant, documented as different methodologies).
- **N2-M6 Inaccessible state dir fails open** — `[FIXED/COMPLETED]`
  (`stop_state.py:71-94` explicit `os.stat`, FileNotFoundError vs OSError;
  empty/malformed treated active).
- **N2-M7 Close loop abandons basket; risk-evaluate bypassed max-open** —
  `[FIXED/COMPLETED]` (`continue` in grid close loop; `api/risk.py:58-66` passes
  the real open count).
- **N2-M8 Side-agnostic marking** — `[FIXED/COMPLETED]`
  (`get_latest_price(side=...)`, side computed per open positions in
  `api/execution.py:35-48`).

## Low findings (original) — statuses

- **N2-L1 minor items** — `[FIXED/COMPLETED]` except: `SECRET_KEY` still unused
  (NEW-06, deferred); idempotency race (NEW-07, deferred); HTF/LTF same-slice
  documented as accepted limitation; close-all in-memory-only now documented in
  the endpoint docstring (`api/execution.py:104-109`); drill noise removed.
- **L-2 silent sentinel persistence failure** — `[FIXED/COMPLETED]`
  (trigger/reset return persistence status; API message appends a warning).
- **L-3 non-constant-time token compare** — `[FIXED/COMPLETED]`
  (`hmac.compare_digest`, `deps.py:47`).
- **L-5/L-6 test pollution / weak assertions** — `[FIXED/COMPLETED]` mostly;
  some tolerances remain (deferred with NEW-02 family).
- **L-7 NAS100 ambiguity** — `[FIXED/COMPLETED — DIFFERENTLY]` (documented).
- **L-8 cosmetic blank lines** — `[PARTIAL — NOT FINISHED]` (NEW-08).

---

# Post-fix re-review (this session)

## Verification performed independently

- `python -m ruff check app scripts --statistics` → **0 errors** (was 120). Exit 0.
- `python -m pytest tests -q` → **316 passed, 1 warning in 17.74s** (was 263).
- `python docs/baseline/contract_diff.py` → **checked=19 diffs=0**, exit 0;
  `sys.exit(1 if diffs else 0)` confirmed in source; wired into CI
  (`ci.yml:42` runs it).
- E-04 drill output now records **25 PASS lines** including 2c (close allowed
  under sentinel) and 5b (close intent in all five bots).
- `intent="close"` verified at all five bot close sites (daemon:127, demo:117,
  ultra:123, gold:338, grid:227); entry sites retain default entry intent.
- Grid bot: protective SL wired to both base and averaging orders;
  close loop continues past per-ticket refusals.
- `test_bot_gate_control_flow.py` (11 KB) drives real bot methods with a stubbed
  `MetaTrader5` module and asserts actual `order_send` outcomes — this properly
  replaces the earlier 45-line text-window test.
- Fix commits inspected: `9edfec1`, `ab665a6`, `884b411`, `0e5399b`, `360e490`,
  `03f3247`, `02708f8`, `2c94d2f`, `8c894cc` (9 commits; total now 44 vs main).

## Review of the other session's re-review (`docs/PHASE2_RE_REVIEW.md`)

That document is accurate and its findings reproduce. Independent confirmation:

- **NEW-01 [HIGH] `[NOT FIXED — WILL COMPLETE NEXT]` — Silent DEMO/LIVE → MOCK
  fallback can simulate real-money orders.** Confirmed by direct read:
  `deps.py:68-73` — in DEMO/LIVE, if `RealMT5Adapter.connect()` fails, a mock is
  returned silently; the gate allows MOCK in every mode, so a LIVE API with a dead
  terminal returns `EXECUTED` for a simulated fill. The test
  `test_demo_falls_back_to_mock_without_terminal` enshrines the fallback as
  intended and no operator-visible signal distinguishes simulated from live.
  This is the exact "no silent LIVE→MOCK fallback" property the safety model
  claims. Must fix before PR: fail closed for LIVE/DEMO when the real terminal is
  unavailable, or surface an explicit degraded/simulated state in health and the
  order result.
- **NEW-02 [MEDIUM] `[NOT FIXED — WILL COMPLETE NEXT]` — Break-even offset uses
  point size instead of pip size; rounds to zero.** Confirmed numerically
  (`execution/engine.py:275-277`): offset = `pips × point`; on EURUSD
  `round(1.085 + 1e-6, 5) = 1.085`, on gold `round(2400 + 0.001, 2) = 2400.0`.
  Canonical pip sizes are 0.0001 / 0.1 (`pricing.pip_size`). The test's
  `pytest.approx(1.085 + 0.000001)` passes despite the rounded-away offset, so it
  does not prove the intended offset. Fix: use `pip_size` for the offset and
  assert the exact moved SL.
- **NEW-03 [MEDIUM] `[NOT FIXED — WILL COMPLETE NEXT]` — Contract diff exempts all
  values for `/api/liquidity/levels` and `/api/strategy/patterns`.** Confirmed
  (`contract_diff.py:49-51,91-95` `KEYS_ONLY_PATHS`): value regressions in those
  two endpoints can no longer fail CI. Restore value-level checks (normalize the
  volatile fields precisely) or add invariants.
- **NEW-04..NEW-08 [LOW] `[OPEN — DEFERRED]`** — all confirmed as stated by that
  review: local-date rollover (`risk/engine.py:49,55` uses `date.today()`, rest of
  system is UTC); health `mt5_connected` always true in PAPER/BACKTEST (mock
  adapter reports connected); `SECRET_KEY` defined but unused; idempotency
  check-then-add race (pre-existing); trailing blank lines in `main.py`.

## New findings from this re-review (not in either prior review)

1. **R2-N1 [LOW] `[NOT FIXED — WILL COMPLETE NEXT]` — Protective-SL digit
   heuristic mis-rounds non-EUR/non-gold symbols.**
   `backend/app/scalper/grid_martingale_bot.py:45-48`: `digits = 5 if "EUR" in
   self.symbol else 3`. GBPUSDm (5-digit) gets its SL rounded to 3 decimals, and
   2-digit index symbols get 3 decimals — a stop price not aligned to the symbol's
   point can be rejected by the broker (invalid stops), silently disabling the
   disaster stop. Fix: derive digits from the symbol spec / `pip_scale_for`
   instead of the EUR heuristic.
2. **R2-N2 [LOW] `[OPEN — DEFERRED]` — `intent="close"` is caller-trusted.**
   Any future call site that labels an *entry* as `intent="close"` bypasses the
   sentinel entirely (mode rules still apply). Currently mitigated by the
   control-flow tests and the E-04 5b drill lines; add a grep/audit rule to the
   E-05 checklist so new sites must justify their intent.
3. **Security note (out of repo):** a credential-looking string
   (`apikey_2180dc63…`) was pasted into the chat session by the operator. Verified
   it does **not** appear anywhere in the repository (`git grep` clean). If that
   key is real, rotate it — pasting it in chat exposes it regardless of repo state.
4. **Re-baseline note (informational):** commit `02708f8` re-baselined the
   `/api/execution/orders` samples after the direction-validation change rather
   than diffing old-vs-new; acceptable since the change was deliberate and
   reviewed, but it means E-03 no longer proves that endpoint unchanged from the
   original pre-refactor baseline.

## Claims from the fix session (verified)

| Claim | Independent evidence | Assessment |
|---|---|---|
| Ruff gate green | re-run: All checks passed | Confirmed |
| Suite 316 passed | re-run: 316 passed, 1 warning | Confirmed |
| Build passes | build re-run by other re-review; sources consistent | Confirmed (not re-run here) |
| Contract diff diffs=0 + CI | re-run: checked=19 diffs=0; exit code + CI wiring read | Confirmed (value-exemption caveat NEW-03) |
| E-04 25 checks | drill output read | Confirmed |
| Close intent at 5 sites | grep + drill 5b | Confirmed |
| Protective SL on grid | code read | Confirmed |
| Risk accounting live | code + tests read | Confirmed |
| Direction validation | code + tests read | Confirmed |
| Retry-safe idempotency | code + tests read | Confirmed |

## Required actions before PR (updated)

- **Must fix before PR** `[NOT FIXED — WILL COMPLETE NEXT]`
  - NEW-01: DEMO/LIVE adapter fallback must fail closed or be operator-visible;
    never return `EXECUTED` for a simulated fill in a real-money mode.
- **Strongly recommended before PR** `[NOT FIXED — WILL COMPLETE NEXT]`
  - NEW-02: break-even offset must use `pip_size`; tighten the test.
  - NEW-03: restore value-level contract checking for the two KEYS_ONLY endpoints.
  - R2-N1: protective-SL digit alignment for non-EUR/non-3-digit symbols.
- **Can be deferred with explicit documentation** `[OPEN — DEFERRED]`
  - NEW-04 (UTC day boundary), NEW-05 (health semantics), NEW-06 (`SECRET_KEY`),
    NEW-07 (idempotency race), NEW-08 (cosmetic), R2-N2 (intent audit rule),
    D-06 scratch-Postgres, E-06 Docker smoke, live-broker verification.

## Final verdict

**Ready after targeted fixes.**

All original blockers from Reviews 1 and 2 are `[FIXED/COMPLETED]` and were
independently re-verified (lint gate green, closes untrapped, PAPER flow
host-independent, risk accounting live, direction validated, retries safe,
fail-closed sentinel and gate). Remaining open work: NEW-01 (must fix),
NEW-02/NEW-03 and R2-N1 (strongly recommended), plus the deferred low items.
Once NEW-01 lands with its refusal test, the branch is fit for PR review.
