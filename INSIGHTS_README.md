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
- The 5m signal also calculates ADX, VWAP, RSI(14), MACD histogram and EMA20/50 (from licensed Dhan OHLCV) and requires **at least 3 of these 5 confirmations**. Historical score values are NOT estimated predictive probabilities.
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

### Five-minute Index Options and F&O Options refresh (12 November 2026)

After the 09:45 preliminary and 10:00 final research passes, the server
re-evaluates `index-options` and `fo-stocks` on each five-minute IST
boundary from **10:05 until market close**. The per-day scheduler keys ensure
no repeat within one five-minute bucket. A single job lock serializes all
work, and Dhan's option chain is rate limited/cache controlled by the adapter.
The React UI polls API snapshots every ~20 seconds; that UI polling does NOT
trigger additional Dhan scans. When the market is closed or the holiday
calendar is missing, no scheduled scans run.

- Index Options checks only supported NIFTY/BANKNIFTY/SENSEX context with
  current completed index bars, SMC-style price break and 15m/60m alignment;
  index cash OHLCV may legitimately have zero volume, which is *not* evidence
  of weak liquidity. PCR and OI are positioning proxies.
- F&O Options checks at most 10 underlyings from the **locked 10:00 shortlist**;
  it never rescans the broad equity universe on each option refresh.
- Option quote freshness cannot currently be verified and premiums are
  explicitly labelled **HYPOTHETICAL**. Empty qualified lists are normal;
  a missing shortlisted universe is a separate discovery problem.
- To prevent empty lists caused by prematurely stringent watchlist gates,
  early selection now ranks positive- and negative-return stocks with
  available recent OHLCV, reserving room for verified sector-mapped symbols.
  The later five-minute BUY/SELL signal algorithm **still requires** actual
  high-volume structural break, multi-timeframe agreement and indicator gates.
  Discovery diagnostics persist after monitoring, so users can distinguish
  missing 5-minute bars, invalid opening structure and unqualified signals.
- Five-minute scheduling is **best effort**, not exact exchange-timestamp
  streaming. Refresh may finish late when the Dhan API is slow. It does not
  create orders, fills or verified trading recommendations.

To update an existing Windows installation, stop it and back up the folder,
then copy only `insights/service.py`, `insights/advanced_smc.py`,
`insights/tests/test_staged_scheduler.py`, and `web/src/main.js` from
this branch into the same relative paths. Then run both unittest suites
and `cd web && npm run build && cd ..`; restart the server. Never overwrite
the local `.env`, SQLite data, sector map or holiday calendar.

## Swing Trades and Multibagger long-term research tabs

**Swing Trades** uses only Dhan completed daily candles, includes a
21/50 EMA trend-pullback entry, consolidation breakout (>=1.5x prior 50-day
volume, within 15% 52-week high), RSI(14) pullback reclaim, Supertrend(10,3)
flip + EMA alignment, and a separate ADX/volume-filtered EMA21/50 crossover.
Columns: Symbol, Strategy, Entry, Stop, Target 2R, Target 3R, Risk:Reward,
Volume ratio, Trend strength. Entries are *reference daily closes*, not
broker fills or current executable prices. Risk/Reward for the 2R plan is
2.0 by construction; strength and RVOL break ties.

**Multibagger** uses completed Dhan daily candles for 150/200-day averages,
past weekly/monthly EMA20, 52-week price levels, a score with a separate
PASS/FAIL/UNVERIFIED row for every criterion, and optional attributable
fundamental/surveillance/RS-rank files. Its UI has 0–50,000 crore market
cap sliders, default **₹300–₹20,000 crore**, and explicitly shows missing
cap data as UNVERIFIED. Every criterion gives exactly 0 or 1 point; do not
treat the score as a predicted return or success probability.

