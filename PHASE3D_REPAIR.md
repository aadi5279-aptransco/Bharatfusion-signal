# Phase 3D — scoped calendar verification and fresh-source repair

This update adds an explicit "Verify and repair from Dhan" button to each snapshot
in Model Health. It does not grant training approval or certify historical prices.

## What is verified

Published NSE cash-equity 2026 closure dates are taken from circular NSE/CMTR/71775:
https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf .
24 November 2026 is a holiday, so zero expected bars are shown for that date.
The list applies only to NSE_EQ. Other segments/years, special sessions and later
calendar amendments remain unverified. Rows on a published holiday are conflicts.

## What repair does

- Reads and hash-verifies the selected saved snapshot. Uses its stored instrument
  ID/segment/type, original capture cutoff and requested window.
- Uses the existing broker authentication and rate-limited, quota-counted transport.
  Requests at most five affected sessions per click, twice per day (5m and 1m).
  Transport retries may cause more HTTP attempts. Other scans are excluded by the
  existing job lock. BUSY means no work was performed.
- Sends day-specific midnight-to-next-midnight requests directly to the official
  /charts/intraday endpoint, bypassing both application history caches.
  Reference: https://dhanhq.co/docs/v2/historical-data/ .
- Validates OHLCV/timestamps and closed regular-session bars. Keeps only rows inside
  the original snapshot window. No future data is added.
- Fills absent bars with fresh positive-volume 5m bars, or OHLCV aggregation of
  exactly five contiguous 1m candles. This is resampling real observations, never
  forward filling/interpolating missing prices.
- If both intervals disagree, leaves that bar unresolved. Accepted parent candles
  are never overwritten, even if the refreshed source differs.
- Saves a new immutable child snapshot, parent ID, request response hashes, source
  counts, last usable timestamps, added-bar provenance, conflicts and residual
  gaps. Failed requests are sanitized; raw exceptions/credentials are not saved.
- Does not alter shared broker caches, live tab signal history or the original
  snapshot. A source discrepancy report is evidence, not a proven root-cause
  attribution between provider history, caches or the previous adapter version.

When no usable source candles are returned, the report says NO_ROWS_RECOVERED.
It does not fabricate success. If more than five sessions need repair, deferred
sessions are listed; repeat on the newest child after reviewing the report.
Persistent earliest-session gaps may need source investigation before later batches.

## Remaining limitations

Corporate-action adjustment, point-in-time universe and eligibility, dated tick/lot
and fee histories are NOT certified by this operation. training_ready remains false
even when every regular-session candle is present. Historical source corrections
and cross-interval conflicts require review; earlier conflicts stay visible.
Published closures do not certify special sessions. Repair is NSE cash-equity only.
Existing source/holiday configurations for other application tabs are unchanged.

The tool cannot guarantee recovery of your 12 missing candles: the real Dhan response
must contain valid originals. No actual customer credentials were used in development.

## Install (existing Windows source installation)

No new full application copy is required. Keep your existing backup; the updater
backs up replaced source files. There is no database migration and old snapshots
remain intact. Close the application before updating.

1. Download the Phase 3D branch ZIP and extract into a separate folder.
2. Open the extracted source folder containing insights, web, tools and
   PHASE3_CHECK.bat. Type cmd in File Explorer's address bar.
3. Run:

```bat
"H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights\.venv\Scripts\python.exe" tools\install_fii_holdings_update.py --project "H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights"
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
PHASE3_CHECK.bat
```

4. Stop on any failed test. If successful, run separately:

```bat
cd web
npm run build
cd ..
START_INSIGHTS.bat
```

5. Press Ctrl+F5, open Model Health, expand the original RELIANCE snapshot.
   November 24 should show VERIFIED_HOLIDAY and zero expected/missing bars.
6. Click Verify and repair from Dhan once. Wait; requests may take several minutes.
7. Inspect the newly saved child snapshot. Review recovered count, remaining gaps,
   conflicts, per-day source results and deferred sessions. Keep the parent.
8. If all twelve missing candles are returned, your original 288-row example can
   become 300 accepted rows. This is conditional on real source availability, not
   a promised result. Training stays blocked pending the other provenance gates.

Tests run via GitHub Actions on Linux and Windows Python 3.11, with a frontend
production build. Local execution workspace was unavailable while preparing this
update. Synthetic tests exercise recovery, incomplete minute groups, conflicts,
holiday scoping, original preservation, busy locks, failures and API restrictions.
