# Strategy Independence Refactoring — Phase 1 Investigation & Implementation Plan

> **Phase:** 1 — investigation and planning **only**. No source file was modified to
> produce this document.
> **Method:** direct reading of the implementation on branch `refactor/consolidation`
> (post–Phase 2 tree). Every claim below cites a file verified by import/call-graph
> inspection, not directory names or README assertions. Where the README disagrees
> with the code, the code wins and the discrepancy is called out.

---

## 1. Executive summary

**The platform does not have one strategy with a clean boundary around it. It has
approximately eight decision-making implementations behind three mutually
incompatible signal schemas, and none of the documented "plugin" machinery is on
any runtime path.**

Concretely:

1. The **live path** (`api/signals.py`, `runner.py`, candle backtester) uses
   `StrategyEngine.evaluate_setup()` → `TradeSignal` (LONG/SHORT/NEUTRAL).
2. The **tick path** (`backtest/tick_backtest.py`) uses a *different, fully separate*
   pipeline: `ScalpStrategyEngine` → `ScalpSignal` (BUY/SELL/NONE), plus its own
   regime gate, fusion score, cooldown, risk engine instance, and position manager.
3. The **five bots + demo script** each embed their own entry logic (EMA/momentum/
   alternating) and talk to MT5 directly; they consume no strategy object at all.
4. The **documented plugin system** (`StrategyPlugin`/`UnifiedSignal`/6-stage gate in
   `strategy/plugin.py`) is imported **only by tests** — zero runtime consumers.

The good news, and the reason this refactor is small rather than large:

- **`RiskEngine.evaluate_trade_risk` and `ExecutionEngine.execute_signal` are already
  strategy-agnostic.** They consume plain dicts with exactly five decision fields
  (`symbol`, `direction`, `entry_price`, `stop_loss`, `take_profit`) plus an ID.
  A de-facto platform contract already exists; it is just not named, not enforced,
  and bypassed by every path except API-orders/runner/candle-backtest.
- **DI already exists** (`api/deps.py` + `app.state`); the strategy is constructed in
  exactly three runtime places (`api/deps.py:64`, `backtest/engine.py:42`,
  `runner.py:42`).

**The plan, in one paragraph:** name the de-facto contract (`StrategyDecision`,
LONG/SHORT only), put one narrow `StrategyProvider` seam (construct + `evaluate`)
behind the three construction sites, make both backtesters consume the same seam
(the tick backtester keeps its own fill model but takes its decisions through it),
give each strategy its own config section, quarantine the research-only packages
with an explicit label instead of moving them, and leave risk, execution, safety,
persistence, and the bots' loops alone. The abandoned plugin ABC is deleted, not
revived. Estimated: ~10 focused commits, no behavior change when the current
strategy is re-registered behind the seam.

---

## 2. Current architecture understanding

### 2.1 Runtime entry points (verified)

| Entry | Process | Decision source | Order path |
|---|---|---|---|
| FastAPI (`app/main.py` + 9 routers) | API | `StrategyEngine` via `api/deps.py` DI | `ExecutionEngine` (gated) |
| `app/runner.py` autonomous loop | own process | `StrategyEngine` constructed inline | `ExecutionEngine` (gated) |
| Candle backtest (`backtest/engine.py`, `/api/backtest/*`) | API process / tests | `StrategyEngine` constructed inline | own inline fill/exit math, own `RiskEngine` |
| Tick backtest (`backtest/tick_backtest.py`) | tests / research scripts | `ScalpStrategyEngine` + regime + fusion + selector + cooldown, all constructed inline | own fill model + `ScalpPositionManager`, own `RiskEngine` |
| 5 bots (`scalper/*_bot.py`, `*_daemon.py`, `*_engine.py`) + `scripts/run_demo_trader.py` | own processes | inline entry logic each | direct `mt5.order_send` (gated post–Phase 2) |
| Research scripts (`scripts/run_phase*.py`) | one-shot | phase engines | none (artifacts only) |

### 2.2 Market-data flow (verified)