Mandatory eligibility checks include: NSE/BSE listing and >=365-day listing
history, verified market cap in selected UI range, 63-session typical-price
times volume average > ₹50 lakh per day (a transparent OHLCV approximation),
no ASM/GSM, and no frequent circuit locks. Market-cap sources,
exchange/surveillance flags, and NIFTY 500 relative-strength percentiles
are **not included in standard Dhan OHLCV** and must be supplied with dated
provenance. Missing any of those eligibility checks yields **UNVERIFIED**.
Verified failure yields **BLOCKED**. The tab allows viewing unverified and
blocked rows to see which information is missing. Long-term scanners use a separate NSE/BSE CASH equity selection from the
existing detailed official Dhan master (instead of the F&O-only subset),
subject to the `INSIGHTS_LONGTERM_MAX_SYMBOLS` cap, source coverage,
and any configured watchlist. With the default 80-stock limit this is
**not** an exhaustive NSE/BSE listing survey. The intraday F&O scanner
continues using its original narrow contract-aware master.

**Scheduling and load:** The regular background scanner runs these two
long-term research screens **once after 15:40 IST** on configured exchange
trading dates while the application is running. It does not run on holidays
and does not conflict with five-minute live option monitoring. An additional
`INSIGHTS_LONGTERM_MAX_SYMBOLS` option defaults to **80** and can be set
to a maximum 500 to change off-hours research coverage. This cap does not
change the intraday shortlist. Historical Dhan requests and tests can be
slow; partial/missing API history is reported rather than fabricated.

**Optional local data sources** (all three are paths configured locally
in `.env`, never credentials, and never scraped without permission):

```dotenv
INSIGHTS_LONGTERM_MAX_SYMBOLS=80
INSIGHTS_FUNDAMENTALS_FILE=H:\\BharatSignal_Fusion_Ready\\fundamentals_verified.json
INSIGHTS_SURVEILLANCE_FILE=H:\\BharatSignal_Fusion_Ready\\surveillance_verified.json
INSIGHTS_RS_RANK_FILE=H:\\BharatSignal_Fusion_Ready\\nifty500_rs_verified.json
```

Fundamental record shape (illustrative schema ONLY; `EXAMPLE` is not a real
listed stock or live researched fundamental value):

```json
{
  "asof":"2026-11-12",
  "symbols":{
    "EXAMPLE":{
      "source":"NAME OF YOUR LICENSED FUNDAMENTALS PROVIDER",
      "period_end":"2026-09-30",
      "market_cap_cr":1200,
      "sales_cagr_3y":23,
      "profit_cagr_3y":22,
      "quarter_profit_yoy":30,
      "roce":21,
      "debt_equity":0.25,
      "promoter_holding":54,
      "promoter_pledging":0,
      "operating_cash_flow":100,
      "peg":1.2
    }
  }
}
```

Surveillance record shape (actual values must be checked from exchange notices
and must not be copied from this illustrative example):

```json
{
  "asof":"2026-11-12",
  "symbols":{
    "EXAMPLE":{
      "source":"EXCHANGE NOTICE OR LICENSED PROVIDER",
      "period_end":"2026-11-12",
      "listed_exchange":"NSE",
      "listing_date":"2022-01-01",
      "asm":false,
      "gsm":false,
      "frequent_circuit_locks":false
    }
  }
}
```

NIFTY500 rank shape (requires a verifiable point-in-time ranked universe):

```json
{"asof":"2026-11-12","source":"LICENSED NIFTY500 RS RANK PROVIDER",
 "ranks":{"EXAMPLE":78}}
```

The user must obtain and maintain the underlying datasets. An attractive
technical score alone is not sufficient to mark a stock ELIGIBLE.

**Windows update:** Back up and stop the existing app. Download the development
branch ZIP, extract separately, then copy these files preserving paths:
`insights/service.py`, `insights/api.py`,
`insights/brokers/dhan.py`,
`insights/strategies/swing.py` (new),
`insights/strategies/multibagger.py` (new),
`insights/tests/test_longterm_research.py` (new),
`web/src/main.js`, `web/src/styles.css`.
Keep `.env`, historical databases, holiday and sector files intact.
Run `python -m unittest discover -s insights\\tests -q`
using the application venv and `npm run build` inside `web`. Both tabs
are GET-only and require no OpenAlgo key. Never enable broker orders.

