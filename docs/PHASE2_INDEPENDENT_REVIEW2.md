# Independent Phase 2 Implementation Review

> Second independent review (Review 2). Read-only review of branch
> `refactor/consolidation` vs `main`. No source, config, or Git history modified;
> only this document is added. Date (UTC): 2026-09-17.
> Review 1 (`docs/PHASE2_INDEPENDENT_REVIEW.md`) was consulted only after
> independent findings were formed. Confirmations are marked; emphasis is on what
> Review 1 missed or understated. `AGENTS.md` does not exist. Suite re-run: 263 passed.

## Executive summary

- Overall implementation condition: large and largely genuine. Gate, sentinel, DI,
  pricing, research consolidation, frontend client, CORS, token gate are present.
  Diff confirmed: 197 files, +10350/-1360. Suite reproduced: 263 passed, 1 warning.
- Whether ready for another review or PR preparation: not ready for PR review or
  PR preparation. Three Review 1 blockers confirmed (120-error lint gate, sentinel
  blocking closes, mode-unaware adapter). This review adds further blockers:
  dead daily counters, unvalidated direction mapping to SELL, FAILED consuming
  idempotency IDs, fail-open unknown-mode fall-through, backtest spread omission,
  fixed break-even point size, inaccessible-dir fail-open.
- Most important concerns: (1) `ruff check app scripts` = 120 errors so D-04 fails;
  (2) emergency stop traps grid basket with no broker SL/TP and gated closes;
  (3) default PAPER API flow refused on MT5 hosts; (4) daily limits dead, direction
  unvalidated, retry impossible after FAILED. No numeric score is given.

## Repository and Git verification

- Branch: `refactor/consolidation` confirmed via `git branch --show-current`.
- Commit count: reported 35, verified 34 (`git rev-list --count main..HEAD`).
  HEAD `dc07cba`, merge-base `3ebf3a8`. Off by one (agrees with Review 1).
- Diff scope: `197 files changed, 10350 insertions(+), 1360 deletions(-)` confirmed.
- Git cleanliness: `git status --short` shows only untracked review docs;
  `git diff --check main...HEAD` clean.
- Unexpected files: no `.env`, keys, DB files, `node_modules`, `.next`, or
  `backend/state/` tracked. `backend/state/` gitignored. Deleted as intended:
  root `app/`, `fusion_2.0.py`, `intelligence/logger.py`, `scalper/config.py`.
  `recharts` removed from `frontend/package.json`. Baselines include opaque binary
  txt files (harmless).

## Task verification

Verdicts: Verified, Partially verified, Not verified, Contradicted.

