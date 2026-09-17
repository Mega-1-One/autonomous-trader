# Profitability Investigation — Live / Demo Execution Path

**Scope:** Why the system loses money on a demo (or any) account. Focused on the
**live execution path** (scalper bots + runner + execution + risk + MT5 adapter + configs).
Backtest/research internals are referenced only where they reveal a live-path defect.

**Method:** Full read of every code path that can call `mt5.order_send`, every config
consumed at runtime, and the project's own published research artifacts
(`backend/data/phase*.md|json|csv`, `backend/scripts/real_tick_performance_report.json`).

---

## 0. TL;DR — the two independent reasons it cannot be profitable

1. **The strategy has no demonstrated edge.** The project's own research says so:
   - `backend/data/phase35_postmortem.md`: directional micro-scalping, ICT/SMC sweeps,
     1,000,000+ observations — **all EXHAUSTED**, "Gross exp <= 0", "0/360 FDR significant".
   - `backend/data/phase39_forward_test_report.md`: forward result **Profit Factor 0.70,
     Expectancy −0.18R, Win rate 48%**, MFE/MAE 0.85 → verdict **NEGATIVE FORWARD EVIDENCE**.
   - `backend/data/phase41_final_audit.md` splits "infrastructure: Grade A" from
     "strategy profitability: UNVALIDATED / no guaranteed profitability".
   With no edge, even perfect execution trends to a loss after costs. This is the root cause.

2. **The live bots are not even running the researched strategy, and are structurally
   money-losing.** The bots that actually place demo orders (`app/scalper/*`) do **not**
   use the ICT/SMC engine, the quality gate, the cost filter, the EV engine, the regime
   filter, or the fusion engine. They trade crude tick-momentum/coin-flip logic with
   **no cap on concurrent positions**, so they churn spread + commission continuously.

Everything below is the evidence, ranked by how much it moves P/L.

---

## CRITICAL — directly turns any edge into a loss

### C1. Gold scalper has no position limit and re-enters ~5×/second (unbounded churn)
- File: `backend/app/scalper/gold_multi_scalper.py`
- `max_open_positions` is accepted (`:26`) and stored (`:37`) but **never referenced again**.
- The order gate is only a 0.2 s debounce: `if is_test_mode or (now - self.last_order_time >= 0.2)` (`:423`), with `last_order_time` reset on every successful fill (`:460`) and a 50 ms loop (`:491`).
- `calculate_account_risk_metrics()` was deliberately reduced to a margin-only check and **does not block on position count, drawdown, daily loss, or risk** (`:121-185`).
- Result on a live demo: a new 0.01 lot position every ~0.2 s until margin is exhausted
  (~12 concurrent positions on a ~$27–50 account). Each position pays spread + commission
  on entry and exit; the loop never waits for a position to close before opening the next.
  This is the single most damaging behavior and by itself guarantees a bleed.
- **Impact:** turn-any-edge-negative. Fix before anything else (enforce `max_open_positions`,
  and require "flat/max-N" before a new entry).

### C2. Entry direction is a 50 ms coin flip, not a signal
- `gold_multi_scalper.py:370-380`: `direction = "BUY" if curr_mid >= self.last_price else "SELL"`.
  `last_price` is overwritten every loop (`:380`) regardless of a fill, so the "signal" is
  the sign of the mid change over the last ~50 ms.
- At tick frequency, bid/ask bounce creates negative autocorrelation: buying after an up-mid
  tick and selling after a down-mid tick systematically crosses the spread the wrong way
  (adverse selection). Expectancy before costs ≈ 0; after spread/commission it is negative.
- `backend/app/scalper/ultra_tick_scalper.py:63`: direction literally alternates
  `BUY/SELL/BUY/SELL` by trade count — a guaranteed-negative-EV coin flip.
- **Impact:** negative edge on every trade, independent of C1.

### C3. No cost / EV / net-edge gate anywhere in the live path
- `backend/app/intelligence/cost_analyzer.py` (CostFilter) and
  `backend/app/intelligence/ev_engine.py` (ExpectedValueEngine) exist and correctly model
  "$7/lot + spread + slippage" and "EV after transaction cost" — but they are **never
  called by any bot or by the live `StrategyEngine`**. They are only used inside the
  backtest path (`app/backtest/tick_backtest.py`).
- No live code checks that the target is ≥ 1.5× total transaction cost before firing.
- **Impact:** trades whose entire target is consumed by spread/commission are still sent.

### C4. All automatic risk halts were removed ("MANUAL STOP ONLY")
- `config/risk.yaml`: `maximum_daily_loss_percent: 0`, `maximum_total_drawdown_percent: 0`,
  `maximum_open_positions: 0`, `maximum_spread_pips: 0`, `maximum_trades_per_day: 0` → all disabled.
