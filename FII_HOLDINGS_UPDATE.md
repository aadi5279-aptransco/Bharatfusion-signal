# FII stock lists: ownership changes and disclosed transactions

The original tab can download deals but show zero FII-labelled trades when no
verified client registry is configured. That is an attribution gap, not proof
that foreign investors bought/sold no shares.

This update adds a separate quarterly ownership comparison above the existing
NSE disclosures. It does not relax client verification or replace the verified
disclosed-deal lists used by other strategies.

## Install on the existing Windows application

1. Download the ZIP for this fix branch and extract it into a separate folder.
2. Stop the running server with Ctrl+C.
3. Open the extracted folder containing UPDATE_FII_HOLDINGS.bat.
4. Double-click UPDATE_FII_HOLDINGS.bat. The default destination is:
   H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
5. The updater backs up matching source files to update_backups, copies the
   complete insights Python module set and web/src/main.js + styles.css,
   runs both test suites, and runs npm run build in the existing web folder.
   Existing .env, data, credentials, and local-only files are retained.
6. After success, run START_INSIGHTS.bat in your EXISTING project. Reload the
   browser with Ctrl+F5. Do not launch the extracted ZIP as a new application.

For another destination, open CMD in the extracted update folder and run:

```bat
UPDATE_FII_HOLDINGS.bat "D:\your\existing\project"
```

The updater uses your existing Python and npm setup. There are no new Python
or frontend dependencies. If any test or build fails, it stops before startup;
save the error output. File-copy failures roll back automatically. A later test
failure leaves the source installed and backed up. To roll back, restore the
files from the printed backup directory and rebuild the old frontend. Newly
added modules can remain unused; no settings/database deletion is needed.

## Get stock lists

1. Open FII Stock Deals.
2. At the top, review/edit the NSE symbols (up to 200). The initial 25-symbol
   basket is only an example, not an exhaustive market scan or index membership.
   Alternatively click Use downloaded deal stocks to fill symbols from your
   stored NSE deals (up to 200, with the total count shown). This selects the
   universe only; it does not classify the underlying deals as FII transactions.
3. Click Scan quarterly FII holdings. The independent worker reads PUBLIC
   Screener company shareholding tables, with a pause between requests. It does
   not use Dhan quotas or hold the intraday scanning lock.
4. Watch progress. Click Increased holdings or Decreased holdings. Search a
   company or set Minimum change (pp). The tables show previous/current FII
   percentages, exact reporting quarters, change in percentage points, retrieval
   time, and a source link. Unchanged companies are counted separately.
5. Missing pages, changed schemas, unavailable latest values, mismatched NSE
   symbols and non-consecutive/future quarters produce explicit failures, not
   invented zero holdings. HTTP 401/403/429 or login redirects stop the batch.
6. Successful per-stock results are cached for 24 hours and saved across app
   restarts. No-data/blocked refreshes retain the prior saved list, with status
   and saved timestamp visible. Partial scans disclose missing/not-attempted
   stocks. Reports older than 180 days have a visible stale label. Different
   companies can report different latest quarters; inspect each row's dates.

## Broader Screener query route

Open the query links under “Scan a wider market with Screener queries / import
CSV”. Custom queries may require your own Screener sign-in/export entitlement.
This application does not store that login or bypass access controls.

Increased ownership:

```text
Change in FII holding > 0
```

Decreased ownership:

```text
Change in FII holding < 0
```

Add FII holding and Change in FII holding columns. Export your chosen universe;
if Excel is downloaded, save as CSV UTF-8. Supported column sets:

- Screener export: Name (or Symbol), FII holding, Change in FII holding.
- Explicit dated comparison: Symbol, Previous pct, Current pct,
  Previous quarter, Current quarter. Quarter values: 2026-06-30 / 2026-09-30.

Download blank dated CSV headers from the tab if needed. Import CSV replaces
only the saved ownership comparison list; it never changes disclosed-deal data.
Combine increased and decreased rows in one file if you want both lists in one
snapshot. Duplicate companies, incomplete rows and invalid values reject the
entire import before writing. Maximum 2 MB / 10,000 rows.

Undated Screener exports are labelled “period not supplied”; previous holding is
calculated as current holding minus the provider's reported change. Company
names are not guessed into NSE symbols. Imported numbers are user-supplied,
not independently verified against exchange filings. Name-only rows are still
searchable and displayed as company names. All lists are explicitly limited to
the selected symbols or imported rows; they do not claim whole-market coverage.

## Meaning of the result

Change (percentage points) = current-quarter FII percentage minus previous-quarter
FII percentage. Positive means ownership increased; negative means it decreased.
This is not the number of shares bought/sold or proof of daily cash transactions:
changes in share capital and classification also change ownership percentages.
Public quarterly holdings are secondary-provider research, not primary NSE
transaction records, and are never fed into the verified daily-deal signal.

Sources: https://www.screener.in/company/RELIANCE/consolidated/#shareholding
and https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern

## Validation

Offline tests cover dated parsing, yearly-table exclusion, exact NSE-symbol
identity, missing/bad data, CSV validation, atomic preservation, access-denial
handling, caching, Windows-style closed SQLite handles, API import and origins,
and separation from verified daily deals. Existing Insights and scheduler tests
remain required. The frontend must be rebuilt after installation.
