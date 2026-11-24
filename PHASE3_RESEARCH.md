# Phase 3A — research foundation

This starts Phase 3 on top of Phase 2 commit
`66726e1c0b87bab1e0eedf530f6aba2cff74335a`. It does **not** complete Phase 3.
No trained model, validated probability, profit claim, automatic training job,
or model promotion is included. The existing Phase 2 BUSY issue is deferred as
requested. Existing tab signal rules and Track Record are unchanged.

## Application

Open **Model Health** in the sidebar. It shows the actual development stage,
implemented primitives, blocked data requirements, and remaining work. Empty
champion/metrics are intentional: no synthetic results are presented as live
performance. GET `/api/v1/market-insights/model-health` is read-only and does not
download data, train a model, acquire the scan lock, or call a broker.

## Implemented code

`insights/alpha/research.py` provides immutable typed inputs and pure functions:

- `Candidate` requires a point-in-time ATR, historical liquidity, verified
  eligibility, a tick size, integer quantity and valid lot-size multiple.
- `Fees` requires explicit rates, provenance and inclusive effective dates.
  Each fill produces brokerage, STT, exchange, SEBI, stamp, IPFT, GST and optional
  delivery-sale fee components. STT/stamp use whole-rupee half-up rounding; other
  charges use two decimals. This is a per-leg research estimate, not exact
  contract-note aggregation. Flat and capped brokerage are explicit inputs.
- `label` enters at the immediate next candle open, applies adverse tick-rounded
  slippage, then anchors ATR-scaled barriers to that fill. Both barriers touched
  means stop first. Stop gaps use the worse open; target gaps receive no better
  price than the barrier. A time limit closes at the last permitted candle.
  Incomplete labels stay PENDING. Locked or illiquid bars quarantine outcomes.
- Capacity uses prior known volume. Slippage is base bps plus impact bps times
  square root of participation. This is an explicit conservative assumption,
  **not an empirically calibrated impact model**. Observed subsequent bar volume
  can invalidate a fill but is never used to improve the entry's slippage.
- `walk_forward` creates expanding chronological train/test folds, purging
  training labels whose end is not strictly earlier than test start minus an
  embargo. Insufficient training folds are skipped. No random splitting.
- `uniqueness_weights` integrates reciprocal overlapping-label concurrency and
  applies exponential recency decay. Calculate separately inside training folds.
- `opportunity_score` accepts a lower confidence probability bound and gross
  average win/loss R, then deducts costs, slippage, uncertainty and correlation
  penalties. Regime discounts cannot improve a negative edge. This helper does
  not estimate probabilities or grant permission to publish a signal.
- `assert_prefix_causal` tests feature outputs against every historical prefix.
  It catches retrospective feature changes, not every possible source leak.

`insights/alpha/journal.py` provides a separate SQLite research event journal:
unique IDs, identical retry idempotency, conflicting rewrite rejection,
transactional appends, UPDATE/DELETE rejection and hash-chain verification.
It is not the app's Track Record, a trained-model registry, or protection against
an administrator rewriting an entire file. Corrections must be new events.

## Scope boundaries and acceptance requirements

The first evaluator handles contiguous completed **intraday normal round trips**.
It rejects missing/overnight bars. Calendar-aware overnight/daily labels, option
exercise and assignment, physical settlement, funding, corporate-action events,
margin constraints and partial fills are not yet supported. No market index may
be treated as an executable contract. Options must use premium candles and the
correct instrument identity; continuous futures need explicit roll treatment.

The research caller owns data provenance: immediate following bars, session
eligibility, adjusted history, point-in-time features and universe membership.
There is no automatic Dhan dataset ingestion or historical training yet.
Do not train until Phase 0/1 data limitations are resolved and documented.

No live default tariff is embedded. Rates vary by segment and date; today's rates
must not be applied to earlier years. Reference checked 24 November 2026:
https://dhan.co/pricing/ . Verify dated tariffs and contract notes before running
real research. The unit-test tariff is deliberately synthetic.

## Remaining Phase 3 stages

1. Point-in-time dataset ingestion, quarantine, manifests, calendar-aware labels,
   cost histories and human pattern review queue.
2. Rule/random-entry/Nifty/logistic baselines; purged out-of-sample experiments,
   sealed holdout and a separate paper-forward window.
3. Meta-label learners, calibrated probabilities and conformal uncertainty;
   benchmark CNN/Transformer/regime/ensemble complexity only against baselines.
4. CPCV, trial accounting, DSR/PBO/significance and stress/capacity reports.
5. Outcome reconciliation, failure clusters, bounded challengers, versioned model
   registry, all-required promotion gates, monitoring and rollback.

No promotion API exists in 3A, so no model can be promoted by these modules.
The full gate set in the user's Phase 3 specification remains mandatory.

## Install and test

Close the app, back up its folder, and extract this branch's ZIP separately.
In CMD in the extracted source folder, run:

```bat
"H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights\.venv\Scripts\python.exe" tools\install_fii_holdings_update.py --project "H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights"
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
PHASE3_CHECK.bat
cd web
npm run build
cd ..
START_INSIGHTS.bat
```

Stop if a command fails. The historical updater name is retained; it copies the
new alpha Python package, Model Health UI and check scripts with backups and
preserves credentials/databases. Existing Python/Node installation is required.
Open Model Health; expected status is **RESEARCH FOUNDATION — NO TRAINED MODEL**.

Tests cover next-bar entry, long/short labels, stop-first ties, gaps, time exits,
future-bar exclusion, post-resolution invariance, cost dates, participation and
lots, bad bars, purged folds, overlap weights, leakage detection, conservative
scores, journal idempotency and the health API. These are correctness tests,
not backtests proving predictive performance.
