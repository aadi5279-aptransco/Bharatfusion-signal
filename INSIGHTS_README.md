# BharatSignal Fusion — Market Insights (additive research edition)

**Status:** Locally runnable Flask + React research UI, **not** an OpenAlgo code fork. All original Tkinter files remain intact; use `START.bat` for the legacy desktop UI or `START_INSIGHTS.bat` for the new web UI. No OpenAlgo source was copied. Vendored Kronos files retain their upstream attribution/license.

## First-time Windows setup

1. Install **Python 3.11** and **Node.js LTS**. Unzip the delivered archive into a new folder (do not overwrite your original installation).
2. Run `INSTALL_INSIGHTS.bat`. This creates `.venv`, installs the official `dhanhq` library, builds React locally, and runs the old and new test suites. Internet access is required for initial package installation.
3. Open `.env` (created from `.env.example`) and set `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN`. Do **not** paste these into GitHub. `.env` is intentionally gitignored. Note that a plain `.env` file is **not encrypted at rest**: restrict Windows user permissions and use OS credential storage if encrypted secret persistence is required. Credentials are never exposed to React.
4. Obtain and validate a current **exchange holiday calendar** yourself, copy `insights_holidays.example.json` to a local file, populate verified holiday dates (including any special market holidays), and set `INSIGHTS_HOLIDAY_FILE` to its full path. Without this, scheduled scans are blocked. Check exchange notices for special sessions as well; ordinary market hours are assumed.
5. For relative-strength intraday scans, verify and edit `insights_sector_map.example.json`, then set `INSIGHTS_SECTOR_MAP_FILE` in `.env` to its full path. Only symbols represented in the official Dhan instrument master are scanned.
6. Optional: provide **licensed, dated** delivery data for BTST via `INSIGHTS_LICENSED_DELIVERY_FILE` referencing JSON of the form `{"date":"YYYY-MM-DD","values":{"SYMBOL":48.2}}`; also needs 20 prior completed sessions' matched-time intraday volume, obtained from Dhan. No delivery data is scraped.
7. Run `START_INSIGHTS.bat`, then open **http://127.0.0.1:8765**. Keep the console running. The Flask API binds only to `127.0.0.1`.

The UI polls `/api/v1` for cached results. Scheduled scans run at/after **09:20**, **10:00**, **15:00** IST, plus dashboard refresh on five-minute clock boundaries, only within configured trading sessions. Scans may finish late if Dhan is slow; no jobs overlap. The UI shows last refresh and unavailable states. Automatic scan operation requires a running PC with internet and valid Dhan entitlements.

## Manual market-data refresh (November 2026 update)

The Dashboard has a **Refresh Market Data** action. Clicking it submits a local-only
`POST /api/v1/market-insights/dashboard/refresh` request and returns immediately.
The background worker fetches completed Dhan 5-minute candles for the mapped index and
sector symbols. It will use the latest Dhan trading session if the market is closed.
The UI displays **HISTORICAL SNAPSHOT — NOT LIVE**, the source session date, the
last completed candle timestamp in IST, and the time of the fetch. It never invents
intraday data or treats historical bias as a live entry signal.

The request is restricted to the local Flask server (127.0.0.1), serialized with
other scheduled scans, and accepts at most one request per 45 seconds. A refresh does
not run strategy scans, record paper trades, or place orders. Dhan data entitlement
and a valid unexpired token are still required. A backend health check exposes
`manual_refresh.status` and errors without leaking credentials. API responses
may remain stale if Dhan data is unavailable or a symbol is unsupported.

To upgrade an already installed Windows copy while preserving local credentials:
1. Stop `START_INSIGHTS.bat` with Ctrl+C and back up the local project.
2. Download this development branch from GitHub and extract it into a separate folder.
3. Copy only these files from the extracted tree into the matching paths of your installed
   project: `insights/service.py`, `insights/api.py`, `insights/tests/test_service.py`,
   `web/src/main.js`, and `web/src/styles.css`.
4. From the installed project folder, run:
   `cd web && npm run build && cd ..`
   followed by
   `.venv\\Scripts\\python.exe -m unittest discover -s insights\\tests -v`.
5. Run `START_INSIGHTS.bat` and check the Dashboard.
Never overwrite `.env`, `insights_holidays.json`, your local sector map,
or any local database when applying an update.

## Live Scanner Reliability Stage — 11 November 2026

Development update on the existing additive, read-only Market Insights module:
- The default 30-stock selection prioritizes names in the user-verified sector map; otherwise the old alphabetical first 30 provided little coverage. A manually specified watchlist filters by the provided symbols rather than using automatic sector priority.
- Intraday is gated to 10:15 IST (four complete 15-minute intervals); all its underlying and NIFTY/sector five-minute candles must belong to the current session and be completed and sufficiently recent. No stale/holiday setups.
- F&O futures OI analysis requires a recent completed current-session 15-minute candle.
- Index Options use the current-session, recent index context. Unverified premium quotes remain **hypothetical research** and are no longer written to the observed-trade journal.
- Scan result counts distinguish data assessed, missing/stale sectors, stale cash candles, missing Dhan inputs, and candidates failing rules.
- The user-facing cards explicitly call out freshness and option premium restrictions. Dhan credentials, order placement disabled, holiday calendars, original UI, and SQLite records are retained.

