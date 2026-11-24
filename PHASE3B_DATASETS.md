# Phase 3B — research snapshots and baseline evaluation primitives

Builds on Phase 3A commit `1819550c6d59532b9c76b035d7c5114dd8f75495`.
This stage adds on-demand history collection to Model Health. It does not promote
models, replace current signals, or fix the Phase 2 BUSY behaviour deferred by the
user. Phase 3 remains in development.

## New application workflow

1. Open **Model Health** after installation.
2. Enter an exactly mapped stock symbol/name (the existing Dhan mapping is used).
3. Choose 1–30 calendar days and click **Save Dhan snapshot**.
4. The app requests completed 5-minute history once, validates it, and persists
   a content-addressed snapshot with its instrument identity and manifest.
5. Accepted/quarantined counts, last candle in IST and RESEARCH_ONLY appear in
   Saved snapshots. Up to 30 recent snapshots are displayed. Data survives restart.

Works after hours as well as during the session when broker historical data is
available. No automatic scheduled history download, training or orders are added.
The existing scan lock prevents simultaneous broker scans. BUSY means no snapshot
was created; wait for the running scan to finish before retrying. The button stays
disabled during a request. Closing the page does not cancel a server-side download.
Index volume can be zero; such rows are quarantined instead of inventing volume.
Start with a liquid mapped equity rather than an index for this collection test.

## Data contract

`insights/alpha/datasets.py`: SHA-256 over canonical JSON containing the complete
manifest, accepted rows and quarantine reasons. SQLite transaction and immutable
triggers prevent accidental modification; reads recheck content hashes. Identical
payload retries are idempotent. A later collection timestamp creates a new snapshot.
This is not tamper-proof against an administrator rewriting the database.

Reject naive timestamps/missing columns; quarantine malformed numbers, zero volume,
duplicate or unordered timestamps, invalid OHLC and non-regular 09:15–15:30 five-
minute grid bars. Forming candles are excluded. Counts of observed within-session
holes are recorded. Whole missing days, opening/closing truncation, exchange holidays
and special sessions are **not** certified by this grid check. Zero-volume rejection
is conservative and does not assert that every zero-volume broker candle is invalid.

Only whitelisted instrument fields are persisted; credentials and raw exceptions
are never part of a snapshot. Dhan source here means the existing broker adapter
was used; it is not independent validation of every candle's provenance.

Every snapshot stays `training_ready=false`. Adjustment, point-in-time universe,
calendar, dated eligibility, costs and tick/lot histories remain unverified. There
is deliberately no override/approve endpoint. Multi-year ingestion, expired options,
corporate-action processing and gold pattern labels remain later work.

## Baseline primitives

`insights/alpha/baselines.py` exposes typed `Event` and pure `evaluate` functions
for developer research. The UI does not train a model from raw snapshots yet.

- Explicit final holdout cutoff excludes events whose features OR label intervals
  cross the boundary before any fit or statistics.
- Expanding purged chronological folds with an embargo; duplicate IDs, future-dated
  features, non-finite values and unsorted event times are rejected.
- Logistic regression uses training-only standardization, overlap/recency weights,
  fixed L2 and 300 iterations; no hyperparameter search or calibrated probability.
- Reports take-all rule candidates, logistic selections, and deterministic seeded
  random candidate selections with the same selection count per fold.
- Reports counts, mean/sum net R and diagnostic uncalibrated Brier scores. Input
  outcomes must already be net of costs. This is not portfolio P&L or a Sharpe ratio.

Random candidate selection is NOT the mandatory random-entry baseline. Nifty/buy-
and-hold, true random-entry, calibration, CPCV, DSR/PBO, significance, stress/capacity
and paper-forward validation remain outstanding. `promotion_allowed=false` always.
A feature timestamp alone does not establish causal provenance. Real-data training
must wait for validated inputs and the remaining acceptance gates.

## Storage and backup

Default database: `%USERPROFILE%\.bharatsignal-insights\research\datasets.sqlite`.
If `BHARATSIGNAL_INSIGHTS_HOME` is configured, use its `research` subdirectory.
Data is outside the application folder by default. **Back up the entire app folder
AND this configured data directory while the application is stopped.** Earlier
instructions to back up only the app folder did not cover this external data root.
Do not upload credential files to GitHub or share them in logs/screenshots.

## Install on the existing Windows system

1. Exit using Logout / Exit and back up the application and configured data folder.
2. Download the Phase 3B branch ZIP; extract separately, not into the running app.
3. Open the extracted folder containing `tools`, `insights`, `web` and
   `PHASE3_CHECK.bat`. Type `cmd` in File Explorer's address bar and press Enter.
4. Run the following updater command there:

```bat
"H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights\.venv\Scripts\python.exe" tools\install_fii_holdings_update.py --project "H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights"
```

5. Switch to the installed application and run tests:

```bat
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
PHASE3_CHECK.bat
```

6. If tests pass, build the interface, then launch (one command at a time):

```bat
cd web
npm run build
cd ..
START_INSIGHTS.bat
```

7. Press Ctrl+F5 in the browser; open Model Health. Expected status:
   **DATASET COLLECTION — NO APPROVED MODEL**. Save one seven-day stock snapshot.
8. Verify a saved row appears. RESEARCH_ONLY and no champion are expected, not errors.
   Source error/BUSY is not a successful save. Stop and share the sanitized error if
   tests/build fail. Do not proceed to AI training just because a snapshot exists.

No additional ML dependencies are required. This is a source update requiring the
existing Python and Node installation. The updater preserves credentials/databases
and backs up overwritten source files. It includes the new research modules.