## Exact Intraday daily + 15m momentum query and AI-ready top 10 (November 2026)

A new `insights/strategies/momentum_query.py` implementation replaces the old
mandatory 5m SMC/BOS/sector gates for the Intraday **BUY** and **SELL** tabs.
All **eight daily criteria** and **three 15m criteria** requested by the user
must pass, using available **completed** 5m and 15m Dhan equity candles:

- BUY daily: latest close > prior completed daily high; > today's session open;
  > prior close ×1.01; current session cumulative volume > 1.5 × *latest*
  20-day volume SMA; close > latest 20-day close SMA; daily RSI14>60;
  close>₹100; latest daily volume SMA20>500,000 shares.
- SELL daily: close < previous completed daily low; < today session open;
  < prior close ×0.99; same high-volume, price and 20-day volume filters;
  close < latest 20-day close SMA; daily RSI14<40.
- BUY 15m: last **completed** 15m close>EMA20, RSI14>60, and last
  15m volume > 2× 20-bar 15m volume SMA. SELL mirrors all three conditions.
- The current trading day's daily close, open, and *cumulative* volume are
  built from all completed 5-minute candles since 09:15; the daily RSI and
  20-day SMAs include that **PROVISIONAL current session** alongside prior
  closed daily bars. These are not completed daily candles, may change
  throughout the day, and are not a live order execution claim.
- Per-stock prior completed daily bars are cached for the session. The live
  five-minute scanner revisits only the fixed 10:00 shortlist. At the first
  two discovery passes, ranking does NOT demand all 11 query gates; only the
  second-stage live signal scan does. Missing history and stale data fail
  closed. Signals may be zero.

An additional `insights/ai_rank.py` module now ranks up to TEN qualifying
intraday setups **across both directions**. The ranking gives transparent
weighted points for current-day/15m relative volume, directional RSI
strength, consistency of recent completed 5m closes, and initial stop risk.
This is a deterministic *AI-ready evidence score*, **NOT trained machine
learning**, NOT a calibrated chance of winning, and NOT validated for
profitability. A model can replace it only after point-in-time, cost-aware
walk-forward training and calibration.

Entry is a **conditional trigger** beyond the most recent completed 5m
candle's high (BUY) or low (SELL), with an ATR buffer; it is *not a filled
transaction or a guaranteed entry*. The 3-bar structure stop has at least
0.8× 5m ATR clearance. Risk outside the **0.3%–2%** initial-stop band is
rejected instead of manipulating the stop to force the trade. Reference
targets are 1.5R and 2.5R based on that valid stop distance, not promises
of achievable exit prices. Only qualifying setups are returned, never forced
to a count of ten. Read-only Dhan mode remains unchanged.

The Intraday page now contains an **AI-ready top 10** table above the
existing BUY/SELL tabs showing symbol, direction, evidence rank, entry
trigger, structure/ATR stop, T1, T2, risk percent and daily/15m volume ratios.
Scores and rule conditions are explained on the detailed signal cards.

**Windows upgrade:** Back up the project and stop START_INSIGHTS.bat.
Download the development branch ZIP, extract into a separate folder and copy:
- `insights/service.py` (updated)
- `insights/strategies/momentum_query.py` (new)
- `insights/ai_rank.py` (new)
- `insights/tests/test_ai_intraday.py` (new)
- `insights/tests/test_diagnostics.py` (updated)
- `insights/tests/test_scanner_quality.py` (updated)
- `insights/tests/test_staged_scanners.py` (updated)
- `web/src/main.js` (updated)

Do not copy or overwrite local `.env`, exchange holiday files, SQLite
database, token, or local watchlists. Run BOTH Python unittest suites and
`npm run build` in `web`. The new code and scores still need a real
Windows test run and independent historical strategy validation.
