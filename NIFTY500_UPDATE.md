# NIFTY 500: Intraday and Positional

This update builds on the Analyse SMC branch and retains the earlier application features. No order placement is added. It improves universe coverage and scan reliability, not proven trading performance.

## What changes

- Intraday resolves the current official NIFTY 500 list to Dhan NSE cash security IDs by exact ISIN. No fuzzy company-name matches and no invented F&O contracts. The full eligible constituent universe is considered at 09:45, 10:00, 11:00, 12:00, 13:00, 14:00 and 15:00 IST. Only the liquid shortlist receives five-minute strategy checks, as before.
- Intraday's strategy-shortlist limit remains `INSIGHTS_MAX_SYMBOLS` (default 30). This is not a limit of 30 on constituent discovery. Existing F&O and Swing selection behavior stays separate.
- Positional uses the same NIFTY 500 membership. Discovery rotates over the entire eligible universe, rather than repeatedly starting at the first 30 mapped F&O stocks. Default discovery batch: 25; up to 25 existing setup stocks get a separate monitoring lane in each five-minute cycle. The lanes alternate to avoid starving discovery.
- Daily and EMA9 higher-timeframe caches remain in use. A cold start requires several cycles: 495 eligible equities require at least 20 discovery cycles at batch size 25, about 100 minutes of scheduled cycle capacity; slow sources and competing jobs can take longer. This is NOT a promise to fetch all 500 multi-timeframe charts every five minutes. Existing candidates receive priority monitoring, subject to the cycle budget.
- Positional cursor/progress survive restart. On timeout, completed results and progress are published. A failed stock no longer repeatedly prevents later stocks from being considered. Progress resets for a new completed daily session or changed universe.
- Rows retain their own check timestamps. Refreshing one batch does not make other stocks appear fresh. Rows older than 10 minutes are marked stale. Missing five-minute price data resets entry readiness instead of reusing a previous READY label.
- Both tabs expose constituent counts, exact mapping failures, exclusions, list retrieval time and source errors. The global `INSIGHTS_WATCHLIST` does not silently truncate the new Positional NIFTY 500 universe.

## Notifications marked as read

Read notifications are removed from the dashboard inbox and in-app popups. Both individual **Mark as read** and **Mark all read** persist in SQLite, so read alerts stay hidden after page refresh or application restart. Reading one alert does not mark unrelated alerts read. Mark all affects alerts up to the displayed snapshot; new alerts arriving during the request remain unread. Duplicate detection retains read records so the same setup is not republished. Poll responses from before a read action cannot restore the old inbox in the browser.

After installation, mark one alert read, refresh the page and confirm it stays hidden. Use Mark all read to clear the inbox, then check that genuinely new alerts still appear.

## Source handling and eligibility

Official CSV: https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv

Index information: https://www.niftyindices.com/indices/equity/broad-based-indices/NIFTY-500

Dhan master documentation: https://dhanhq.co/docs/v2/instruments/

The list refreshes daily. Downloads are size/schema/count/duplicate validated and atomically cached. On failure, a validated cache can be used for up to seven calendar days, prominently marked as cached with a refresh error; this does not prove membership remained unchanged. Expired/unavailable membership blocks these NIFTY 500 selections without substituting the entire exchange. Retry cooldown is 30 minutes; Intraday observes it on its next scheduled discovery. Dhan mapping refreshes once per local date.

The downloaded list checked during development contained 501 rows, including a dummy corporate-action placeholder. It mapped 495 regular NSE EQ equities with zero missing or ambiguous mappings. Six entries were explicitly excluded: BAGMANE, BIRET and EMBASSY (RR), HFCL and STLTECH (BE), and DUMMYHEG (dummy). These are observations of that download, not a frozen list. The app shows the actual live counts. This release covers regular equity stocks; REIT and trade-to-trade strategies require separate handling and are not silently treated as regular intraday equities. Dhan ASM/GSM `Y` flags are also excluded; this is not a comprehensive regulatory eligibility guarantee.

## Install on your existing Windows computer

1. Close BharatSignal using **Logout / Exit**.
2. Download the complete ZIP from the new feature branch linked in the pull request. Use **Code → Download ZIP**, or the commit ZIP link supplied with the update.
3. Right-click the ZIP → **Extract All**. Extract into a separate folder, not over the working app.
4. Open the extracted folder that contains `UPDATE_NIFTY500.bat`.
5. If your installed app is still at `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`, double-click `UPDATE_NIFTY500.bat`.
6. For a different destination, open CMD in the extracted folder and run:

```bat
UPDATE_NIFTY500.bat "C:\Users\YourName\BharatSignal"
```

7. The script installs required Python packages, backs up changed application files, copies updated code, runs tests and rebuilds the frontend. It preserves `.env`, credentials and databases. Do not continue if a step fails.
8. Start `START_INSIGHTS.bat` in your **installed app folder**, not the extracted update folder. Refresh the browser with Ctrl+F5.

The update requires the existing Python virtual environment and Node/npm. For a new computer, follow the fresh-installation guide using this complete ZIP instead of an older ZIP.

## Check that it works

1. Open **Positional**. Check the NIFTY 500 source status, constituent count and mapped eligible equities. Wait for a cycle to finish.
2. After another five-minute cycle, verify cumulative attempted/assessed counts increase and pending counts reduce. Different rows should carry their own `Last checked` time. Source errors explain unavailable charts; they are not buy/sell signals.
3. During a verified market session after 09:45 IST, open **Intraday**. Verify NIFTY 500 valid/missing quote counts and the shortlist. The quoted universe can be much larger than the strategy shortlist.
4. At the next scheduled hourly refresh, verify the shortlist refresh timestamp advances. Between those slots only strategy checks should repeat.
5. Inspect any setup's stock, entry reference, T1, T2, SL, strategy, reason and freshness. A source failure or stale result must not appear as a fresh entry recommendation.

Optional batch tuning in `.env` (restart after changing):

```dotenv
INSIGHTS_POSITIONAL_BATCH_SIZE=25
```

Range: 1–100. Larger batches do not override the 240-second soft cycle budget or broker limits. Increasing this value is not a guarantee of faster complete coverage.

## If the official constituent download is blocked

Download the CSV from the official link using your browser, save it locally, then add its full path to `.env`:

```dotenv
INSIGHTS_NIFTY500_FILE=C:/Users/YourName/BharatSignal/ind_nifty500list.csv
```

Restart the app. A manual file is labelled user supplied and uses its file modification time; files over seven days old are rejected. Replace it with a fresh official download rather than changing its timestamp. Remove this setting to return to automatic downloads.

## Validation and practical limits

Validation: the Insights regression suite, three scheduler tests, and Vite production build are run before publishing. New tests cover parsing, real-source exceptions, exact mapping, duplicates, unavailable/stale caches, daily master refresh, Intraday isolation, rotation/restart, timeouts, source failures and individual row expiry. Public source mapping is checked separately from authenticated Dhan candle/quote access.

No authenticated live-market or Windows execution test was possible in the development environment. Validate with your Dhan credentials and configured exchange calendar. No new calibrated win rate, perfect entry, guaranteed target, live execution, or profitability claim is made. Existing strategies and their research labels remain in place; historical and paper-trading validation is still required.
