# Phase 0 — Dhan data infrastructure checkpoint

This change extends the existing BharatSignal Market Insights application, based on commit `19f235b82278b78e982545faed23094764a9ffaf`. Earlier unpublished strategy-audit edits are excluded. Phase 1 and the Pattern/Alpha Engines have not started.

## Status and evidence boundary

The implementation and offline fault-injection tests are delivered. **Phase 0 empirical acceptance is NOT complete.** No Dhan credentials or local `.env` were available in the development workspace. No live or sandbox authentication, market data, corporate-action adjustment or performance claim is made. The application's existing strategies remain research rules, not a trained/self-improving AI.

## Current official contract findings (reviewed 22 November 2026)

| Topic | Documented contract | Implementation / remaining evidence |
|---|---|---|
| Base | `https://api.dhan.co/v2` | Fixed host; no arbitrary caller URL; redirects blocked |
| History | POST `/charts/historical`, `/charts/intraday` | Same fields as existing adapter; daily `toDate` exclusive |
| Intervals | 1, 5, 15, 25, 60 minutes | Unsupported intervals rejected |
| Intraday availability | Up to five years for active instruments; maximum 90 days per request | Stable calendar-month partitions, at most 31 days; actual limits not empirically tested |
| Authentication | Access token required; client-id required for quote/chain; profile GET accepts token | Credentials from existing local environment; account/token excluded from health reports |
| Profile | `/profile` includes token validity, data plan and data validity | Background startup/periodic read, health status and UI display |
| Rate limits | Data 5/s and 100,000/day; quote 1/s; chain one unique request/3s | Capacity-one buckets: data 4/s, quote 0.9/s, chain one/3.1s. Conservative global chain serialization |
| Timestamps | Epoch timestamp | UTC epoch parsed then converted to timezone-aware Asia/Kolkata; empirical timezone validation pending |
| Instrument master | Official detailed CSV includes IDs, underlying IDs, expiries and lots | Validated daily persisted master; existing application parser retained |
| Adjustments | No verified adjustment contract established by this work | Explicit AS_REPORTED / UNVERIFIED label; no guessed split/dividend factors |
| Sandbox | No suitable market-data sandbox endpoint/capability verified | Not run; no invented sandbox URL. Offline fixtures are not a Dhan sandbox |

Sources:
- https://dhanhq.co/docs/v2/
- https://dhanhq.co/docs/v2/historical-data/
- https://dhanhq.co/docs/v2/authentication/
- https://dhanhq.co/docs/v2/option-chain/
- https://dhanhq.co/docs/v2/instruments/

## Architecture and code

`DhanReadOnly` → restricted read-only compatibility client → `Transport` → exact method/path allow-list → limiter/quota → fixed HTTPS host.

History additionally passes through `HistoryStore` → validation → atomic SQLite chunk commit. Interrupted downloads resume from committed monthly partitions. Recent data overlaps the previous day for corrections; the persistent cache advances at completed-candle boundaries. Historical partitions revalidate after 24 hours.

Files:
- `insights/data_layer/transport.py`: read-only allow-list; redirects blocked; bounded retry/jitter for HTTP 429/5xx/network failures; no retry for authentication failures; sanitized errors.
- `insights/data_layer/history.py`: history partitions, incremental overlap, persistent cache, bad-response quarantine fingerprints and quality reports.
- `insights/data_layer/master.py`: official detailed master cache and schema checks.
- `insights/data_layer/client.py`: existing adapter-compatible read methods; unsupported SDK methods raise.
- `insights/brokers/dhan.py`: guarded REST facade, quote/depth transport integration, profile and data-health reporting.
- `web/src/data_health.js`: connection/subscription/quota/quality context inside the existing application.
- `insights/phase0_check.py`: explicit local live read-only smoke harness; offline by default.

SQLite is used because it ships with Python and supports transactional chunk/checkpoint updates on Windows without another database service. It is row storage, not a columnar engine. This is a bounded data-layer foundation, not a completed multi-year training warehouse.

Quota counters survive restarts and include each retry. Data plus chain calls share the 100,000 local daily ceiling and 80% warning. Quote/profile counts are separately visible. Buckets are shared among this application's threads, not separate Python processes. Account-wide usage by other applications cannot be observed; run one BharatSignal backend per account. The instrument CSV uses a separate unauthenticated official host.

## Validation and quarantine behaviour

- Reject missing/unequal/empty arrays, non-finite or nonpositive prices, invalid OHLC ordering, negative volume/OI, conflicting duplicate candles, missing requested OI.
- Deduplicate identical candles; exclude unfinished candles.
- Count zero-volume observations rather than treating all zero-volume index bars as corruption.
- Flag within-day gaps; do not fill candles or assume holiday/special-session gaps are missing trades.
- Quarantine response fingerprint/array-length metadata, not authenticated raw responses or secrets. No chunk checkpoint is committed for rejected responses.
- Market data remains unadjusted/as reported until independent corporate-action evidence is supplied. No synthetic adjustment layer is promoted.

## Offline verification of initial commit 283da1b

- 399 Market Insights tests passed, including 20 Phase 0 transport/cache/fault tests.
- 3 root tests passed.
- Production Vite frontend build passed (39 modules).
- No Windows or authenticated Dhan execution was performed here.

## Acceptance items still open