| Task | Claimed status | Evidence found | Missing or concerning details | Verdict |
|---|---|---|---|---|
| A-01 | complete | branch + docs in `98eb4fe` | none | Verified |
| A-02 | complete | `docs/baseline/` manifest + 19 samples + tooling | mock-only, binary baselines | Verified |
| A-03 | complete | `requirements.txt:13` pin `<0.24` | none | Verified |
| B-01 | complete | `api/deps.py` AppState + `ExecutionEngine(adapter, risk_engine)`; no module-level service | `build_adapter()` prefers Real regardless of mode; tests host-dependent | Partially verified |
| B-02 | complete | `core/pricing.py`; M-fix `instrument.py:33-35`; characterization first | dual pip conventions | Verified |
| B-03 | complete | `core/safety.py` table; 12 sites gated + engine | blocks closes; unknown-mode fall-through; textual gate test | Partially verified |
| B-04 | complete | 4 deletions, no refs | none | Verified |
| B-05 | complete | `core/stop_state.py` + subprocess test | silent write failure; inaccessible-dir open; docstring mismatch | Partially verified |
| C-01 | complete | spec PnL; 502; `get_latest_price` | cost change untested; NAS100 split; break-even point bug | Partially verified |
| C-02 | complete | `last_trades`; `BT_` IDs; seeded RNG | spread ignored; HTF/LTF same slice; ruin mismatch | Partially verified |
| C-03 | complete | `mt5_orders.py`; bots + demo script; None-guards | gated closes; close-loop early return | Partially verified |
| C-04 | complete | `research/common/*`; `_bootstrap.py` | 5 scripts use bootstrap; 10 hash defs remain | Partially verified |
| C-05 | complete | `lib/api.ts`, token, types, confirms, badge; recharts gone | token on GETs; bundle-visible | Verified |
| C-06 | complete | CORS in `main.py:46-53`; env; Redis gone; Alembic placeholder | README deeper fixes absent | Partially verified |
| C-07 | complete | `mt5_real.py:192-194` magic/comment | none | Verified |
| D-01 | complete | `api/deps.py:31-50` gate on mutating endpoints | non-constant-time compare | Verified |
| D-02 | complete | 13+ new test files green | weak/textual tests; missing close/direction/retry/counter tests | Partially verified |
| D-03 | complete | no swallow; None-guards at direct sites | engine lacks None-guard for custom adapters | Partially verified |
| D-04 | complete | CI jobs added; `pyproject.toml` F-only | `ruff check app scripts` = 120 errors | Contradicted |
| D-05 | complete | `risk/engine.py:87-98`; yaml default 0 | unreachable while counters dead | Partially verified |
| D-06 | complete | ini placeholder; `env.py` env URL; README `create_all` | no scratch Postgres run | Partially verified |
| E-01 | complete | reproduced 263 passed, 1 warning | none | Verified |
| E-02 | complete | build reproduced by Review 1 | manual walkthrough not verifiable | Partially verified |
| E-03 | complete | `contract_diff.py` checked=19 diffs=2 | always exit 0, not in CI, wall-clock unproven | Partially verified |
| E-04 | complete | drill output present | 19 PASS not 20; no close/bot-loop coverage | Partially verified |
| E-05 | complete | dead-code greps clean | single-hash claim false; 16 F401 remain | Partially verified |
| E-06 | complete | Redis gone, no refs | Docker run not reproduced here | Not verified |

## Critical findings

### [CRITICAL] C-1 — CI lint gate fails (confirms Review 1)
- Files: `.github/workflows/ci.yml:58-59`; `backend/pyproject.toml:5-12`; e.g.
  `app/api/backtest.py:69`, `app/backtest/engine.py:91`,
  `app/execution/engine.py:139`, `app/core/config.py:1`,
  `scripts/run_phase18_calibration.py:26`, `scripts/run_phase19_edge_discovery.py:27`.
- Wrong: `ruff check app scripts` = Found 120 errors (88 F541, 16 F401, 14 F841, 2 F821).
- Matters: D-04 done-condition unmet; push = red CI; limitation line misleading.
- Repro: `cd backend; python -m ruff check app scripts --statistics`.
- Fix: repair F401/F841/F821; decide F541; re-run to zero.
- Blocks PR: Yes.

### [HIGH] H-1 — Sentinel blocks protective closes; grid has no broker SL (confirms Review 1, adds detail)
- Files: `app/core/safety.py:39-44`; `app/scalper/grid_martingale_bot.py:164-170,189-213,77-86`;
  `app/scalper/mt5_orders.py:40-51`; gated closes in daemon/ultra/demo/gold bots.
- Wrong: closes gated like entries; grid omits SL/TP; close loop returns on first refusal.
- Matters: stop traps uncapped basket; contradicts ADR-8 bot-command close claim.
- Repro: temp STATE_DIR, trigger, call `_close_all_grid_positions` with stubbed mt5.
- Fix: gate only risk-increasing sends; close-allowed path; continue loop; broker SL; test.
- Blocks PR: Yes.

### [HIGH] H-2 — Adapter ignores mode; PAPER regresses on MT5 host (confirms Review 1)
- Files: `app/api/deps.py:53-60,63-74`; `app/core/safety.py:56-61`; `app/core/config.py:28`.
- Wrong: Real preferred even in PAPER; gate then refuses every API order on MT5 host.
- Matters: contradicts ADR-3 mock-paper promise; unlisted behavior change.
- Repro: MT5 host, PAPER, `POST /api/execution/orders` -> 400 forbids real send.
- Fix: mode-aware `build_adapter()`; PAPER test independent of host.
- Blocks PR: Yes.

### [HIGH] N2-H1 — Daily counters never updated (missed by Review 1)
- Files: `app/risk/engine.py:43-46,118-148`; `app/execution/engine.py:69-192`;
  `app/api/risk.py:23-26`. Grep finds no increments outside tests.