`MarketDataService(adapter)` → `fetch_candles` / `get_symbol_info` / `get_latest_price`
is the only market-data seam and is already strategy-agnostic. Adapter selection is
mode-aware via the single `app/data/adapter_factory.build_adapter` used by both the
API and `runner.py`. **Input assembly is not centralized:** `api/signals.py:15-16`
hardcodes H1/100 + M5/200 fetches, `runner.py:56-57` the same, `backtest/engine.py`
receives caller-supplied candles, tick consumers build `TickBuffer`s themselves. A new
strategy needing different inputs (ticks, H4, more history) must edit each call site.

### 2.3 What `StrategyEngine` actually is (verified, `strategy/engine.py`)

A 10-step ICT/SMC scalp evaluator. Constructor reads `settings.strategy_config`
(`entry.*`, `timeframes.ltf`, `market_structure.swing_lookback`, `sessions.*`) **and**
falls back to `settings.risk_config["stops_and_targets"]` for SL/TP distances — i.e.
the strategy's stop/target sizing policy is split across two config files. It
internally constructs six sub-engines plus `SessionFilter`, takes
`(symbol, htf_candles, ltf_candles, point_size)`, and returns a `TradeSignal`.

### 2.4 The three signal schemas (verified)

| Schema | Direction vocab | Price fields | ID field | Reasons | Live consumers |
|---|---|---|---|---|---|
| `TradeSignal` (`strategy/engine.py:17-33`) | LONG/SHORT/**NEUTRAL** | entry_price/stop_loss/take_profit | client_signal_id | free-form dict (embeds sweep/FVG/OB dicts) | runner, candle backtest, `/signals` |
| `ScalpSignal` (`scalper/signal.py`) | BUY/SELL/**NONE** | entry_reference/stop_reference/target_reference | signal_id | string list | tick backtest only (hand-remapped at `tick_backtest.py:210-214`) |
| `UnifiedSignal` (`strategy/plugin.py:15-38`) | LONG/SHORT/**FLAT** (enum) | entry_price/stop_loss/take_profit | signal_id | reason_codes + market_state + strategy_name/version | **none at runtime (tests only)** |

`tick_backtest.py:210-214` hand-translates `ScalpSignal` fields into execution-dict
keys — machine evidence the schemas do not align.

### 2.5 Config split (verified)

- `config/strategy.yaml` (74 lines) is 100% ICT-scalp-specific: every section names a
  pattern engine (`market_structure`, `liquidity`, `displacement`, `fvg`,
  `order_block`, `sessions`, `entry`). Well isolated in one file — but a new
  strategy needs a wholly different shape, and `StrategyEngine.__init__` also reads
  `risk.yaml:stops_and_targets` as a fallback (cross-file sizing policy).
- `config/risk.yaml` is generic (limits, stops/targets defaults, position
  management, symbol mappings). No strategy concepts inside. **Do not split.**
- `.env` / `Settings` is platform + safety flags. No strategy content. **Do not split.**

---

## 3. Current strategy dependency map

```text
Current Architecture (runtime imports only)

                 ┌──────────────────────────────┐
                 │  api/structure, liquidity,   │── direct imports of 6 sub-engines
                 │  setups  (analysis pages)   │   (duplicates engine.py pipeline)
                 └──────────────┬───────────────┘
                                │
  api/signals ──► StrategyEngine ──► {structure, liquidity, displacement,   ┐
  runner ───────► StrategyEngine ──►  fvg, sweeps, order_block, sessions}   │ ICT/SMC
  backtest ─────► StrategyEngine ──► TradeSignal ──► RiskEngine ──► ...     │ internals
                                                └─► ExecutionEngine (API/runner only)
                                                                       ────┘
  tick_backtest ─► ScalpStrategyEngine ──► ScalpSignal ──► own risk/cooldown/fills
       ▲                  ▲
       │                  └── regime/fusion/selector (tick-pipeline-only users)
  5 bots: inline entry logic ──► mt5 direct (no strategy object anywhere)

  strategy/plugin.py (StrategyPlugin/UnifiedSignal/gate): NO inbound runtime edges.
  context/, intelligence/, information/, swing/: NO inbound runtime edges
      (research + scripts + tests only).
  risk/, execution/, safety/, pricing/, models/: NO strategy imports at all.
```

Strategy-specific edges crossing into generic areas (the coupling inventory):

1. **C1.** `api/setups.py:31-52` re-implements the strategy's 6-engine analysis pipeline
   inline (structure→liquidity→displacement→FVG→sweeps→order-blocks), duplicating
   `StrategyEngine.evaluate_setup` steps 2–6 without signal assembly.
2. **C2.** `api/structure.py`, `api/liquidity.py` import ICT sub-engines directly.
3. **C3.** `api/signals.py:15-32` hardcodes input assembly (H1/100, M5/200,
   `point_size` plumbing) and returns `signal.to_dict()` verbatim, including
   `setup_type` (`"SCALP_BULLISH_SWEEP"`), `confidence` (hardcoded 0.85), `timeframe`
   label, and free-form `reasons` with embedded sweep/FVG/OB dicts.
4. **C4.** `api/deps.py:64,89` constructs and type-annotates the concrete
   `StrategyEngine`; `backtest/engine.py:42`, `runner.py:42` hardcode it too.
5. **C5.** Candle backtest manages fills/exits inline (`backtest/engine.py:80-142`)
   instead of using `ExecutionEngine`; tick backtest has a third fill model
   (`tick_backtest.py:128-160` + `ScalpPositionManager`). Strategy behavior therefore
   cannot be compared across modes — each mode re-implements execution semantics.
6. **C6.** `ScalpStrategyEngine.generate_signal` takes `ScalperFeatures` (tick
   aggregate) while `StrategyEngine.evaluate_setup` takes candle lists — two
   incompatible strategy-input shapes, so no single backtester can serve both.
7. **C7.** `tick_backtest.py:209` mutates its own `risk_engine.maximum_spread_pips`
   mid-run; `tick_backtest.py:56,63` hardcodes strategy + risk thresholds inline.
8. **C8.** `StrategyEngine.__init__` reads `risk.yaml:stops_and_targets` as fallback
   for SL/TP distances — sizing policy split across strategy config and risk config.
9. **C9.** `SignalModel` (`models/domain.py:69-82`) mirrors `TradeSignal`
   (`setup_type`, `confidence`, `reasons` JSON). Write-never at runtime (only
   `test_database.py` touches it), so this is latent, not live, coupling.
10. **C10.** Frontend `/strategy` page renders ICT nouns (`fvg_type`,
    `mitigation_status`, sweep/order-block lists); `/orders` renders `setup_type`,
    `risk_reward`, raw `reasons` JSON. Display survives schema change only where it
    stays generic (lists, JSON blob); labels do not.
11. **C11.** The 5 bots embed entry logic with zero shared decision interface; each
    bot is effectively a forked strategy+execution bundle (plumbing is now shared
    via `mt5_orders.py`; decisions are not).
12. **C12.** `strategy.yaml` is entirely ICT-shaped; a new strategy cannot reuse a
    single key of it (except the file's existence).

Not coupling (verified, do not touch on this evidence):
- `RiskEngine`, `ExecutionEngine`, `core/safety.py`, `core/pricing.py`,
  `core/stop_state.py`, `MarketDataService`, adapters — zero strategy imports.
- `context/`, `intelligence/`, `information/`, `swing/` — zero runtime inbound
  edges; they are research code with runtime-sounding names, not platform coupling.

---

## 4. Actual strategy/platform boundary

Derived from what risk and execution provably consume today (both take plain dicts):

**The platform contract is five decision fields plus identity and status:**

```text
Strategy input (provided BY the platform):
  symbol: str
  candles: dict[timeframe -> list[candle]]   # today: {"HTF": [...], "LTF": [...]}; strategy-owned choice of keys
  point_size: float
  config: dict                               # the strategy's OWN section only

Strategy output (returned TO the platform):
  symbol, direction ∈ {"LONG", "SHORT"}, entry_price, stop_loss, take_profit,
  client_signal_id, status ∈ {"APPROVED", "REJECTED"},
  setup_type: str (opaque label), confidence: float,
  reasons: dict (opaque to the platform; rendered verbatim by the UI)

Ownership:
  strategy decides:   entries, indicators/features it needs, SL/TP proposal,
                      setup taxonomy, confidence, its config shape
  risk decides:       sizing, RR gating, limits, locks, approval (unchanged)
  execution decides:  idempotency, sync, sends, fills, lifecycle (unchanged)
  backtest decides:   fill realism (spread/slippage/commission/latency),
                      determinism, metrics (unchanged)
  UI receives:        the decision dict verbatim + aggregate pattern data for
                      analysis pages (see E3 scoping)
```

Classification of the surrounding pieces (§4 A/B/C):

- **(A) True strategy dependency — must move behind the seam:** `StrategyEngine`
  + 6 sub-engines as used by live paths; `ScalpStrategyEngine` + `ScalperFeatures`
  input shape; per-bot entry methods; `strategy.yaml` content; `setup_type`/
  `confidence`/`reasons` producers.
- **(B) Generic infrastructure — must not change:** `RiskEngine`,
  `ExecutionEngine`, `core/safety.py`, `core/pricing.py`, `core/stop_state.py`,
  `MarketDataService`, adapters + `adapter_factory`, DI container, token/CORS,
  `PositionRecord`/audit shapes, backtest metrics, Monte Carlo, walk-forward.
- **(C) Reusable strategy-support — candidate, evaluate per item:**
  `InstrumentSpecification` + `core/pricing` (keep shared: every strategy needs
  pip/contract math — already generic); `TickEngine`/`TickBuffer` + candle types
  (keep shared as *input* building blocks, not strategy); `MarketRegimeEngine`/
  `SignalFusionEngine`/`StrategySelector`/`CooldownManager` (used only by the tick
  pipeline today — keep them importable where they are; do NOT promote to a generic
  "platform layer" with no second consumer); `SessionFilter` (keep; both live
  strategies may use it).

---

## 5. Existing abstractions assessment

| Abstraction | Solves | Depended on by | Isolates strategy? | Verdict |
|---|---|---|---|---|
| `StrategyPlugin` ABC + `generate/evaluate/validate/explain` | nothing at runtime | tests only (`test_phase38`, `test_phase41`) | No — dead | **Delete the ABC** (keep `UnvalidatedResearchStrategy` + gate only if a test needs them; they are research fixtures, not platform). Do not revive it: 5 abstract methods with no caller is the speculative plugin system the constraints forbid |
| `UnifiedSignal` (19 fields incl. `strategy_name/version`, `market_state`, `data_snapshot_hash`) | research audit trail | tests only | N/A (unused) | **Do not adopt** as the platform contract: it forces every strategy to mint version/audit metadata the platform never reads; the 5-field decision dict is sufficient |
| `SignalQualityGate` (6 stages) | research gating demo | tests only; stage 4 hardcodes `UnvalidatedResearchStrategy()` (not generic) | No | **Leave in `strategy/` as research code**; do not wire into live paths (that would add an unowned approval layer) |
| `TradeSignal` dataclass | live signal shape | runner, backtest, signals API, 3 test files | Partially (fields, not construction) | **Keep as one implementation** of the new seam's output; slim its platform-visible surface to the §4 dict |
| `ScalpSignal` + `ScalpStrategyEngine` | tick-pipeline decisions | `tick_backtest.py` only | Within its pipeline | **Keep**; make it a second implementation behind the same seam via an adapter, not by merging the classes |
| `MarketDataService` + adapters | market-data seam | everything runtime | Yes | **Keep untouched** |
| `api/deps.py` DI | shared instances | all routers | Yes for engines | **Keep**; only the strategy accessor's concrete type changes |

---

## 6. Key coupling problems (ranked)

1. **Three schemas, four decision stacks (C1–C7, C11).** Replacing "the strategy"
   today means rewriting the ICT engine *and* the tick pipeline *and* each bot, plus
   hand-translations between schemas. This is the problem the refactor exists to solve.
2. **Strategy construction hardcoded in 3 runtime places + concrete DI type (C4).**
   No seam to substitute a different strategy for API, runner, or candle backtest.
3. **Input assembly lives in callers (C2, §2.2).** Timeframes/counts/point plumbing
   are router/runner literals; a tick- or H4-based strategy forces edits in each.
4. **SL/TP sizing policy split across `strategy.yaml:entry` and
   `risk.yaml:stops_and_targets` (C8).** A new strategy inherits a fallback chain it
   didn't ask for.
5. **UI/API surface mirrors ICT nouns (C3, C10).** `/strategy`, `/orders`, and
   `api.ts` types would all churn on a strategy change; `setup_type` strings and
   `reasons` internals are unversioned.
6. **Latent DB coupling (C9).** `SignalModel` hardcodes the TradeSignal shape; harmless
   today (write-never) but will mislead the first person to persist signals.

---

## 7. What is already sufficiently decoupled (do not touch)

- `RiskEngine`, `ExecutionEngine` (+ idempotency, locks, counters), safety gate,
  sentinel, pricing, adapters, `MarketDataService`, DI mechanics, token/CORS,
  backtest metrics/Monte Carlo/walk-forward math, position records and audit shape,
  research engines and artifacts, bot loops/plumbing/gate calls, config *files*
  `risk.yaml`/`.env` structure.
- `context/`, `intelligence/`, `information/`, `swing/` packages: research-only;
  do not move, rename, or "promote" — label them (one doc paragraph + package
  docstrings) and stop.
- `ScalpPaperExecutionEngine` (`scalper/execution.py`): test-only; leave it.

---

## 8. Proposed target architecture

```text
Proposed dependency direction (runtime)

  api/signals ──┐
  runner ───────┼──► StrategyProvider ──► concrete strategies ──► shared inputs
  backtest ─────┘   (construct + evaluate)   ICTStrategyAdapter     (MarketDataService,
                                     │        MomentumScalpAdapter    candles/ticks,
                                     │        <future>Strategy        specs, config)
                                     ▼
                              StrategyDecision (dict; §4 contract)
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              RiskEngine      ExecutionEngine   BacktestEngines
              (unchanged)     (unchanged)       (fill models unchanged;
                                                 take decisions via seam)

  api/structure, liquidity, setups ──► AnalysisProvider (opt-in, per-strategy;
      ICT sub-engines move behind it; default ICT implementation preserved)

  bots: unchanged loops/plumbing; entry call sites optionally take
        StrategyDecision later (explicitly out of the essential scope)

  research/*, context/*, intelligence/*, information/*, swing/*:
      untouched, labeled "research-only" (ADR-style note, no moves)
```

Concretely: one narrow seam module (new, e.g. `app/strategy/provider.py` — exact
home at implementer discretion) defining:
- `StrategyDecision` — the §4 output dict shape with validation (direction
  LONG/SHORT, finite positive prices, SL/TP on the correct side of entry, ID present);
- `StrategyProvider` — minimal interface: `name`, `configure(config)`,
  `evaluate(symbol, market_inputs, point_size, config) -> StrategyDecision`;
- `MarketInputs` — `{symbol, candles: {timeframe: [...]}, point_size}`; the strategy
  declares which timeframes it needs rather than receiving hardcoded H1/M5;
- a registry/factory mapping `strategy.name` (from config) to provider, defaulting
  to the current ICT engine.

Deliberately absent: a `StrategyPlugin`-style multi-method ABC, version/audit
metadata requirements, a generic "analysis framework", any new dependency.

---

## 9. Essential changes

### E1. Define and enforce the decision contract
- **Change:** new `StrategyDecision` validation (direction ∈ LONG/SHORT; finite
  prices; SL/TP correctly sided vs entry; `client_signal_id` present; status
  ∈ APPROVED/REJECTED). Rejecteds carry `rejection_reason` and never reach risk.
- **Why:** today the contract is implicit and dialect-fragmented (LONG/SHORT/NEUTRAL
  vs BUY/SELL/NONE vs LONG/SHORT/FLAT); `tick_backtest` hand-maps fields.
- **Scope:** one new module + unit tests. Consumers adopt gradually (E2–E4).
- **Dependency impact:** none until adopted (pure addition).
- **Benefit:** a strategy change can never again silently flip sides or drop fields;
  contract tests pin the boundary.
- **Risk:** near-zero (additive). **Validation:** contract unit tests incl.
  adversarial inputs (zero/negative prices, inverted SL/TP, unknown direction).

### E2. Introduce the `StrategyProvider` seam at the three construction sites
- **Change:** `api/deps.py` (construct + `get_strategy_engine` return type),
  `app/runner.py`, `app/backtest/engine.py` obtain the strategy from a
  name→provider factory (config key, e.g. `strategy.name`, default `"ict_scalp"`).
  Register the current `StrategyEngine` behind an `ICTStrategyAdapter` that keeps
  the exact current behavior (same inputs, same outputs).
- **Why:** removes the only hardcoding that forces multi-file edits per strategy.
- **Scope:** `strategy/provider.py` (new), `deps.py`, `runner.py`,
  `backtest/engine.py`, one registration test + wiring tests.
- **Dependency impact:** routers keep working; `/signals` response shape unchanged
  while the ICT provider is default.
- **Benefit:** swapping the default name + config is the whole "replace strategy"
  operation for API/runner/candle-backtest.
- **Risk:** low; behavior preserved by characterization (existing
  `test_signal_engine.py`, backtest tests). **Validation:** suite green + a test
  substituting a stub provider end-to-end through API and backtest.

### E3. Quarantine the ICT analysis pages behind the provider (narrowly scoped)
- **Change:** `api/structure.py`, `api/liquidity.py`, `api/setups.py` stop importing
  ICT sub-engines directly. Two options for the implementer, in preference order:
  (a) the active provider exposes an optional `describe(symbol, candles)` returning
  the current JSON shapes (ICT provider delegates to the existing engines —
  zero UI/API change); (b) if (a) proves awkward, keep the three routers pinned to
  an explicitly named `ICTAnalysisProvider` while `/signals` uses the swappable
  seam, and document that the analysis pages are ICT-specific.
- **Why:** C1/C2 — today these routers duplicate the strategy pipeline; any
  strategy change otherwise forces router edits.
- **Scope:** 3 routers + provider method; frontend untouched.
- **Dependency impact:** contained to the three routers.
- **Benefit:** analysis UI keeps working; strategy swap touches at most one place.
- **Risk:** medium-low; contract-diff + page tests guard shapes. **Validation:**
  E-03-style response comparison on the three endpoints.

### E4. Unify strategy configuration per strategy
- **Change:** each provider declares its config section (e.g.
  `strategy.yaml:strategies.<name>.*`); the provider receives **only its section**.
  Move the SL/TP fallback out of `StrategyEngine` into the ICT adapter's section
  (values unchanged); `risk.yaml:stops_and_targets` stays as risk-side defaults.
- **Why:** C8/C12 — a new strategy currently inherits ICT keys plus a hidden
  risk-config fallback.
- **Scope:** `strategy.yaml` (additive sections), `strategy/engine.py` init,
  provider factory wiring.
- **Dependency impact:** existing keys keep working (deprecated fallback path with
  a warning, removed only if a later phase demands it).
- **Benefit:** a new strategy ships one config block; platform config untouched.
- **Risk:** low. **Validation:** config-resolution unit tests (section isolation,
  fallback values identical).

---

## 10. Valuable changes

### V1. Tick backtest consumes the seam (keeps its fill model)
- **Change:** `TickBacktestEngine` accepts a `StrategyProvider` (default: adapter
  over the existing `ScalpStrategyEngine`, preserving BUY/SELL→LONG/SHORT mapping
  in one place instead of inline at `tick_backtest.py:210-214`). Regime/fusion/
  cooldown/funnel stay exactly as they are.
- **Why:** C6/C7 — second strategy stack with its own vocabulary and hand-mapped
  fields; currently unpluggable.
- **Scope:** `tick_backtest.py` constructor + signal intake (~30 lines); delete the
  inline remap.
- **Dependency impact:** tick-backtest tests only.
- **Benefit:** strategy experiments run on ticks without forking the harness.
- **Risk:** low-medium; tick tests + metrics regression guard it. **Validation:**
  identical metrics on the existing tick fixtures.

### V2. Slim the UI/API strategy surface to the contract + opaque extras
- **Change:** `api.ts` types: keep `direction/entry/stop/take/status` strict,
  `setup_type/confidence/reasons/pattern-lists` as opaque (`unknown`/JSON blob).
  `/strategy` page keeps rendering lists but drops ICT-specific field assumptions
  (`fvg_type`, `mitigation_status`) in favor of generic label/value rendering;
  `/orders` already renders `reasons` as JSON — keep that.
- **Why:** C10 — every strategy rename currently ripples into TypeScript types.
- **Scope:** `lib/api.ts`, `strategy/page.tsx` rendering only; no route changes.
- **Dependency impact:** none on backend. **Validation:** `npm run build` + page walkthrough.

### V3. Delete the dead plugin ABC (+6-stage gate stays research-only)
- **Change:** remove `StrategyPlugin` ABC from `strategy/plugin.py` (zero runtime
  importers); keep `UnvalidatedResearchStrategy`, `UnifiedSignal`,
  `SignalQualityGate` where they are for the two research tests that use them.
- **Why:** §6 — a 5-method ABC with no callers is precisely the speculative
  abstraction the constraints forbid; its existence misleads (README claims it).
- **Scope:** one class deletion + README line correction.
- **Dependency impact:** `test_phase38`, `test_phase41` keep working (they use the
  concrete classes, not the ABC — verify before deleting).
- **Benefit:** removes the false "already pluggable" story; forces the real seam.
- **Risk:** trivial. **Validation:** suite green + grep for `StrategyPlugin(`.

### V4. Align persistence schema with the contract (schema-compatible)
- **Change:** when signals are first actually persisted, add nullable generic
  columns rather than reusing ICT-shaped ones; until then, no migration. At most:
  document that `SignalModel.setup_type/confidence/reasons` mirror the decision
  contract's opaque fields.
- **Why:** C9 is latent (write-never); a premature migration is churn.
- **Scope:** docs only, unless persistence lands in the same release.

---

## 11. Changes explicitly deferred (do not do)

- **D1. Unify the three fill/exit models** (`ExecutionEngine` vs candle-backtest
  inline vs tick-backtest+`ScalpPositionManager` vs broker-side bot SL/TP). Real
  divergence, but each model encodes mode-specific realism (latency, spread kills,
  broker stops); unifying is a large, risky rewrite with no strategy-replacement
  payoff. Revisit only with a dedicated backtest-fidelity phase.
- **D2. Restructure bots around the seam.** The 5 bots are independent products with
  own loops; forcing them through `StrategyDecision` now would churn working,
  gated, tested code for no consumer benefit. Revisit per-bot if a bot is ever
  redesigned.
- **D3. Move/rename research packages** (`context`, `intelligence`, `regime`,
  `fusion`, `information`, `swing`) or fix the `regime↔scalper` cycle beyond
  documentation. Zero runtime impact on strategy replacement; label only.
- **D4. Split `risk.yaml`/`.env` or introduce per-strategy risk profiles.** Risk
  config has no strategy content; splitting files adds joints with no benefit.
- **D5. New frameworks, event buses, DI libraries, ORM changes, renames, tech-stack
  changes.** Explicitly out, per constraints.
- **D6. Strategy logic or profitability work.** The ICT engine's rules, thresholds,
  and the research verdicts are untouched; characterization tests must keep passing.

---

## 12. Implementation sequence

```
E1 contract + validation tests
 └─► E2 provider seam + ICT adapter + 3-site wiring (stub-swap test proves it)
      ├─► E3 analysis pages behind provider (contract-diff on 3 endpoints)
      └─► E4 per-strategy config sections
V1 tick-backtest seam ──► V2 UI slimming ──► V3 delete ABC ──► V4 persistence note
(each independently committable; suite + contract diff green after each)
```

Rollback per step is `git revert` of that step's commits; no migrations are
introduced by any step (V4 is docs-only unless persistence ships).

## 13. Testing/validation strategy

- **Contract tests (new):** decision validation matrix (valid, inverted SL/TP,
  zero/negative prices, unknown/empty direction, missing ID); provider stub swapped
  end-to-end through `POST /api/strategy/signals`-equivalent path, runner-equivalent
  call, and candle backtest — asserting identical downstream handling.
- **Preservation tests:** existing `test_signal_engine.py`,
  `test_pricing_characterization.py` (locks `_scalp_levels`), backtest/monte-carlo
  tests, and the E-03 contract diff must pass unchanged (ICT adapter = old behavior).
- **Tick parity:** `test_tick_backtest.py` metrics identical before/after V1.
- **No-new-flakiness:** full suite in forward, reverse, and shuffled module order
  (the harness now supports this — verified during Phase 2).
- **Static gates:** `ruff check app scripts`, `npm run build`, E-05-style grep that
  no runtime module outside `strategy/` + seam imports ICT sub-engines.

## 14. Definition of done

1. A second, behaviorally different strategy (e.g. an SMA-crossover provider in
   tests, or the existing momentum engine promoted behind the seam) can drive
   `/signals`, `runner.py`, and the candle backtester by changing only
   configuration + one registration — demonstrated by a test, not claimed.
2. `StrategyEngine` internals (sweeps, FVGs, ICT thresholds) can be edited without
   touching `api/`, `backtest/`, `runner.py`, `risk/`, or `execution/`.
3. All 323 existing tests pass unmodified except where an intended, documented
   contract change requires it; contract diff shows only the documented shape
   stability (success shapes unchanged).
4. No new abstraction without a consumer: every new interface has ≥2 call sites or
   an explicit test double exercising it.

## 15. Risks and tradeoffs

| Risk | Likelihood | Mitigation |
|---|---|---|
| Seam too narrow — a future strategy needs inputs the seam lacks (e.g. order-book, calendar) | Medium | `MarketInputs` carries candles + symbol + point_size today and is extensible by additive optional fields; input assembly moves behind provider methods in E2 so extensions don't touch routers |
| Seam too wide — providers re-implement risk/execution concerns | Low | Validation layer rejects anything but decisions; risk/execution untouched and still authoritative downstream |
| Analysis pages (E3) prove awkward to generalize | Low | Fallback documented in E3: pin them to a named ICT provider; dashboard keeps working either way |
| Tick pipeline (V1) resists the seam (BUY/SELL, features input) | Medium | Scoped as Valuable, not Essential; the ICT→candle path (the live path) is what must work day one |
| Scope creep into fill-model unification or bot rewrites | Medium | Hard boundary in §11 D1/D2; reviewer checkpoints after E2 and after E4 |

## Appendix: stopping-condition checklist (§16)

- [x] Important runtime paths traced (API, runner, candle/tick backtests, bots, research scripts)
- [x] Meaningful coupling identified (C1–C12) with file:line evidence
- [x] Actual boundary derived from risk/execution inputs (§4 contract)
- [x] Existing abstractions evaluated with keep/modify/replace verdicts (§5)
- [x] Necessary changes determined (E1–E4) vs valuable (V1–V4) vs deferred (D1–D6)
- [x] Unchanged items named explicitly (§7, §11)
- [x] Concrete plan with scope/validation per change (§9–§10)
- [x] Validation defined (§13–§14)

---

*End of Phase 1 deliverable. No code, config, test, or schema was modified.*