1. Real profile/subscription and token-expiry behaviour on the user's account.
2. Historical/intraday/OI reads for representative large/mid/small caps, index/stock futures, current ATM options and expired contracts.
3. Empirical 90-day request boundary and inclusivity behaviour; multi-year completeness and download performance.
4. Known split/bonus/dividend comparisons and an attributable corporate-action source before adjustment/training.
5. Muhurat/special-session calendar; suspension, delisting, SME, ban and surveillance eligibility. Existing regular-session rules are not replaced in Phase 0.
6. Full live-market observation of forming candles, sparse ticks, missing bars and zero-volume responses.
7. Sandbox availability and capabilities must be confirmed with Dhan. Never treat fixture tests as sandbox/live evidence.
8. Windows execution and full-session soak testing.

The old strategy code and legacy launcher are not declared fully audited by this phase. No profitability, calibrated win rate or production-ready ML claim is made.

## Install on the existing Windows PC

1. Close BharatSignal with **Logout / Exit**.
2. Download this phase's GitHub ZIP and extract to a separate folder.
3. Run `UPDATE_PHASE0.bat`. Default destination: `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`.
4. For another destination, open CMD in the extracted folder and run `UPDATE_PHASE0.bat "C:\path\to\existing\app"`.
5. Wait for tests/build success. Credentials/settings/databases are preserved; old source files are backed up under `update_backups`.
6. Start the installed app's `START_INSIGHTS.bat`, press Ctrl+F5, and expand **Dhan data health**.
7. From CMD in the installed app folder, run `PHASE0_CHECK.bat` for offline preflight. Run `PHASE0_CHECK.bat --live` only with your locally configured valid credentials and active Data API access. This sends read requests only.
8. Reports are saved under `%USERPROFILE%\.bharatsignal-insights\phase0_reports` (or your configured `BHARATSIGNAL_INSIGHTS_HOME`). Share the sanitized report, never your `.env` or token.

Do not delete existing journal databases. The new `dhan_data.sqlite` contains market data, validation metadata and local quota accounting. Clearing it also clears local quota history, so it is not a quota-reset mechanism.

After evidence review, stop for approval before Phase 1.

## Follow-up diagnostic correction — 23 November 2026

The user's local report dated 22 November confirms authenticated read calls, an active data plan, instrument-master retrieval and successful candle/option-chain responses. This is user-supplied smoke evidence, not full-session certification.

The follow-up fixes missing mappings being marked PASS, requests daily derivative OI, records expiry/strike/side/security ID for option samples, and distinguishes download metadata from returned-frame coverage. Observed-date regular-grid checks now flag missing tails, off-grid timestamps, outside-session observations and partial end-of-session bars. A 200-bar research baseline is disclosed separately from strategy readiness; it is not a universal indicator requirement. Sparse data is REVIEW, not an unconditional PASS.

Transport exceptions retain only validated numeric provider/HTTP codes. Raw provider messages and credentials are not written to the report.

**Follow-up verification is pending.** The execution environment was unavailable; eight new regression tests were added but not executed here. The earlier 399+3 results apply only to the initial commit. Run the existing update script's full tests before starting the app.

These changes improve evidence and diagnostics. They do not establish the cause of the missing index-futures mapping, repair provider history gaps, shift timestamps, fill missing bars, or certify special sessions. The adapter's existing candle filtering is unchanged pending executable regression checks and provider evidence. Phase 0 acceptance remains open; Phase 1 is paused.

## Report comparison and request-boundary correction — 23 November 2026

Reviewed the user's 09:57 IST report: three checks PASS, three UNAVAILABLE, forty REVIEW. The latest 1-minute candles end at 09:56 and 5-minute candles at 09:50. This supplies a live-session sample, not a full-session soak test.

A checker defect counted candles before the actual seven-day request start as missing. Coverage now excludes those timestamps using the explicit requested start; it does not infer that missing leading data is acceptable from the first returned candle. Two new regression tests verify that request truncation is excluded while missing end-of-day candles remain flagged.

Remaining observed issues: BANKNIFTY futures mapping absent; ATM CE and PE daily requests return HTTP_400; stock historical sessions have missing end-of-day candles; derivative timestamp/session anomalies remain. The 200-bar research warning is expected for the short diagnostic windows and does not itself establish provider failure. Contract identity and raw-response evidence are still needed before changing mappings or timestamp semantics.

Verification: 30 focused Phase 0 tests and 3 root tests passed locally. Full-suite rerun status is recorded below. No new authenticated Dhan calls were made in this workspace.

Full-suite rerun after restoring workspace Flask/websocket dependencies: 409 Insights tests passed; 3 root tests passed; Python compile check passed. The earlier eight evidence tests are now executed successfully, plus two request-boundary regressions. Frontend code was unchanged in this correction.

## Mapping and daily option request correction — 23 November 2026

The index-futures resolver now normalizes master IDs/whitespace, restricts known indices to their exchange, and permits an exact UNDERLYING_SYMBOL alias match only if candidate underlying IDs are absent or placeholders. An explicit conflicting ID, conflicting symbol, or multiple contracts at the nearest expiry still blocks mapping. No contract display-name substring matching or hardcoded security IDs are used. The result records its mapping method and official master fields.

Daily option requests now omit optional expiryCode. Futures requests retain it. This follows Dhan's instrument documentation, which describes expiry code as applicable to futures contracts: https://dhanhq.co/docs/v2/instruments/ . It is a candidate correction for the reported HTTP_400, not proof of its cause. Rejected requests continue to report UNAVAILABLE; they are not relabelled PASS and no synthetic daily data replaces the response.

Ten regression tests and a credential-free GitHub Actions workflow are included. The local execution environment was unavailable for this revision. Previous 409+3 results apply to the preceding commit, not this change. Check the PR's new CI result and run UPDATE_PHASE0.bat locally before use. Real-Dhan validation of both changes remains pending. Full Phase 0 acceptance is not claimed.