- Wrong: `maximum_trades_per_day` / daily-loss locks can never fire; no rollover.
- Matters: enabling limits gives false confidence.
- Repro: set limit 1, execute two mock orders, count stays 0.
- Fix: record on EXECUTED/close; rollover; tests.
- Blocks PR: Yes.

### [HIGH] N2-H2 — Direction unvalidated, non-LONG becomes SELL (missed)
- Files: `app/api/execution.py:11-18`; `app/execution/engine.py:135,217,254,278`.
- Wrong: free-form `direction`; typo like `long` opens a short.
- Matters: silent side flip is a safety defect.
- Repro: POST `direction: GARBAGE` -> SELL execution.
- Fix: Literal/pattern validation -> 422; normalize case explicitly.
- Blocks PR: Yes.

### [HIGH] N2-H3 — FAILED consumes idempotency ID (missed)
- Files: `app/execution/engine.py:78-80,124-125,163-164`.
- Wrong: ID marked before send; broker FAILED blocks legitimate retry.
- Matters: transient failure becomes permanent rejection.
- Repro: same `client_signal_id`, first FAILED, second -> duplicate REJECTED.
- Fix: mark only on EXECUTED or separate send-attempt tracking.
- Blocks PR: Yes.

### [MEDIUM] N2-M1 — Gate fail-open for unknown modes (understated by Review 1)
- Files: `app/core/safety.py:72-78`. No final raise; future mode falls through to allow.
- Fix: explicit final `raise SafetyViolation`. Blocks PR: No (do with H-1/H-2).

### [MEDIUM] N2-M2 — Backtest ignores spread, asymmetric slippage (missed)
- Files: `app/backtest/engine.py:76-118`. `spread_pips` only for risk check; slippage only on SL.
- Fix: apply spread/slippage symmetrically or document + test. Blocks PR: No.

### [MEDIUM] N2-M3 — Break-even uses fixed point 0.01 (missed)
- Files: `app/execution/engine.py:194,231`; caller `app/api/execution.py:34`.
- Wrong: FX offset wrong by ~1000x when enabled.
- Fix: per-symbol point/pip lookup. Blocks PR: No (disabled by default).

### [MEDIUM] N2-M4 — PositionManager omits broker info; NAS100 split (missed)
- Files: `app/scalper/position_manager.py:60,95`; `app/data/mt5_mock.py:54` (20) vs
  `app/scalper/instrument.py:58` (1).
- Fix: pass symbol_info through; document intended NAS100. Blocks PR: No.

### [MEDIUM] N2-M5 — Ruin thresholds inconsistent (missed)
- Files: `app/backtest/monte_carlo.py:26` (50%) vs `app/backtest/walk_forward.py:118` (20%).
- Fix: single definition or distinct names. Blocks PR: No.

### [MEDIUM] N2-M6 — Inaccessible state dir fails open (understated)
- Files: `app/core/stop_state.py:62-85`. `is_file()` swallows OSError; outer branch unreachable.
- Fix: explicit stat handling; align docstring (empty file is active). Blocks PR: No.

### [MEDIUM] N2-M7 — Close loop abandons basket; risk-evaluate bypasses max-open (missed)
- Files: `app/scalper/grid_martingale_bot.py:189-213`; `app/api/risk.py:56-62` (count 0).
- Fix: continue-on-refusal; pass real open count. Blocks PR: No.

### [MEDIUM] N2-M8 — Side-agnostic marking; sweep methodology risk (missed)
- Files: `app/services/market_data.py:42-69`; commit `d524677` (~180 imports).
- Fix: side-aware marking; verify sweep hunks. Blocks PR: No.

### [LOW] N2-L1 — Minor items (missed or understated)
- `SECRET_KEY` default unused (`app/core/config.py:25`); backtest HTF/LTF same slice
  (`app/backtest/engine.py:146-152`); engine None-guard absent; token `!=` timing
  (`app/api/deps.py:44-50`); `close-all` in-memory only (`app/api/execution.py:82-94`,
  `app/execution/engine.py:290-297`); test pollution/dead lines; drill 2400.0 noise.

## Safety-spine review