**IMPORTANT: The absence of a fresh Dhan option-chain quote timestamp means option levels cannot be treated as executable.** This stage does not independently backtest strategy returns or validate option quotes; live tests remain necessary. The Dhan option adapter's nested response fix is a prerequisite.

Windows update (existing installation; no Git required):
1. Stop START_INSIGHTS.bat with Ctrl+C.
2. Back up the *entire existing installation folder*, including any local-only settings and snapshots.
3. From GitHub download the feature/market-insights-web-20261109 branch ZIP; extract into Downloads as a *separate source folder*.
4. Copy ONLY: insights/scanner_quality.py, insights/service.py, insights/strategies/equity.py, insights/tests/test_scanner_quality.py, insights/tests/test_diagnostics.py, web/src/main.js, web/src/styles.css into corresponding installed application subfolders.
5. In the installed application root: .venv\\Scripts\\python.exe -m unittest discover -s tests -q
6. Then: .venv\\Scripts\\python.exe -m unittest discover -s insights\\tests -q
7. Then: cd web && npm run build && cd ..
8. START_INSIGHTS.bat; check /api/v1/health, /api/v1/market-insights/intraday, /index-options and /fo-stocks after 10:15 IST on an exchange-open day.

If a test/build fails, do not continue to live testing. Restore from backup or investigate the failure. Never copy downloaded .env example over the live .env; never share tokens. No automatic order placement occurs.

## Tabs

- **Dashboard:** NIFTY/SENSEX rule score: EMA20/50/200, ADX, VWAP and 20-candle structure. India VIX and FII/DII are explicitly unavailable unless separately licensed. Sector change and strength relative to NIFTY, computed from Dhan sector-index candles.
- **Analyse:** Search by exact Dhan-mapped symbol, or `NIFTY 25000 CE`. Select expiry (optional). PCR, max pain, OI support/resistance, OI changes and strike OI chart derive from the licensed Dhan option-chain response. Historical IV percentile is unavailable without stored IV history. Option premium plan is a **research scenario**, with quote-age warnings.
- **Intraday:** 09:45 preliminary discovery, 10:00 final shortlist, then 5-minute shortlist-only monitoring, 5-minute ORB + VWAP + relative volume + ADX + NIFTY and sector strength. Requires sector map and completed candles. Outputs underlying cash entry, stop, T1, T2. Backtest unvalidated means **research only**.
- **BTST:** Scheduled at 15:00 IST. No signal if licensed delivery %, prior 20-session matched-time 15:00 volume, or sector history is absent.
- **Index Options:** NIFTY, BANKNIFTY, SENSEX CE/PE determined from index direction and OI. Premium levels are hypothetical until premium history and freshness are validated; expiry-day/high-IV warnings are shown. NSE and BSE indices require correctly mapped Dhan security IDs and segments.
- **F&O Stocks:** Futures price/OI buildup and real option-chain premium scenario; blocks if futures OI is missing. **No invented option premium**.
- **Track Record:** Immutable SQLite signal observations with separate observed T1/SL/expiry statuses. A bar touching both SL and T1 is counted as SL (conservative). Not executed fills. The observed win rate does not claim trading profitability.

## Backend APIs

`GET /api/v1/health`, `GET /api/v1/market-insights/dashboard`, `/intraday`, `/btst`, `/index-options`, `/fo-stocks`, `/analyse?symbol=NIFTY`, `/track-record`, `/backtests`, `/status`.

No API accepts order-placement requests. `ENABLE_ORDER_PLACEMENT=true` causes startup to **fail closed**. This app does not contain broker order functions.

## Validation

`python -m unittest discover -s tests -v`

`python -m unittest discover -s insights/tests -v`

For a preliminary historical Dhan replay: `python -m insights.validate --strategy intraday --symbol RELIANCE --sector Energy`. This is **not a production-ready walk-forward backtest**; its results are explicitly marked ineligible pending point-in-time out-of-sample evaluation. BTST and options remain disabled until licensed historical data exists. Missing/expired credentials or holiday coverage cause visible no-data states, not fake signals.

## Adding a strategy

Create `insights/strategies/my_strategy.py` with a stable `NAME`, `VERSION`, and a **pure** function accepting completed Dhan candles and time-aware context. Return `None` when inputs/gates are missing; otherwise return a dict with `strategy, version, symbol, direction, signal_at, entry, sl, t1, t2, rr, confidence, reasons`. Levels must derive from deterministic rules. Add unit tests, validate historical price/option data, update the service scheduler, persist through `Journal.record`, and keep the output research-only until independent backtest passes.

## Security and limitations