- `gold_multi_scalper.py` computes drawdown/daily P/L but explicitly never blocks on them.
- Consequence: a losing streak has no circuit breaker; the bot keeps adding size/exposure
  into the loss. On a small demo account this is the difference between a bad day and a blown account.
- **Impact:** unbounded tail risk; converts normal variance into ruin.

### C5. Safety flags give a false sense of protection for MT5 bots
- The MT5 bots import `settings`/`ExecutionMode` but **never check them**; they call
  `mt5.order_send` directly (`gold_multi_scalper.py:440`, `ultra_tick_scalper.py:86`,
  `grid_martingale_bot.py:92`, `demo_scalper_engine.py:73`, `autonomous_scalper_daemon.py:166`).
- README warns of this, but there is no in-code guard. `EXECUTION_MODE=PAPER` does not
  stop these scripts. A "demo test" can therefore place unlimited real demo orders.
- **Impact:** no guardrail; directly enables C1.

---

## HIGH — materially distorts the risk/return geometry

### H1. SL/TP geometry ignores spread → effective RR collapses (and can invert)
- `backend/app/strategy/engine.py:66-80` `_scalp_levels()` computes SL/TP in pips from the
  **candle close**, not from the live ask/bid. Entry is set to `latest_candle["close"]` (`:131,170`).
- A long fills at **ask = close + spread**, while the stop sits `stop_loss_pips` below close.
  Real risk = `SL + spread`, real reward = `TP − spread`. With gold at 3 SL / 5 TP pips and a
  2–4 pip spread, true RR drops from the configured 1.67 to well under 1 — sometimes the stop
  is already inside the spread → instant/`INVALID_STOPS` behavior or immediate stop-out.
- The RR gate (`:133,172`) passes because it measures the theoretical pip distances, not the
  post-spread distances.
- **Impact:** the headline 1.67 RR is fictional in live conditions; this is a primary reason
  "wins" are tiny and "losses" are full-size.

### H2. Gold scalper ignores its own configured stops; real exits are $0.60 / $0.50
- `gold_multi_scalper.py:387-390`: distances are floored by hard-coded dollars:
  `min_sl_dist = max(1.00, stop_loss_pips*pip_scale, spread*2.5)` and
  `min_tp_dist = max(1.50, take_profit_pips*pip_scale, spread*3.0)`.
  With the runner's 5/15 pip config (`scripts/run_gold_multi_scalper.py:27-30`) and gold
  `pip_scale=0.10`, this produces SL=$1.00 / TP=$1.50 — the config is silently overridden.
- Meanwhile closes are driven by USD thresholds: `min_profit_target_usd=0.60`,
  `max_loss_usd=0.50` (`gold_multi_scalper.py:308-311`). So the displayed "+15 pip TP" is
  essentially never reached; the strategy is really a **+$0.60 / −$0.50** trade = RR 1.2,
  requiring >45.5% win rate before costs.
- **Impact:** risk.yaml RR settings do not apply to the bot that actually trades; realized
  geometry is worse than documented.

### H3. Commission modelling is wrong for the likely account type, and sizing over-risks small accounts
- `_net_profit()` subtracts `volume * commission_per_lot` with `commission_per_lot=7.0`
  (`gold_multi_scalper.py:88,32`) — a **one-way** deduction of a value that in the research
  is described as a **round-turn** $7/lot. Exness "Standard" accounts (typical for a $27–50
  demo) charge **$0 commission** instead, so the close logic over-subtracts and can hold
  losers / dump winners at the wrong time; on a raw-spread account it under-subtracts.
- `RiskEngine.calculate_position_size()` (`backend/app/risk/engine.py:63-78`) clamps to
  `min_volume` (0.01) regardless of whether 0.01 already risks far more than the intended
  `risk_per_trade_percent=0.1%`. On a $27 account, 0.1% = **$0.027**, but the smallest gold
  position with a $1 stop risks **$1.00** (~3.7% of account) — ~37× the intended risk.
- **Impact:** incorrect close decisions + structural over-leveraging on small accounts.

### H4. Live fill price is stale and slippage/stop-distance guards are absent
- `StrategyEngine` sends `entry_price = candle whole close`; the actual fill is at current
  market with `deviation=10/20`. No re-quote, no max-slippage cap beyond the deviation, no
  rejection if price moved. Combined with H1, the geometry is invalidated at fill time.
- `runner.py:63` updates open positions with **bid only** (`update_positions({symbol: bid})`),
  so shorts' floating P/L and R-multiples are wrong (spread-sized error on every tick).

