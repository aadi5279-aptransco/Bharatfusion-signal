# Phase 1 — evidence-based audit

Baseline `147e27b35fe5848f4ac8c460a5fe3d82d418f691`; date 23 November 2026 IST. **No behaviour changes made.**

## Decision

Discovery and source audit are complete for the inspected application paths. Live correctness and profitability are **not certified**. Do not interpret the existing PASS smoke checks as Phase 0 market-data acceptance or approval to train/promote models.

No Critical exploit or confirmed future-feature leakage is established by this review. High findings below are sufficient to block dependable performance measurement and entry-ready claims. The most direct current application defect is F01: a qualifying Intraday candidate is rejected by the journal's nullable-confidence mismatch.

Severity: Critical = direct catastrophic integrity/security failure with established reachability; High = wrong/missing plans or invalid performance/eligibility; Medium = bounded correctness, reliability or missing-control risk; Low = presentation/diagnostic issue. These labels describe impact, not probability of trading profit.

Method: source inspection at a pinned commit, existing CI evidence and user-pasted reports. The new reproduction recipes were **not executed**: this session has no usable Python/runtime or live Dhan credentials. See [VALIDATION.md](VALIDATION.md). No exhaustive security, numerical or market-session certification is claimed.

## Finding index

| ID | Severity | Finding |
|---|---|---|
| F01 | High | [Intraday qualifying candidates fail at journal insertion](#f01) |
| F02 | High | [Outcome journal assumes an entry without confirming a fill](#f02) |
| F03 | High | [Backtest fill timing is optimistic despite prefix-only strategy inputs](#f03) |
| F04 | High | [Costs are incomplete and the backtest fee label is misleading](#f04) |
| F05 | High | [Derivative candles bypass the cash session/grid filter](#f05) |
| F06 | High | [Corporate-action adjustment and historical universe are not certified](#f06) |
| F07 | High | [No complete pre-entry circuit/ban/surveillance gate](#f07) |
| F08 | Medium | [Tick sizes and lot metadata are not consistently carried into plans](#f08) |
| F09 | High | [Trading calendar has no special-session model and the close boundary is inclusive](#f09) |
| F10 | High | [Cash liquidity freshness uses retrieval time rather than trade time](#f10) |
| F11 | Medium | [Indicator definitions vary across tabs; flat RSI differs](#f11) |
| F12 | High | [Scheduler loses failed slots and can miss dashboard/outcome cycles](#f12) |
| F13 | Medium | [Failed discovery consumes the hourly slot and retains same-day lists without age cap](#f13) |
| F14 | Medium | [Local origin protection omits some refresh endpoints](#f14) |
| F15 | Medium | [No portfolio-wide constraint or common overlap identity](#f15) |
| F16 | Medium | [Historical fundamentals/ownership lack publication-time lineage](#f16) |
| F17 | Medium | [Missing previous OI is treated as zero](#f17) |
| F18 | High | [Track Record coverage, timeout and immutability are incomplete](#f18) |
| F19 | Medium | [Validation metadata is global/download-scoped, not fully returned-frame-scoped](#f19) |
| F20 | Medium | [Worker coordination and retention are process-local and unbounded in places](#f20) |
| F21 | Low | [UI freshness and error observability are uneven](#f21) |
| F22 | Medium | [Common cleaning is not a complete finite/timezone contract](#f22) |
| F23 | Medium | [F&O and legacy option scenarios lack source quote freshness certification](#f23) |
| F24 | Medium | [BANKNIFTY futures mapping remains a live acceptance blocker](#f24) |

<a id="f01"></a>

## F01 — Intraday qualifying candidates fail at journal insertion

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/strategies/momentum_query.py:131](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/strategies/momentum_query.py#L131) sets confidence=None. [insights/ai_rank.py:84](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/ai_rank.py#L84) preserves that field; cycle_wave.annotate does not replace it. [insights/db.py:69](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/db.py#L69) calls float(confidence). [insights/service.py:529](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L529) records before appending to buy/sell; its exception handler increments unavailable_count.

**Reproduction:** Create a valid Journal signal with confidence=None in a temporary database (recipe V1). It raises TypeError. With a mock broker producing a qualifying momentum setup, run scan_intraday: the row is lost before the list append and counted unavailable.

**Impact:** A valid setup can disappear as an apparent source failure. This is an integration defect, not a lack of strategy agreement.

**Proposed repair / acceptance:** Support a nullable uncalibrated probability separately from a finite heuristic score; keep the label honest. Add an end-to-end qualified-candidate regression.

<a id="f02"></a>

## F02 — Outcome journal assumes an entry without confirming a fill

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/service.py:1109](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L1109) tests stop/target directly after signal_at. [insights/ai_rank.py:84](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/ai_rank.py#L84) explicitly produces conditional triggers, not fills.

**Reproduction:** Record BUY entry=100, SL=95, T1=110. Supply subsequent completed candles O=111,H=112,L=111,C=111: resolver marks T1 at 110 despite no obtainable entry at 100. For an untriggered plan, candles below entry touching SL are likewise counted as a stopped trade.

**Impact:** Target-touch counts cannot establish realised trade performance; gap fills and conditional entry ordering are absent. Stop-first same-candle resolution is good but does not fix entry semantics.

**Proposed repair / acceptance:** Introduce signal-created, order-eligible, filled and closed paper states; next-bar realistic fills, gap-aware exits and explicit ambiguity policy.

<a id="f03"></a>

## F03 — Backtest fill timing is optimistic despite prefix-only strategy inputs

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/backtest.py:19](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/backtest.py#L19) correctly passes only the observed prefix, but lines 23–38 use candidate entry unchanged and label entry_bar at the signal bar. No next-open/trigger fill exists.

**Reproduction:** V2: use a candidate entry=100 with every subsequent bar trading at 111–112 and T1=110. The function can count a positive T1 outcome even though next-bar entry would be above the target. Repeat with a gap below SL: exit remains the stop price.

**Impact:** Execution-timing bias is the strongest confirmed backtest bias here. It is distinct from future-feature leakage; neither causal features nor stop-first ties prove tradability.

**Proposed repair / acceptance:** Use one fill simulator shared with outcome resolution; enter no earlier than the next bar with realistic side-specific fills, spread, gaps and liquidity.

<a id="f04"></a>

## F04 — Costs are incomplete and the backtest fee label is misleading

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/backtest.py:36](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/backtest.py#L36) charges (entry+exit)*costs_bps/10000, while line 52 calls costs_bps a round-trip approximation. [insights/service.py:1118](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L1118) omits costs so [insights/db.py:90](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/db.py#L90) stores zero.

**Reproduction:** At entry=exit=100 and costs_bps=20, fee=0.40: 40 bps of entry notional, not 20. Resolve a journal outcome and inspect costs=0. No product/side/date/quantity input can distinguish delivery, intraday, futures or option taxes.

**Impact:** Results are not net of full Indian charges or liquidity-aware slippage. Bias is not necessarily always upward: the bps approximation can overcharge some trades and undercharge others.

**Proposed repair / acceptance:** Version charges by effective date and product; brokerage/STT/exchange/GST/SEBI/stamp, applicable other charges, rounding, quantity/lot and slippage/impact. Reconcile example contract notes before promotion.

<a id="f05"></a>

## F05 — Derivative candles bypass the cash session/grid filter

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/brokers/dhan.py:28](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/brokers/dhan.py#L28) deliberately returns futures/options unchanged; [insights/data_layer/history.py:32](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/data_layer/history.py#L32) checks elapsed duration but not exchange session/grid. User report includes 15:39 derivatives and PE first aggregate timestamp 11:56.

**Reproduction:** Supply NSE_FNO 5m bars at 11:56 and 15:35 with now=16:00. General validate and broker cash filter do not reject those timestamps. Compare with the corresponding cash/index path. Use only an isolated fixture.

**Impact:** Misaligned or off-session bars may enter derivative features or outcomes. Their actual provider meaning needs verification; the report does not prove genuine exchange trades at those times.

**Proposed repair / acceptance:** Apply instrument/venue/date-specific sessions and interval grids, quarantine ambiguous bars, and explicitly decide how to handle final session stubs. Do not shift timestamps by a guessed constant.

<a id="f06"></a>

## F06 — Corporate-action adjustment and historical universe are not certified

**Severity:** High. **Evidence status:** Confirmed design limitation; actual corporate-action and delisted-data reconciliation not run.

**Evidence:** [insights/data_layer/history.py:1](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/data_layer/history.py#L1) explicitly retains AS_REPORTED prices; [insights/nifty500.py:88](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/nifty500.py#L88) resolves current membership; [data.py:79](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/data.py#L79) filters contracts against wall-clock date.

**Reproduction:** Replay a known split/ex-date and compare raw returns/ATR with a separately verified adjustment ledger. Attempt a historical scan using today's constituents: no point-in-time membership input is available in this path.

**Impact:** Split/bonus discontinuities can resemble breakouts; current-member research has survivorship bias. Historical model training and comparative performance are not defensible yet.

**Proposed repair / acceptance:** Preserve raw plus versioned adjusted data, point-in-time corporate-action availability and universe snapshots. Document unavailable delisted coverage rather than fabricating it.

<a id="f07"></a>

## F07 — No complete pre-entry circuit/ban/surveillance gate

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/liquidity_shortlist.py:64](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/liquidity_shortlist.py#L64) checks price/volume/turnover but not bands/lock/ban. [data.py:87](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/data.py#L87) filters only ASM_GSM_FLAG='Y' when the column exists. [insights/data_layer/master.py:33](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/data_layer/master.py#L33) explicitly says full eligibility needs separate evidence.

**Reproduction:** Feed a high-volume, high-turnover quote at an upper circuit with no executable sell depth into shortlist refresh; it meets the documented shortlist checks. Remove ASM_GSM_FLAG from a valid master: parsing does not fail closed. Inspect F&O scan for a dated ban-list join: none is present.

**Impact:** Passing current liquidity/strategy checks does not establish eligibility for a new position. Historic turnover can coexist with a currently locked book.

**Proposed repair / acceptance:** Add a shared dated eligibility service for bands/operating ranges, two-sided executability, suspensions, ASM/GSM/series and F&O bans. Respect differences between cash price bands and derivative operating ranges.

<a id="f08"></a>

## F08 — Tick sizes and lot metadata are not consistently carried into plans

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/indicators.py:70](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/indicators.py#L70) and [insights/positional.py:56](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/positional.py#L56) round to two decimals. [data.py:97](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/data.py#L97) omits futures lot/tick; options include lot. [insights/data_layer/contracts.py:66](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/data_layer/contracts.py#L66) returns tick but no lot. Order flow does use a verified tick.

**Reproduction:** With a verified tick of 0.05, a computed entry 100.03 remains 100.03 in common risk outputs. Inspect an index-futures mapping: no lot field is returned. Available option strikes are used rather than an invented fixed step, which is a positive.

**Impact:** Levels may not be executable on the instrument grid; quantity/margin-aware sizing cannot rely on a uniform schema.

**Proposed repair / acceptance:** Use effective-date instrument identity including lot/tick/expiry; side-aware tick rounding and revalidate stop/target order and R after rounding.

<a id="f09"></a>

## F09 — Trading calendar has no special-session model and the close boundary is inclusive

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/config.py:28](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/config.py#L28) uses weekday/holiday membership and minute tuples through (15,30). [insights/service.py:39](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L39) validates the calendar against the host's current year.

**Reproduction:** V3: a normal trading date at 15:30:30 is considered open. A declared Saturday special session is still blocked. Replay a prior-year date while host year differs from the calendar file: calendar acceptance is tied to host time.

**Impact:** Scans may run after the normal close or miss Muhurat/special sessions. Pre-open order-entry, matching and normal trading are not separate session states.

**Proposed repair / acceptance:** Use dated exchange/segment session intervals with explicit boundaries, interruptions and exceptional sessions; inject the evaluation date into calendar loading.

<a id="f10"></a>

## F10 — Cash liquidity freshness uses retrieval time rather than trade time

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/brokers/dhan.py:281](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/brokers/dhan.py#L281) copies last_trade_time but stamps fetched_at from the scan's now for non-options. [insights/liquidity_shortlist.py:65](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/liquidity_shortlist.py#L65) validates only fetched_at.

**Reproduction:** Return yesterday's last_trade_time with positive price/volume and a current fetched_at. Shortlist selection can pass. Contrast index_premium.quote_values, which checks actual option trade age and depth.

**Impact:** Stale or suspended names can appear liquid; quote freshness cannot be inferred from a successful HTTP fetch.

**Proposed repair / acceptance:** Validate exchange trade timestamp and session-volume date, reject future/stale quotes, and separately record request/receipt/source timestamps.

<a id="f11"></a>

## F11 — Indicator definitions vary across tabs; flat RSI differs

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/indicators.py:22](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/indicators.py#L22) uses first-observation EMA/EWM smoothing; [insights/strategies/swing.py:14](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/strategies/swing.py#L14) maps all-flat RSI to 0. [insights/positional.py:25](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/positional.py#L25) uses SMA-seeded Wilder and maps flat RSI to 50.

**Reproduction:** Pass 40 equal closes to swing._rsi: after warm-up it returns 0; momentum_query._rsi returns 50. Compare first valid ATR/RSI on a nonconstant fixture with positional.wilder; the seeding conventions differ.

**Impact:** The same indicator name can imply different thresholds across tabs. First-observation EMA is a convention, not automatically a bug; unversioned inconsistency and flat-series handling are the defect.

**Proposed repair / acceptance:** Specify one versioned numerical contract, seed/warm-up/NaN/flat rules and golden fixtures. Preserve intended strategy differences explicitly in config.

<a id="f12"></a>

## F12 — Scheduler loses failed slots and can miss dashboard/outcome cycles

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/service.py:1443](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L1443) adds monitor_key before calling the job. Lines 1451–1465 only refresh dashboard/outcomes when minute%5==0. One global lock spans the scan.

**Reproduction:** Stub scan_intraday to raise once at 10:01 then succeed; invoke run_due again at 10:02: its bucket is already done. Invoke at 10:04 then 10:06: periodic dashboard/outcome path misses 10:05. Mock other due jobs to keep the fixture isolated.

**Impact:** Transient source errors suppress retries; slow broad scans can starve freshness-sensitive work.

**Proposed repair / acceptance:** Separate pending/running/succeeded/failed state, bounded retries, bucket catch-up and deadlines. Refresh evaluation time after long work; reserve resources for index monitoring.

<a id="f13"></a>

## F13 — Failed discovery consumes the hourly slot and retains same-day lists without age cap

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/liquidity_shortlist.py:31](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/liquidity_shortlist.py#L31) records attempt_slot before work; same slot returns immediately. selected() checks only date.

**Reproduction:** First refresh at 10:00 returns no valid quotes; restore provider at 10:05 and refresh again: no new attempt until a later slot. A 09:45 list can survive repeated failures through the afternoon and remain selectable.

**Impact:** Strategies may scan an increasingly outdated liquidity universe even while its data-quality banner reports failure.

**Proposed repair / acceptance:** Retry within the slot with backoff; expose last successful discovery and enforce configurable shortlist age/revalidation.

<a id="f14"></a>

## F14 — Local origin protection omits some refresh endpoints

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/api.py:24](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/api.py#L24) guards a prefix subset; dashboard, disclosed deals and participant refresh POST routes are outside it. [insights/app_controls.py:12](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/app_controls.py#L12) has a stronger host/origin/token guard for exit.

**Reproduction:** Using Flask test_client with stubbed refresh methods, POST /api/v1/market-insights/dashboard/refresh with Origin=https://example.invalid and REMOTE_ADDR=127.0.0.1. Compare against index-options/refresh: the latter is rejected by the guard, the former reaches its handler.

**Impact:** Cross-site requests may trigger local work/quota use. Loopback binding limits exposure and there is no broker-order path; no remote credential compromise is asserted.

**Proposed repair / acceptance:** Apply a consistent local host/origin policy to all mutations, with explicit allowed cases and CSRF protection. Keep exit token protection.

<a id="f15"></a>

## F15 — No portfolio-wide constraint or common overlap identity

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/fo_selection.py:26](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/fo_selection.py#L26) deduplicates within F&O, while [insights/db.py:72](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/db.py#L72) keys by strategy/version/symbol/direction/time. Shared portfolio exposure, sector/correlation and lot/margin checks are not in these paths.

**Reproduction:** Generate same-stock BUY candidates in Intraday and a second strategy at the same time: journal keys differ. Create two contracts with identical displayed symbol and strategy/time but different IDs: current key can collide. Verify on a temporary Journal.

**Impact:** Multiple correlated ideas can be presented/count separately; current journal identity can also suppress distinct contracts.

**Proposed repair / acceptance:** Separate immutable instrument+setup identity from presentation; cluster overlapping trades and add explicit capital, margin, sector and risk budgets before sizing.

<a id="f16"></a>

## F16 — Historical fundamentals/ownership lack publication-time lineage

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/strategies/multibagger.py:52](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/strategies/multibagger.py#L52) checks asof/period/source envelopes; [insights/qglp.py:53](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/qglp.py#L53) checks export/period dates; [insights/fii_holdings.py:68](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/fii_holdings.py#L68) checks consecutive quarter ends but not filing availability timestamps.

**Reproduction:** Import an otherwise valid historical-quarter row with an asof predating its actual publication; the input schema cannot independently verify the publication event. Compare a quarter-end backtest against a later filed revision.

**Impact:** Using these current imports in retrospective ML can leak future filings/restatements. Current screens appropriately label user-supplied values, so this is not a claim that present live screens already backtest leaked fundamentals.

**Proposed repair / acceptance:** Store filing publication/retrieval/revision times and units; as-of joins must use known_at, not quarter_end. Reconcile sector-specific ratios and restatements.

<a id="f17"></a>

## F17 — Missing previous OI is treated as zero

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/strategies/options.py:9](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/strategies/options.py#L9) defaults missing numbers to zero; chain_metrics subtracts previous_oi using that default.

**Reproduction:** V4: a leg with oi=100 and no previous_oi yields ce_change=100. Unknown previous OI should produce unknown change, not a reported +100 buildup.

**Impact:** Diagnostics can exaggerate OI change. PCR/max-pain are static aggregate calculations, not directional proof; their separate current-OI formula is not inherently wrong.

**Proposed repair / acceptance:** Carry availability per field and preserve null changes; distinguish interval OI buildup from previous-session changes. Reject negative OI and incomplete-chain comparability as appropriate.

<a id="f18"></a>

## F18 — Track Record coverage, timeout and immutability are incomplete

**Severity:** High. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/db.py:78](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/db.py#L78) chooses oldest 20 OPEN records; [insights/service.py:1112](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L1112) uses 75 bars for all recorded strategies. Journal stores updates, not append-only provenance; [insights/db.py:111](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/db.py#L111) replaces older backtests. F&O scan returns snapshots without a journal.record call.

**Reproduction:** Keep 20 oldest records with unavailable history and a valid 21st: repeated reconciliation selects the same first 20. Inspect a BTST journal entry: it receives the same 75-bar horizon. Compare all UI signals/notifications with journal rows: the APIs do not guarantee full coverage.

**Impact:** Unresolved records can starve newer ones; research horizons differ; the journal cannot establish an immutable, complete record of every issued plan. One-way outcome update correctly prevents normal repeated closure but is not tamper-evident.

**Proposed repair / acceptance:** Append-only issued/fill/outcome events with code/data/config hashes; per-strategy horizons, retry queues and full-tab coverage; preserve every validation/model version.

<a id="f19"></a>

## F19 — Validation metadata is global/download-scoped, not fully returned-frame-scoped

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/data_layer/history.py:105](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/data_layer/history.py#L105) stores only last three chunk reports in shared last_quality. Reports describe downloaded/merged cache work, not necessarily the final sliced/adapter-filtered frame. [insights/brokers/dhan.py:160](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/brokers/dhan.py#L160) filters again.

**Reproduction:** Download a month, return a five-day slice, then fetch another instrument. Compare returned row count and last timestamp with shared status: counts/scope differ and the latest request replaces prior metadata. User's old 60m report already showed differing last_bar values.

**Impact:** VALIDATED can be misread as complete exchange-session coverage. The newer phase0 returned_quality report is an improvement, not proof every API consumer has per-frame quality.

**Proposed repair / acceptance:** Attach immutable per-result quality with instrument/request/asof, grid and expected-session coverage; retain download diagnostics separately.

<a id="f20"></a>

## F20 — Worker coordination and retention are process-local and unbounded in places

**Severity:** Medium. **Evidence status:** Static risk confirmed; duplicate-process impact, memory pressure and throughput not load-tested.

**Evidence:** [insights/service.py:1472](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L1472) guards start with an instance field and uses threads; run_due accumulates _done keys. [insights/data_layer/history.py:54](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/data_layer/history.py#L54) stores chunks/quarantine without a visible retention job in that module.

**Reproduction:** Instantiate two services against the same temporary root and stub their broker: each can start a scheduler. Advance run_due through many days and inspect _done growth; inspect database retention after repeated unique requests.

**Impact:** Single launcher/port behaviour reduces ordinary duplicate starts but does not provide a cross-process scheduler lease. Long-running storage/memory growth and load limits remain unmeasured.

**Proposed repair / acceptance:** Enforce installation-level worker ownership, bounded job-state retention and cache/quarantine policies; measure 500-symbol soak latency and resource use.

<a id="f21"></a>

## F21 — UI freshness and error observability are uneven

**Severity:** Low. **Evidence status:** Error masking and timestamp inconsistency confirmed; response-order race is an unexecuted reproduction hypothesis.

**Evidence:** [web/src/main.js:34](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/web/src/main.js#L34) renders raw signal_at; main requests poll via setInterval without a common response-version contract. [insights/service.py:539](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L539) collapses several errors into unavailable_count; start loop masks unexpected exceptions.

**Reproduction:** Throttle the API beyond 20 seconds and return same-view responses out of order; inspect whether older payload replaces newer. Trigger F01 and observe generic unavailable_count rather than the schema error. Inspect signal cards for raw ISO time strings.

**Impact:** Users cannot consistently tell no setup from invalid data or internal failure. Currency formatting already uses en-IN; tab selection already clears old data, so those are not defects.

**Proposed repair / acceptance:** Central IST display/freshness components, per-source reason codes, request sequence/cancellation and redacted structured logs/correlation IDs.

<a id="f22"></a>

## F22 — Common cleaning is not a complete finite/timezone contract

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/indicators.py:7](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/indicators.py#L7) validates non-null/positive OHLC but not finite values or timezone-aware DatetimeIndex. VWAP groups by the input index date at line 30.

**Reproduction:** Pass an otherwise valid frame with volume=+infinity or all four OHLC values=+infinity on one row: comparisons alone do not reject it. Supply a naive DatetimeIndex: cleaning accepts it. Downstream stronger Dhan/Positional/SMC validators do reject many such inputs.

**Impact:** Direct reusable functions can yield invalid features or incorrectly reset sessions on a non-IST index. This is a boundary inconsistency, not evidence that every live Dhan response bypasses validation.

**Proposed repair / acceptance:** Centralize finite, timezone, session and schema validation. Explicitly convert to IST before grouping and require feature-specific finite warm-up readiness.

<a id="f23"></a>

## F23 — F&O and legacy option scenarios lack source quote freshness certification

**Severity:** Medium. **Evidence status:** Confirmed by static inspection; reproduction not executed here.

**Evidence:** [insights/strategies/options.py:58](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/strategies/options.py#L58) checks bid/ask/volume but not quote time, and adds an explicit warning. [insights/service.py:1073](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/service.py#L1073) marks F&O plans hypothetical; index_premium has stronger independent freshness gates.

**Reproduction:** Provide old chain values with positive OI/volume and a narrow spread; option_plan can return a plan. Compare with index_premium.quote_values using a stale last_trade_time, which rejects it.

**Impact:** Cross-tab consistency is weaker than the latest Index Options path. Current warning labels mitigate misrepresentation but do not make those premiums timely.

**Proposed repair / acceptance:** Use the same verified contract quote/depth timestamp contract across tabs before a plan is entry-ready; retain unverified values only as clearly dated research.

<a id="f24"></a>

## F24 — BANKNIFTY futures mapping remains a live acceptance blocker

**Severity:** Medium. **Evidence status:** User-reported live failure; exact current master cause not independently reproduced.

**Evidence:** [insights/data_layer/contracts.py:16](https://github.com/aadi5279-aptransco/Bharatfusion-signal/blob/147e27b35fe5848f4ac8c460a5fe3d82d418f691/insights/data_layer/contracts.py#L16) uses exact identity and rejects conflicts/ambiguity rather than guessing. User's latest pasted report still says NO_RESULT_OR_MAPPING, while stock futures map.

**Reproduction:** Run the existing PHASE0_CHECK.bat locally on this audited revision and retain the BANKNIFTY mapping check plus sanitized matching official master fields. Compare required columns, ID/symbol aliases, exchange, expiry and ambiguity. Do not paste credentials.

**Impact:** Order flow and any futures-dependent Bank Nifty strategy can remain unavailable. No specific master-row cause can be established from the pasted null result alone.

**Proposed repair / acceptance:** Diagnose actual master candidates and add a fixture for the verified failure; preserve fail-closed mapping instead of choosing a guessed contract.


## Look-ahead and repainting review

- **Confirmed execution bias:** F02/F03. Prefix-only inputs do not solve same-close/conditional-fill assumptions.
- **No confirmed future-feature leak in inspected pivot paths:** smc_expert waits for right-side confirmation; EMA9 trendline examines only pivots with N right bars in the supplied prefix; cycle_wave also waits for right bars. A marker drawn on its historical pivot date is not permission to trade at that date. Persist confirmation time separately before Phase 2 training labels.
- **Provisional daily data is intentional:** momentum_query builds a running daily proxy from completed 5m bars and labels it provisional. It can change later in the day. This is not future leakage at scan time, but substituting final daily OHLC into historical intraday replay would leak. Preserve each scan's as-of inputs.
- **Higher-period review:** EMA9 drops the initial partial resample bucket and checks closed period ends. Multibagger filters weekly/monthly labels by completed daily asof; its initial partial bucket and older-year holiday completeness are not independently certified. Swing's public scan accepts dates <=asof and relies on callers for completed daily data; do not call it directly with a current forming daily candle.
- **Point-in-time gaps:** current universe and imported fundamentals have no independently verified historical membership/filing lineage (F06/F16).
- **Required proof still pending:** prefix invariance, streaming-vs-batch equivalence, confirmation-time stamping, full/partial weekly/monthly holiday tests and next-bar fill replay in VALIDATION.md. Absence of a suspicious shift is not a proof of no leakage.

## Requirement coverage and unresolved checks

| Requested area | Audit conclusion / evidence |
|---|---|
| Data sources/failures/cache/IST/partial bars | Architecture map; F05/F06/F10/F19/F22/F24. Strong structural validation exists but no complete exchange-session certification. |
| Pre-open, normal hours, holidays/Muhurat | F09. Need segment/date-specific pre-open phases, auction/continuous boundaries and exceptional sessions. Official general pages can differ; dated circulars must govern. |
| 2/5/10/20% circuit bands and locked stocks | F07. Do not apply cash fixed bands universally to derivatives; load effective instrument ranges. |
| Lots/expiries/ban/strike step | F07/F08/F24. Actual chain strikes are selected. Stock parse_master and F&O scan exclude same-day expiry while index paths allow it: an explicit documented product policy is required, not an automatic extension of expired contracts. |
| BTST/T+1/ASM/GSM | Partial master flag filtering exists; no complete delivery/settlement/auction-risk gate. BTST is research, not assurance shares settle for sale. T+0 exceptions and effective settlement schedules must be distinguished. |
| Brokerage/STT/exchange/GST/SEBI/stamp/slippage | F04. No reconciled product/date/side charge engine. No claim of exact current tax rates in this audit. |
| Liquidity/impact/capacity | Turnover and volume/spread thresholds exist; F07/F10/F13/F15. No order-size-dependent market-impact/capacity validation. |
| Wilder RSI/ATR/ADX/EMA | F11; EWM is causal but seeds differ. EMA200 minimum length alone is not a universal convergence guarantee. |
| Session VWAP | Per-date reset exists; F22 for boundary. Cash indices' non-traded volume must not be treated as real volume; dashboard trend correctly does not require it. |
| Supertrend | Implemented separately in Swing and Positional; formulas inspected, golden numerical equivalence unrun. Initial trend convention and NaN propagation require fixture tests. |
| OBV | No shared OBV numerical contract established in reviewed core modules. Treat correctness/availability as unverified, not implemented by inference. Add flat-price/zero-volume fixture before advertising it. |
| Pivots/S&R/chart patterns | Prior rolling levels shifted; confirmed swing pivots in SMC/EMA9/cycle. Full requested Phase 2 pattern catalog is not present as one shared engine. |
| Warm-up/NaN/off-by-one | F11/F22 plus temporal validation matrix. Stronger validation exists at some consumers. Raw valid-bar count alone is insufficient per feature/timeframe. |
| Survivorship/overlap/double counting | F06/F15/F18. F&O one-underlying limit helps within that tab only. |
| Risk and option math | ATR/structure stops and premium CE/PE direction exist; F02/F04/F08/F15/F17/F23. PCR/max pain are context, not P(success); IV percentile is explicitly unavailable without history. |
| FII/DII freshness | Separate report dates, identity registry and quarterly stale flag exist. Quarterly holdings use >180-day stale flag; publication lag/revisions still lack point-in-time lineage. Empty verified deals is not zero foreign activity. |
| Multibagger fundamentals | Missing/stale imports fail or remain unverified; QGLP excludes identified financial sectors and warns about accounting quality. Values/units/restatements not reconciled to audited filings (F16). |
| Track Record honesty | Stop-first ties and one-way closure exist. F02/F04/F18 prevent interpreting it as full realised net performance or immutable complete issuance history. |
| Errors/races/duplicate jobs/memory/slow scans | F01/F12/F13/F19/F20/F21; load/race/soak tests not run. No claim of a measured memory leak. |
| Security | Read-only broker allowlist and guarded exit positive; F14. No penetration test or dependency vulnerability scan performed. |
| UI loading/empty/errors/numbers/IST | en-IN formatting and state reset exist; F21 for inconsistent timestamps and diagnostic/race concerns. Browser rendering/accessibility untested. |
| Logging/monitoring | Quota and data-health snapshots exist; global/latest reports and generic errors limit attribution. No measured SLO/latency budget. |
| “AI” and profitability | Heuristic ranks and expert rules, not calibrated models. No approved advanced ML stack, net-EV ranking, champion/challenger, CPCV or promotion evidence established. |

## Positive controls to preserve

1. Broker read-only restrictions, local exit token, conservative payload limits and browser security headers.
2. Dhan finite/OHLC/OI validation, conflicting duplicate rejection, quarantine summaries, partitioned cache and forming-candle removal.
3. Cash/index 09:15 grid filtering, explicit daily completion boundary, recent-data checks and frozen premarket watchlist.
4. Stop-first same-bar ambiguity resolution, OPEN-only journal closure, unvalidated/research labels and no fabricated win probabilities.
5. Confirmed-right-bar pivots, prior-window breakout references and incomplete-period handling in EMA9.
6. Real expiry/strike identity, independently checked ATM quotes in Index Options, and at-most-eight F&O candidates without padding.
7. Unverified FPI clients remain unclassified; quarterly ownership and aggregate participant context are not represented as complete daily stock flows.
8. Notifications have persisted read state; removing calendar navigation did not remove the shared alert workers.

## Repair order for approval, not implemented

1. F01 Intraday schema integration; F02/F03/F04/F18 honest issued/fill/outcome/cost accounting.
2. F05/F07/F08/F09/F10/F24 data, calendar, instrument and eligibility contracts.
3. F12/F13/F19/F20/F21 scheduling, diagnostics and operational checks; F14 common local API protection.
4. F11/F22 unified numerical contracts, then approved Phase 2 causal patterns.
5. F06/F15/F16/F17/F23 point-in-time context, portfolio/option consistency and dataset readiness before Phase 3.

Each repair needs its own regression and review. The user's phase-by-phase approval gate remains in effect.

## Official references checked

These are reference sources, not evidence that the application's local data matches them. Date-effective circulars and actual instrument files take precedence over general pages.

- [NSE market timings](https://betanseapi.nseindia.com/static/market-data/market-timings): normal cash session and pre-open order-entry boundary.
- [NSE pre-open description](https://www.nseindia.com/static/products-services/equity-market-pre-open): pre-open includes order matching/buffer; its general page differs from the timings page, so do not hardcode an undated universal phase schedule.
- [NSE cash price bands](https://betanseapi.nseindia.com/static/products-services/equity-market-price-bands) and [derivative operating ranges](https://betanseapi.nseindia.com/static/products-services/equity-derivatives-price-bands): distinguish band types.
- [SEBI surveillance source directory](https://www.sebi.gov.in/curation/surviellance.html): ASM/GSM exchange sources.
- [NSE Clearing ban-period circular](https://nsearchives.nseindia.com/content/circulars/CMPT71501.pdf): use effective ban rules/list rather than treating master presence as permission for a new position.
- [Dhan instrument schema](https://dhanhq.co/docs/v2/instruments/), [historical data](https://dhanhq.co/docs/v2/historical-data/), [market quote](https://dhanhq.co/docs/v2/market-quote/): source fields and API contracts.
- [Dhan charges](https://dhan.co/pricing/): product-specific charges and rounding; values need versioning and contract-note reconciliation.