Gate table correct for known modes; sentinel genuinely cross-process (subprocess test);
12 direct + 1 adapter sites all textually gate-preceded; ordering gate-before-risk-send
correct; unknown-adapter maps to REAL (fail-closed). Fail-open holes: unknown-mode
fall-through, inaccessible-dir open, silent write failure. Sentinel blocks entries by
design but also blocks closes (must change). Close-all API is in-memory only and must
not be read as flattening broker positions. Boot validator still refuses LIVE without
flags. Defaults safe (PAPER, flags false, localhost CORS, token off). Drill limitation
statement omits close-blocking.

## Numerical and trading-logic review

PnL `price_diff x contract x vol` correct with broker precedence; EURUSD/XAU expected
values independent and correct. NAS100 split (1 vs 20) needs a decision. Dual pip
conventions (`pricing.pip_size` canonical vs `mt5_orders.pip_scale_for` legacy) are a
trap. Spread rescaling documented; gate disabled. Risk sizing consistent on mock.
Backtest: deterministic IDs, seeded RNG, commission deducted, no new look-ahead beyond
`candles[:i+1]`; but spread ignored, slippage asymmetric, HTF/LTF identical slices.
Monte Carlo now uses `last_trades`; noise seeded. Ruin definitions differ. UTC handling
clean. Live-broker values unverified (report is honest).

## API, security, and deployment review

Token enforced only in production with token set; 401 on missing/wrong; dev open by
design; `!=` should be `hmac.compare_digest`. CORS wildcard removed; explicit origins.
Contract 17/19 plausible but tool exits 0, not in CI, heavy normalization. Direction
unvalidated; risk-evaluate count fixed at 0. DB `create_all` official; Alembic
placeholder + env URL; no scratch Postgres proof. Redis removed; compose coherent
(hardcoded password pre-existing). No secrets committed. `SECRET_KEY` unused default.

## Test adequacy review

98 new tests; suite green. Strong: subprocess sentinel, propagation, truth table,
characterization-first, determinism, magic stub, CORS/token matrices. Weak: gate test
is 45-line text window; no close-under-sentinel, direction, FAILED-retry, counter,
FX break-even, spread, write-failure, concurrency, permission tests; `/run` contract
re-runs in-process; global `app.state` mutation; `<5.0` price windows; no per-bot
fake-mt5 control-flow tests. Mocks appropriate at MT5 boundary.

## Claims from the implementation report

| Claim | Evidence | Assessment |
|---|---|---|
| Branch refactor/consolidation | `branch --show-current` | Confirmed |
| 35 commits | `rev-list --count` = 34 | Misleading or inaccurate |
| 27 tasks complete | per-task table | Confirmed but limited |
| 197 files +10350/-1360 | diff stat | Confirmed |
| 263 passed 1 warning | reproduced 10.35s | Confirmed |
| Frontend build passed | Review 1 reproduced | Confirmed |
| Docker smoke healthy | Redis removal yes; run not reproduced | Not independently verified |
| E-04 20 checks | 19 PASS lines | Misleading or inaccurate |
| 13 sites gated | 12+1 all preceded | Confirmed |
| Token/CORS verified | tests + code | Confirmed |
| 17/19 wall-clock | tool + DI-only routers | Confirmed but limited |
| Forex/gold/candle/MC/IDs/seed fixes | code + tests | Confirmed (NAS100 ambiguous) |
| Ruff App Control | ruff runs, 120 errors | Misleading or inaccurate |
| Mocks only; README other branch; sweep restored | code/diff | Confirmed (sweep incomplete) |

## Required actions before PR

- Must fix before PR: C-1 (zero ruff); H-1 (close-allowed path, loop, SL);
  H-2 (mode-aware adapter); N2-H1 (counters); N2-H2 (direction validation);
  N2-H3 (idempotency).
- Strongly recommended before PR: N2-M1..M8; Review 1 M-1..M-6; missing regression
  tests; `contract_diff` non-zero exit + CI; F821 fixes; venv precedence decision.
- Can be deferred with explicit documentation: N2-L1; live-broker checks; Docker and
  scratch-Postgres proofs; report count corrections.

## Final verdict

**Not ready for PR review** — fails its own lint gate, traps de-risking under stop,
regresses default PAPER on MT5 hosts, and carries dead risk accounting, direction
fallback, and retry defects. Targeted fixes then focused re-review.