### H5. Sweep detection has no recency window and is not time-ordered
- `backend/app/strategy/sweeps.py` scans **every** candle against **every** liquidity level
  and returns them in level-major order. `StrategyEngine` then takes `reversed(sweeps)`
  (`engine.py:125,164`) as "the recent sweep" — which is actually the last level's latest
  sweep, not the temporally latest one, and it may be dozens of candles old.
- There is no "within the last N candles" filter, so a stale sweep paired with any
  unmitigated FVG/OB still authorizes an entry.
- **Impact:** entries are frequently triggered by stale/irrelevant structure.

### H6. Sessions / regime / news filters are off
- `config/strategy.yaml`: `sessions.enabled: false` → `SessionFilter` returns "Always On"
  (`app/strategy/sessions.py:23`). `MarketRegimeEngine` and the fusion engine are not used
  live at all. The bots trade 24/5, including the Asian session where the project's own
  Phase 39 data shows the worst performance (PF 0.58) and spreads are widest.
- **Impact:** trading conditions with the worst cost/edge ratio.

### H7. Fixed pip stops are too tight for gold/indices
- 3 pip SL / 5 pip TP on gold = **$0.30 / $0.50** price distance. Gold's spread alone can be
  $0.20–$0.40, so the stop sits within a normal tick cluster; the position is stopped by
  noise before the target can be reached (Phase 39: MFE/MAE 0.85 = "adverse heavy").
- **Impact:** low realized win rate by construction.

### H8. Two disconnected systems; the one that trades is the crude one
- `app/backtest/tick_backtest.py` wires strategy → regime → fusion → risk → cost, and its
  `scripts/real_tick_performance_report.json` shows **0 trades executed** across ~15k real
  ticks per symbol (all "No trades executed"). The sophisticated gate is so restrictive
  (or the pipeline so incomplete) that it never fires.
- The demo bots bypass all of it. So the research conclusions about the ICT/SMC strategy
  do not even describe what the bots do — the bots are simpler and have no gate.
- **Impact:** you cannot reason about live P/L from the research artifacts; live behavior
  is a separate, worse system.

---

## MEDIUM — bugs that corrupt signals, accounting, or symbol handling

### M1. Lookahead bias in structure detection
- `app/strategy/structure.py:76-116`: a swing at index `i` is confirmed using candles
  `i+1..i+lookback`, yet `analyze_structure()` consumes it for BOS/MSS at index `i` (`:157-203`).
  `confirm_on_close` is also ignored: `StrategyEngine` never passes the config's
  `market_structure.confirm_on_close: false` (`engine.py:53`; `structure.py:62` defaults True).
- **Impact:** backtest results are optimistic; live signals differ from what was validated.

### M2. Order-block "break" check is effectively always true
- `app/strategy/order_block.py:42-44`: `... or (len(structure_events) > 0)` makes the break
  requirement true whenever any structure event exists → OB quality gate is bypassed.

### M3. Position tracking keyed by order ticket vs position ticket
- `gold_multi_scalper.py:472` stores `tracked_positions[res_open.order]`, but reconciliation
  compares against `p.ticket` (`:281,284`). On brokers where the position ticket ≠ order
  ticket this marks every position "closed externally" each loop and clears tracking.
- **Impact:** noisy reconciliation and unreliable per-position metadata.

### M4. `InstrumentSpecification` strips all "M" characters
- `app/scalper/instrument.py:30`: `symbol.upper().replace("M", "")` corrupts any symbol
  containing M that is not a suffix alias (e.g. `USDMXN` → `USDXN`), yielding wrong
  pip/contract/digit specs.

### M5. Pip-scale detection is inconsistent between bots
- `autonomous_scalper_daemon.py:70` and `grid_martingale_bot.py:53` test `"XAU" or "USTEC"`,
  but the index symbol is `NAS100`/`US100` → falls back to `0.0001`, so index SL/TP and grid
  step are off by orders of magnitude. `gold_multi_scalper.py:235` hard-codes gold to 0.10.
- **Impact:** stops/targets mis-scaled on non-forex symbols.

### M6. Spread scaling depends on caller-supplied `digits`
- `app/scalper/tick_engine.py:70-77` divides by `point_size*100` (digits 3) or `point*10`
  (digits 5), else `raw/point`. For indices (digits 2) this yields a huge "pip" number, so
  the strategy's `max_allowed_spread` gate is mis-scaled and blocks or passes wrongly.

### M7. Paper/dashboard path is not real
- `scripts/run_paper_simulation.py` + `realtime_paper_simulation.py` only print quotes; the
  saved `backend/data/paper_simulation_summary.json` shows **12 ticks, 0 trades**. The API
  execution engine (`app/api/execution.py:9-10`) uses the **Mock** adapter, so dashboard
  positions/PnL are simulated and unrelated to the demo account.