- Do **not** commit `.env`, passwords, CSV exports, credentials or databases.
- Token renewal is attempted only for active, eligible Dhan-Web tokens when `DHAN_WEB_GENERATED_TOKEN=true`. Other cases require manual secure reauthentication. Refresh tokens remain in memory only. <https://dhanhq.co/docs/v2/authentication/>
- Option chains are globally throttled to **one request per 3.1 seconds** and cached; this is stricter than Dhan's documented unique-request limit. <https://dhanhq.co/docs/v2/option-chain/>
- The new API uses Dhan only. The legacy app still contains historical workflows involving external public pages and risk reports; those original code paths are not rewritten or silently enabled in this new service.
- The React app uses `lightweight-charts` for OI strike charts. A premium/candlestick price chart requires separately licensed time-series OHLC and is not depicted without it.
- This is a research release, **not yet authenticated against your Dhan account or tested visually on Windows**. No claim of profitability, win rate or guaranteed scan timing is made.

## Advanced SMC / MTF staged scanner — November 2026 development branch

New architecture, still **read-only research**, with no guaranteed win rate:
- At or after **09:45 IST**, Dhan Market Quote batches up to 500 eligible NSE F&O cash underlyings and returns session return/volume. The configured `INSIGHTS_MAX_SYMBOLS` (default 30) limits **deep 5-minute candle analysis** to the strongest positive and negative quote candidates. If quote API is unavailable, the app clearly labels a limited configured-universe fallback. Session-to-date quote volume is NOT relative volume.
- Preliminary lists require real 5-minute opening-range/structure breaks with >=1.5x trailing 20-candle volume. These are **watch candidates, not trades**.
- At or after **10:00 IST**, repeat that deep selection once and lock at most eight top bullish plus eight bearish stocks for the day. If the server starts after 10:00, skip the missed preliminary pass; don't double-scan.
- From **10:05 IST** on five-minute boundaries, monitor only the locked stocks. Actual research BUY/SELL signals require >=2.0x 5m volume, the 09:15/09:20/09:25 opening range, 20-bar BOS/price structure break, EMA9/21 trend, 15m + 60m trend alignment, and NIFTY/verified-sector relative return confirmation. CHoCH, three-candle FVG and sweep flags are stated as **range-based SMC proxies**.
- `Intraday` contains two internal tabs: **Breakout BUY** and **Breakdown SELL**, each with qualifying signals and separately labeled non-executable preliminary ranking.
- Dhan Market Quote's five-level resting bid/ask quantities are sampled in one batch for the shortlist when available. A quote's *last_trade_time* must be verified recent; otherwise the depth ratio is **unavailable**. Resting depth is not market-order aggressor volume, footprint delta, absorption or evidence of a specific institution.
- Index Options require current completed index 5m structure+volume and 15m/60m directional alignment plus option-chain OI/PCR. F&O Stocks use only the shortlisted underlyings, current 5m structure, 15m/60m trend, actual futures OI build-up and chain metrics.
- Option premium entry/SL/T1/T2 remain **HYPOTHETICAL, quote age unverified**; they are not recorded as actual executions or observed trades.
- BTST uses only the locked shortlist and requires verified 15m/60m, prior daily + **completed weekly** bullish trends, historical matched-time volume and user-provided, dated licensed delivery data. Missing delivery or timeframes block a signal rather than inventing data.
- **Important:** Results are only among the configured/deep-filtered universe, NOT a guarantee to identify every winner among all listed stocks. Only five sector mappings are currently configured in the user's installation; many otherwise strong stocks cannot pass sector-relative confirmation until an accurate sector map is expanded. Scan targets at 09:45/10:00 are *not* timing guarantees, especially on slow networks.
- Live order placement is still completely disabled.

### Update on existing Windows H:\\ installation

1. Stop `START_INSIGHTS.bat` and copy the existing `BharatSignal_Fusion_Insights` folder as backup.
2. Download this development branch as ZIP from GitHub; extract in Downloads **separately** from your installation.
3. Copy ONLY these updated/new source files, preserving paths:
   - `insights/advanced_smc.py` **new**
   - `insights/service.py`
   - `insights/brokers/dhan.py`
   - `web/src/main.js`
   - `web/src/styles.css`
   - `insights/tests/test_advanced_smc.py` **new**
   - `insights/tests/test_staged_scanners.py` **new**
   - `insights/tests/test_staged_scheduler.py` **new**
4. From the installed project root:
   ```cmd
   .venv\\Scripts\\python.exe -m unittest discover -s tests -q
   .venv\\Scripts\\python.exe -m unittest discover -s insights\\tests -q
   cd web
   npm run build
   cd ..
   START_INSIGHTS.bat
   ```
5. Visit `http://127.0.0.1:8765`, then `/api/v1/health` and `/api/v1/market-insights/intraday` on a market-open day. Inspect `preview_buy`, `preview_sell`, `shortlist_finalized`, `shortlist_symbols`, `buy_signals`, `sell_signals`, `breadth_quotes`, and `discovery_mode`.

Never overwrite `.env`, `insights_holidays.json`, `insights_sector_map.json`, or SQLite data. Rebuild React after copying source; do not edit `web/dist` by hand. Python and React changes need Windows test verification; this development version is not declared profitable or production-ready.