### M8. `RealMT5Adapter.send_order` ignores magic/comment and hard-codes magic
- `app/data/mt5_real.py:192`: `"magic": 100001` is hard-coded (the passed `magic` and
  `comment` are dropped). Breaks per-strategy attribution and any magic-based position
  management/filtering.

### M9. No persistence / restart dedup in the live runner
- `app/runner.py` + `app/execution/engine.py` keep positions in memory with a fresh UUID
  `client_signal_id` each scan (`engine.py:62`), so idempotency does not survive restarts and
  can duplicate exposure after a crash.

### M10. Max-hold time exit randomizes outcomes
- `config/risk.yaml:33` `max_holding_time_seconds: 30` (gold bot 120 s). A fixed clock exit
  closes winners before target and losers before stop, adding variance with no edge.
  Combined with C2's coin-flip entries, it seals a negative expectancy.

### M11. Grid/martingale bot is negative-EV by design
- `app/scalper/grid_martingale_bot.py`: basket TP = basket SL = $0.50, martingale 1.5×
  averaging, `max_grid_orders=3`, then a forced close at cycle end (`:170`). Without an edge
  this is a classic martingale that caps wins and takes full losses; the `$0.50`/`$0.50`
  symmetry is worsened by spread + the `volume*7` commission estimate.

---

## LOW — hygiene, clarity, and dead/duplicated code

- **L1.** `StrategyEngine` hard-codes `confidence=0.85` (`engine.py:157,196`) — meaningless.
- **L2.** Multiple demo bots with different magics (`888777`, `999111`, `999333`, `888999`,
  `777111`) can run simultaneously and create conflicting exposure with no coordinator.
- **L3.** `SignalQualityGate`/`UnvalidatedResearchStrategy` (`app/strategy/plugin.py`) is not
  wired into any live loop.
- **L4.** `app/scalper/execution.py:54-56` slippage assumes `0.01` per pip for all symbols.
- **L5.** README/`.env.example` still say `EXECUTION_MODE` choices are `BACKTEST, PAPER, LIVE`
  while code adds `DEMO`; `.env` is absent so everything defaults to PAPER, yet the bots ignore it.

---

## Prioritized fix order (for the next session)

1. **C1** — enforce a hard concurrent-position cap and "flat-before-entry" in every bot;
   remove the 0.2 s re-entry debounce as the only throttle.
2. **C4/C5** — restore a real risk kill-switch (daily loss / max DD / max spread) and make
   MT5 bots respect a single execution-mode gate before any `order_send`.
3. **H1/H2/H7** — compute SL/TP from live ask/bid **including spread**, derive stops from
   ATR/volatility (not fixed pips), and make the bot use the config values it is given.
4. **C3** — wire `CostFilter` + `ExpectedValueEngine` into the live decision path; reject
   any trade whose target < ~1.5× total cost.
5. **C2/H8** — replace the tick-momentum/coin-flip direction with one real, pre-validated
   signal source; do not run the crude bots as-is.
6. **H5/H6/M1** — add sweep recency + chronological sorting, enable sessions, fix lookahead,
   and use the regime/fusion gates live if they are expected to help.
7. **Root cause (0)** — treat any profitability work as a **research problem first**: the
   Phase 35/39 conclusion is that price-derived micro-scalping has no surviving edge. Expect
   the infrastructure to stop bleeding after 1–6, but do not expect profit without a new,
   genuinely out-of-sample-validated signal (the project's own recommendation: non-price
   exogenous data, e.g. CME futures volume / macro calendar).

---

## Key evidence index

| Claim | Evidence |
|---|---|
| No edge in research | `backend/data/phase35_postmortem.md`, `phase39_forward_test_report.md`, `phase41_final_audit.md` |
| Gold bot position spam | `app/scalper/gold_multi_scalper.py:37,423,460,491` |
| Tick-momentum entries | `gold_multi_scalper.py:370-380`; `ultra_tick_scalper.py:63` |
| Risk halts disabled | `config/risk.yaml`; `gold_multi_scalper.py:121-185` |
| Cost/EV unused live | `app/intelligence/cost_analyzer.py`, `ev_engine.py` (imported only by `app/backtest/tick_backtest.py`) |
| SL/TP ignores spread | `app/strategy/engine.py:66-80,131-137,170-176` |
| Bot overrides config SL/TP | `gold_multi_scalper.py:387-390`; `scripts/run_gold_multi_scalper.py:24-32` |
| Sizing over-risks small account | `app/risk/engine.py:63-78` |
| Safety flags bypassed | `app/data/mt5_real.py:175-209`; all `app/scalper/*_scalper*.py` |
| Strategy never fires in tick test | `backend/scripts/real_tick_performance_report.json` (0 trades all symbols) |
