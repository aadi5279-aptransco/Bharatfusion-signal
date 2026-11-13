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

## Additional Fib + SMC + OI option research setups (12 November 2026)

Two additional **separately labeled** studies appear in both **Index Options**
and **F&O Stocks**, alongside and *without modifying* the existing
trend/OI-based research candidate list. These studies are checked by the
already-scheduled 5-minute refreshes after 10:00. The 9:45 study can be
evaluated as soon as two subsequent 5-minute candles have closed (earliest
09:55). The 12:45 study cannot form until the 12:45–13:15 reference candle
is **fully complete**, with earliest two-post-close confirmation around
13:25. Exact verification depends on fresh Dhan data.

### 9:45 opening range
- Six SPOT five-minute candles from **09:15–09:45** construct range HIGH (1)
  and LOW (0). Fib levels are **0, 0.44, 0.5, 1**; the 0.44–0.5 band is
  explicitly no-trade.
- Two completed five-minute closes above 0.5 give a provisional bullish
  bias; two closes below 0.44 give a provisional bearish bias.
- Observable sweep/BOS/CHoCH-style evidence, a retrace/retest into a previously
  formed three-candle imbalance (FVG) or last opposite candle (order-block
  proxy), and a directionally confirming close are **all** required for
  `STRUCTURE_READY`. SMC labels are objective price-range *proxies*, not
  evidence of actual institutional positioning.
- Spot entry is the five-minute close after the pullback/retest; spot stop
  is outside the identified order block or gap invalidation. The opening
  range high/low becomes the preferred first target if still ahead of price;
  otherwise the first target uses 1.5R; the second uses 2R. This is a
  SPOT-price research scenario only, never an option premium plan.

### 12:45–13:15 thirty-minute candle
- The 12:45 reference is assembled from **exactly 6 completed SPOT 5m bars**
  (12:45, 12:50, 12:55, 13:00, 13:05, 13:10) to prevent fetching a
  misaligned/incomplete 30m candle. The fib is always **low=0, high=1**,
  regardless of green/red candle color.
- If green: bullish sustain >0.5, bearish sustain <0, and 0–0.5 no-trade.
- If red: bullish sustain >1, bearish sustain <0.44, and 0.44–1 no-trade.
  Both require two subsequent completed 5m closes and SMC retest evidence.
- Watch for wicks across the 30m extremes; one wick alone cannot confirm a
  reversal. The study uses price-based sweep/BOS/CHoCH/FVG/OB *proxies*.

### OI validation
- OI-based classification compares the current Dhan option-chain OI against
  any actually provided `previous_oi` values for the nearest five strikes,
  and compares total PCR with its previous-OI baseline. It is NOT a live
  five-minute PCR *time series* and never claims one.
- The confirming side also requires **actual separate completed 15m futures
  OI candles**: CE requires rising futures price and OI; PE requires falling
  futures price and rising OI. For indices, the nearest FUTIDX is matched
  by exact Dhan master underlying instrument ID, never guessed by name.
- If the chain/futures is missing, inconsistent or contrary, the study is
  **WATCH_ONLY** or **SKIP**, not an OI-confirmed signal.
- The final `OI_CONFIRMED_SPOT_RESEARCH` label does NOT verify executable
  option quote freshness, payoff, order book, fills, performance or win rate.
  Actual CE/PE premium entry, stops and target levels remain **unverified**.
- Stock-option studies use only the finalized 10:00 stock shortlist (up to
  ten names) and never perform additional full-universe discovery every five
  minutes. Index-option studies use only the mapped major index SPOT feeds.
- The UI exposes fib levels, structure status, spot-only reference levels,
  no-trade reasons, near-strike OI and futures evidence separately from the
  existing option strategy signals.

**Files to update on an existing Windows installation:** from the GitHub
development branch, preserve their relative paths:
- `insights/strategies/fib_smc.py` (new)
- `insights/strategies/fib_oi.py` (new)
- `insights/tests/test_fib_smc_options.py` (new)
- `insights/service.py` (updated)
- `insights/brokers/dhan.py` (updated)
- `web/src/main.js` (updated)

Stop and back up BharatSignal Fusion first. Never overwrite `.env`,
SQLite databases or calendar/configuration. After copying, run
`.venv\\Scripts\\python.exe -m unittest discover -s tests -q`
and `.venv\\Scripts\\python.exe -m unittest discover -s insights\\tests -q`,
then `cd web && npm run build && cd ..`. Do not claim the new strategies
are live-validated or profitable until they pass independent backtests
with actual historical quote ages, slippage and costs.

### NIFTY extra 18:15 spot candle — session validation (12 November 2026)

The official Dhan NIFTY index feed returned **76** 5-minute records on
2026-11-12: the valid cash spot sequence **09:15–15:25 IST** (75 bars)
plus one anomalous **18:15 IST** bar. Do **not** globally shift timestamps:
the first 75 bars are correctly aligned.

The Dhan adapter now filters only **IDX_I, NSE_EQ and BSE_EQ** intraday
spot/cash candles to the regular IST 09:15–15:30 session window and to
the interval-specific 09:15 candle-start grid. These records are excluded
BEFORE being cached or supplied to charts, Fib reference ranges, opening
range, RSI, SMC or live research scans. Futures and options histories
retain their original timestamps (other session hours or special sessions
require an explicit exchange-calendar validation policy).

Read-only preflight now reports `out_of_session_discarded` and
`session_check` alongside each candle probe. On a historical NIFTY 5m
probe covering 2026-11-12, expect 75 regular-session candles and
`out_of_session_discarded: 1`. The actual returned total can include
multiple days; the 75 figure refers to the **one session** only.
No source Dhan payload or local credentials are modified.

Deployment: copy `insights/brokers/dhan.py`,
`insights/diagnostics.py` and the new
`insights/tests/test_spot_session_filter.py` from the development branch
into your backed-up application, then run the 5 new session-filter tests,
both unittest suites, and the preflight. React is unchanged.

#### Follow-up: mixed IST offset regression fix

The first offline test fixture joined a `ZoneInfo('Asia/Kolkata')`
`DatetimeIndex` with a fixed-offset `+05:30` index. Some pandas
versions yield a generic `Index`, causing `AttributeError` on
`tz_convert`. Both fixture and adapter are corrected:

- The test explicitly converts the anomalous 18:15 bar into the same
  `Asia/Kolkata` timezone before appending.
- The read-only cash/index adapter can safely normalize an index of
  wholly timezone-aware pandas Timestamps to a uniform IST DatetimeIndex.
  Naive timestamps fail closed and can never be silently relabeled.
- Added two regression tests. Expect **7 tests** from
  `insights.tests.test_spot_session_filter`, then both full test suites.

Upgrade only `insights/brokers/dhan.py` and
`insights/tests/test_spot_session_filter.py` from this branch.
No React build, Dhan token, .env or order setting changes are needed.

## Analyse top gainers/losers, MTF bias and Gann/time/wave evidence — November 2026

**Analyse selections**: `GET /api/v1/market-insights/analyse/choices`
returns the app's mapped indices plus up to 15 gainers and 15 losers in
a single Dhan Market Quote batch, cached for 60 seconds. Previous-session
close is the return baseline where the source provides Dhan quote
`ohlc.close`; otherwise the record explicitly labels `SESSION_OPEN`.
This is not a complete NSE/BSE gainer/loser universe. Outside market
hours the ranking is marked stale.

Cash/index **Analyse** no longer fails simply because a stock has no
listed F&O chain. The analyser first retrieves recent completed 5m, 15m,
60m cash/spot OHLCV and conditionally evaluates direction/entry levels.
Expiry/option-chain metrics and resting-depth snapshots are optional
additional evidence, not unverified substitutes for executed trade flow.
`insights/analyse_engine.py` returns a bullish/bearish research tilt
only on fully aligned 20/50 EMA three-timeframe trend; a conditional
entry plan additionally needs a 20-bar breakout and a structure/ATR
protective stop within 0.2%–3.0%. Research targets use 1.5R and 2.5R,
with spot/cash prices **not option premium fills**.

**No imaginary win probability:** `probability_of_win: null` and a
corresponding `probability_status` remain until an eligible, timestamped,
cost-aware walk-forward validation/calibration pipeline is supplied.
A 0–100 heuristic score is not a predictive probability.

**Gann/time/confirmed-wave independent layer**:
`insights/cycle_wave.py` evaluates square-root increment support and
resistance, 30/45/60/90/120/180-minute offsets relative to the 09:15
IST regular-session anchor, and *confirmed* local price swing pivots.
It is appended (not used to silently add gates) to **Intraday**, **Index
Options**, **F&O Stocks**, and to the existing Fib research setup
panels. It does NOT claim a validated Elliott 1-5/A-B-C count,
forecasted reversal, institutional execution, or improved profitability.
Absent/incomplete candles yield `UNAVAILABLE`.

### Safe Windows update
Back up and stop the current application first. Extract the current
development branch ZIP elsewhere and copy ONLY:
- `insights/cycle_wave.py` (new)
- `insights/analyse_engine.py` (new)
- `insights/analyse_workflow.py` (new)
- `insights/tests/test_analyse_gann_wave.py` (new)
- `insights/service.py` (updated)
- `insights/api.py` (updated)
- `insights/brokers/dhan.py` (updated)
- `web/src/main.js` (updated)
- `web/src/styles.css` (updated)

Do not replace `.env`, holiday calendar, sector maps or SQLite
data. Run both Python unittest suites, then `cd web && npm run build`
and restart `START_INSIGHTS.bat`. Inspect
`/api/v1/market-insights/analyse/choices` and a selected cash/index
`/api/v1/market-insights/analyse?symbol=NIFTY`.
The new changes require Windows test and live Dhan verification.

## Swing Trades additional daily/weekly Gann + time-cycle + swing-wave layer

Swing Trades, previously using the existing daily EMA/ADX/RSI/Supertrend/
breakout logic, now attaches a separate **completed daily and weekly**
evidence object to each *already qualified* swing candidate.

- **Gann price:** square-root-of-price steps anchored to the latest
  *confirmed daily pivot*; shows nearby mathematical support/resistance.
- **Swing time windows:** 20, 30, 45, 60, 90, 120 completed trading
  sessions from the last confirmed daily swing; 4, 8, 13, 21, 34
  completed weekly bars from the last confirmed weekly swing.
  This is not the intraday 09:15 clock cycle methodology.
- **Wave structure:** separately classifies confirmed daily and
  weekly higher highs/lows as RISING SWINGS, FALLING SWINGS,
  MIXED/CORRECTIVE or UNDETERMINED. Elliott counts are explicitly
  UNVERIFIED, not fabricated.
- **Fail-closed weekly:** an unfinished calendar week is dropped;
  the Friday week is considered complete only after 15:40 IST.
  The current daily candle is likewise excluded until 15:40.
- Original scan qualifiers, candidate ranking, entry, stop,
  2R and 3R targets are **unchanged**. The layer cannot insert a
  new trade, alter risk or claim an increased win probability.
- The UI adds support, resistance, daily/weekly wave geometry
  and near-cycle columns to the existing Swing Trades table.

Files for existing Windows deployment:
`insights/swing_gann_wave.py` (new),
`insights/tests/test_swing_gann_wave.py` (new),
`insights/service.py` (updated),
`web/src/main.js` (updated).

Stop and back up the application, copy those four paths, run
`.venv\\Scripts\\python.exe -m unittest insights.tests.test_swing_gann_wave -v`,
both full Python unit test suites, `cd web && npm run build`,
restart `START_INSIGHTS.bat` and verify Swing Trades.
The daily long-term scan remains scheduled only at 15:40 IST
or later on an eligible exchange day.

## New pre-market 08:00 stock watchlist and independent opening Fib option watches

### Pre-Market 8 AM tab
- Uses the **previous fully completed Dhan daily candles only**;
  it does not claim access to 8:00 AM cash/index prices when the
  exchange has not opened.
- The source is the mapped **F&O stock universe**, limited by
  `INSIGHTS_PREMARKET_MAX_SYMBOLS` (default 220, capped at 250).
  Coverage and unavailable/short history counts are displayed.
  It does **not** claim whole-NSE/BSE coverage.
- Displays the strongest 10 previous-day gainers and 10 losers (if
  eligible data exists), a separate 20-session **close** breakout/breakdown
  flag, prior-session relative volume, EMA20/EMA50 direction and an
  explanatory *heuristic watch score* (not win probability).
- On a configured market morning, scheduler builds/uses this watchlist
  starting **08:00 IST**. If the app stayed running after the previous
  close, the 15:40+ long-term scan also prepares an atomic local
  `premarket_watch.json` cache from that completed session, so it can
  be loaded immediately after next startup. The cache is accepted at
  8 AM **only** if its session date matches the last eligible trading
  day from the configured exchange calendar. If the app was off or
  Dhan access failed, the tab may show unavailable rather than
  fabricate candidates; the app cannot execute with the computer off.
- Previous-day gainers/losers are watchlist candidates, **NOT** guaranteed
  next-session BUY/SELL calls. Actual first candle and redbar
  direction requires fresh completed same-session 5m candles.
- Legacy 09:45/10:00 shortlist and all 11 strict daily/15m signal rules
  remain independently available and unchanged.

### Index Options and F&O Stocks — new directional watches
Both tabs now independently show **two additional** 5m price-structure
watches separate from legacy strict SMC/Futures-OI signals and the old
09:45/12:45 Fib studies.

**First 5-minute opening candle**: use spot index/cash 09:15–09:20
bar. Low = Fibonacci 0; high = 1. Two subsequent *completed* 5m
closes above 1 produce a **CE spot-direction watch**; two closes
below 0 produce a **PE spot-direction watch**. The first possible
confirmation is ~09:30 IST. One wick cannot qualify.

**First red bar**: explicitly ignore the 09:15 opening candle and find
the first subsequent 5-minute candle with `close < open`. Set Fib
**0 = that red bar HIGH and 1 = LOW** (descending orientation).
0.44 is then the **upper** price line, 0.56 the **lower** line.
Two completed 5m closes above 0.44 create a CE direction watch;
two below 0.56 a PE direction watch. The 0.44–0.56 price band
is NO TRADE. Before a red candle or two confirmation bars exist,
the UI says WAITING; if there is no sustained break it says
NO_TRADE. Both trigger prices and the selected reference candle
appear on a 5m underlying spot/cash chart.

For watches passing the 2-close rule, illustrative **underlying**
stop is the reference opposite extreme; 1.5R and 2.5R
targets are displayed only when the stop direction is valid and
within a 6% safety guard. These are NOT option premium levels or fills.
Only then does the app optionally look up the nearest Dhan
ATM option contract and prior/current OI evidence, with expiry,
strike, security ID and **unverified quote age** explicitly labelled.
OI missing/contradictory must not suppress the observed spot watch,
but no premium-level trade can be called validated without a
fresh contract quote, transaction costs and market backtesting.

The Index Options scans operate independently from dashboard bias.
The F&O Stock option direction scanner now checks a bounded
**balanced** sample of morning premarket movers, the 10:00 shortlist
and configured F&O underlyings even if strict legacy signals are
empty; it does not re-scan all equities every five minutes.
Actual order execution remains permanently disabled.

### Installation for an existing Windows app
Stop and back up the program; copy these files from the development
branch preserving the indicated project paths:

- NEW `insights/strategies/opening_redbar.py`
- NEW `insights/strategies/premarket.py`
- NEW `insights/tests/test_opening_redbar.py`
- NEW `insights/tests/test_premarket_8am.py`
- UPDATED `insights/tests/test_staged_scheduler.py`
- UPDATED `insights/service.py`
- UPDATED `insights/api.py`
- UPDATED `web/src/main.js`
- UPDATED `web/src/styles.css`

Never overwrite `.env`, Dhan credentials, calendar files,
SQLite journals or other local databases. Commands:

```bat
cd /d "H:\\BharatSignal_Fusion_Ready\\BharatSignal_Fusion_Insights"
.venv\\Scripts\\python.exe -m unittest insights.tests.test_opening_redbar -v
.venv\\Scripts\\python.exe -m unittest insights.tests.test_premarket_8am -v
.venv\\Scripts\\python.exe -m unittest discover -s tests -q
.venv\\Scripts\\python.exe -m unittest discover -s insights\\tests -q
cd web
npm run build
cd ..
START_INSIGHTS.bat
```

Check local endpoints:
- `GET /api/v1/market-insights/pre-market`
- `GET /api/v1/market-insights/index-options`:
  `opening_setups`, `opening_ready`
- `GET /api/v1/market-insights/fo-stocks`: same two fields.

Check `previous_session`, coverage counts and each candidate's
`state`. Do not interpret historical watchlists as current
trades. Source changes must still pass the Windows tests/build and
live Dhan validation; do not assume predictive accuracy.

## Analyse upgrade — top 20 each, manual F&O symbols and ATM CE/PE research

The existing **Analyse** tab now shows **up to 20 top gainers and up to
20 top losers**, plus all mapped indices. This extends the quote
selection window from 15 to 20 on each side without inventing ranked
securities when Dhan quote coverage is incomplete. At market close the
quote list is flagged stale. A new browser autocomplete provides the
current F&O stock names/tickers from the mapped Dhan instrument master;
manual text entry still works. `InsightsService._lookup` also resolves
an exact F&O futures root from Dhan's real mapped symbol, rather than
guessing from company names.

The new `insights/atm_recommendation.py` always attempts to identify
the **nearest listed ATM strike** using the actual Dhan option chain
and its reported underlying last_price (or a current-session completed
5m close if the chain lacks it). It shows an independent selection
status when spot data, expiry, contract ID, bid/ask or direction is
unavailable. No arbitrary ATM strike is fabricated.

A bullish 5/15/60 breakout may suggest an **ATM CE** study, and a
bearish counterpart an **ATM PE** study. Alternatively, a single
unambiguous first-5m/red-bar two-completed-close setup can provide a
directional watch when multi-timeframe history is missing. Conflicting
or absent direction is **WATCH — NO CLEAR CE/PE BIAS**.
A manually requested PE/CE contradicting the price confirmation is
marked **MANUAL CE/PE UNCONFIRMED**, without quote-derived targets.

When a mapped ATM CE/PE contract has a security ID, positive bid/ask,
reported trade volume and spread <= 5%, the read-only ATM panel can
show hypothetical **option PREMIUM** entry = Dhan best ask,
stop loss = ask - 20% of the ask (or bid/ask spread, whichever larger),
T1 = entry + 1.5R and T2 = entry + 2.5R.
These are **ILLUSTRATIVE**, *not live executable entries*. Dhan's chain
does not independently verify a contract leg's exchange quote
timestamp. At market close the plan is explicitly marked HISTORICAL.
Historical win probability remains unavailable; option buyers face
theta, IV, spreads, slippage and costs. This feature does **not**
place broker orders or modify any original strategy gates.
The existing legacy OI/PCR option study remains separately visible.

### Windows deployment files
- NEW `insights/atm_recommendation.py`
- NEW `insights/tests/test_analyse_atm.py` (9 synthetic regression tests)
- UPDATED `insights/analyse_workflow.py`
- UPDATED `insights/service.py`
- UPDATED `web/src/main.js`

Stop and back up the local app first. Copy only these changed files
from branch `feature/market-insights-web-20261109`. Do not overwrite
the .env file, Dhan credentials, databases or calendars.

```bat
cd /d "H:\\BharatSignal_Fusion_Ready\\BharatSignal_Fusion_Insights"
.venv\\Scripts\\python.exe -m unittest insights.tests.test_analyse_atm -v
.venv\\Scripts\\python.exe -m unittest insights.tests.test_analyse_gann_wave -v
.venv\\Scripts\\python.exe -m unittest discover -s tests -q
.venv\\Scripts\\python.exe -m unittest discover -s insights\\tests -q
cd web
npm run build
cd ..
START_INSIGHTS.bat
```

UI: open Analyse, inspect 20+20 available quote movers, or type
`BAJFINANCE` or select a mapped full name. The new ATM panel shows
strike, expiry, option type, Dhan security ID, bid/ask/spread,
direction source, and (only when valid) hypothetical PREMIUM entry,
stop and targets. Inspect `GET
/api/v1/market-insights/analyse?symbol=BAJFINANCE` and the
`atm_recommendation` JSON object for unavailable reasons.
Source work is committed, but Python unit tests and live Dhan
integration must be verified on the Windows installation.

## Dashboard · NSE Participant Positioning — FII / Pro / Retail

The **Dashboard** now has three **nested colored SVG circles**:
- Outer circle: FII
- Middle circle: proprietary traders (PRO)
- Inner circle: Client (retail category, not exclusively small investors)

Green = positive index-derivatives positioning proxy; red = negative;
grey = neutral or unknown. Each category has its underlying index
futures net OI, day-over-day change, normalized futures/options
positioning score, volume-participation agreement and an observed
cycle-window net-position change. The UI also shows the observation
date, available history, expiry calendar status and last NSE fetch.

**Official NSE data:**
- `https://archives.nseindia.com/content/nsccl/fao_participant_oi_{ddMMyyyy}.csv`
- `https://archives.nseindia.com/content/nsccl/fao_participant_vol_{ddMMyyyy}.csv`

These expand the two NSE archive directory/prefix URLs supplied for
the project. The CSV parser validates real header names, the report's
embedded date when present, participant categories (FII/PRO/CLIENT)
and every numerical column; NSE HTML errors, 403 responses and missing
reports fail closed. Source URLs and content hashes are retained with
daily rows. The HTTP fetcher is bounded and does not use Dhan credentials
or bypass access restrictions.

**Storage**: `BHARATSIGNAL_INSIGHTS_HOME/participant_positions.sqlite`
contains the **raw daily OI and volume snapshots** (JSON per report
row), with an idempotent per-day/per-kind/per-participant primary key
and both kinds committed in one transaction. DII is also recorded
if present, though only three categories are visualized.

**Important aggregation limitation**: NSE participant-wise reports
aggregate across *all index instruments and all expiries*. They do
NOT break positions down by specific expiry/strike. The module labels
an **expiry observation window** only, using actual expiry dates
obtained from Dhan NIFTY `expiry_list` or the locally retained
`participant_expiry_calendar.json` list. If no verified expiry is
known, the UI prints UNVERIFIED, not a guessed expiry.
The first available report in a known cycle is the baseline.
A cycle change is **latest net OI − first stored net OI**;
**daily OI snapshots are never summed**.
If the true start of expiry is not in the archive, the label
explicitly reads 'observation window', not a complete cycle.

**Heuristic direction** for index derivatives only:
- Futures score: 100 × (index futures long − short) / total
- Options proxy: 100 × [(index call long + index put short)
  − (index call short + index put long)] / total of those legs
- Participant score: 60% futures + 40% option-proxy; NEUTRAL
  threshold ±8 units
- Overall display score: FII 50%, Pro 30%, Client 20%.
- NSE VOL long/short columns serve only as
  **participation agreement**, not true executed trade delta,
  buyer/seller aggressor order flow, or a validated confidence.
- All three in UP or DOWN prints ALL THREE ALIGN.
- The model is descriptive; it neither changes option-entry
  gates nor predicts market moves with a guaranteed probability.
  The PRO/CLIENT groups can hedge or hold spreads; 'Client'
  includes more than small retail investors.

**Scheduling** (local app must remain running):
- 08:00–09:15 IST: try to fetch missing reports from the prior
  completed trading session.
- 18:00–19:30 IST and 19:30 onward: try current day's NSE EOD
  report after publication. If not yet posted/403, old data
  stays stored and the panel reports PARTIAL/UNAVAILABLE.
- Backfill is bounded to six recent missing trading sessions
  per invocation (maximum eight); at most one attempt per time
  window. Historical window: last ~36 calendar days.
- All downloading happens in a worker thread, **never the Dhan
  intraday job lock**. No automatic action occurs when the
  Windows program or computer is switched off.
- Dashboard has an explicit `Refresh NSE reports` button.

**Local read-only API:**
- `GET /api/v1/market-insights/participant-positioning`
- `POST /api/v1/market-insights/participant-positioning/refresh`

**Modified files:**
- NEW `insights/nse_participants.py`
- NEW `insights/participant_refresh.py`
- NEW `insights/tests/test_nse_participants.py` (12 offline cases)
- NEW `insights/tests/test_nse_participant_api.py` (2 route cases)
- UPDATED `insights/service.py`
- UPDATED `insights/api.py`
- UPDATED `web/src/main.js`
- UPDATED `web/src/styles.css`

**Safe Windows update**: stop the local app and back it up. Copy the
eight files above from the development branch, preserving relative
paths. Do not overwrite `.env`, the Dhan API credentials,
SQLite journals, calendar settings or local backtests.

```bat
cd /d "H:\\BharatSignal_Fusion_Ready\\BharatSignal_Fusion_Insights"
.venv\\Scripts\\python.exe -m unittest insights.tests.test_nse_participants -v
.venv\\Scripts\\python.exe -m unittest insights.tests.test_nse_participant_api -v
.venv\\Scripts\\python.exe -m unittest discover -s tests -q
.venv\\Scripts\\python.exe -m unittest discover -s insights\\tests -q
cd web
npm run build
cd ..
START_INSIGHTS.bat
```

After startup, visit
`http://127.0.0.1:8765/api/v1/market-insights/participant-positioning`
and inspect date, refresh.status, participants and expiry_scope.
If you are online after NSE report publication, click the
Dashboard's **Refresh NSE reports** button.
NSE network access is not guaranteed; production live ingestion and
Windows test suites must be independently validated before trusting
the displayed signal interpretations.

**NSE access handling:** HTTP 403 or 429 immediately stops that
batch, instead of trying additional dates. Such a response means
the official archive has blocked or rate-limited automated access;
the application does not bypass the restriction, fabricate data,
or erase previously archived records.

### Windows SQLite WinError 32 regression — NSE participant tests

On Windows, the first NSE tests failed at `TemporaryDirectory` teardown:
`PermissionError: [WinError 32] ... positions.sqlite`. Root cause was
`with sqlite3.Connection as db` being misread as closing the connection;
it only commits/rolls back the transaction and leaves the handle open.

`insights/nse_participants.py` now wraps every connection in a
`@contextmanager` that commits/rolls back and **always calls
`db.close()` in a `finally` clause**, even on exceptions.
The existing `with self._connect() as db:` call sites are unchanged.
The updated `insights/tests/test_nse_participants.py` includes a
Windows-sensitive regression that renames the SQLite file after writes
and reads while the store object is still alive.

**Upgrade only these two files** from the development branch:
`insights/nse_participants.py` and
`insights/tests/test_nse_participants.py`.
Run `python -m unittest insights.tests.test_nse_participants -v`
(13 tests) and `python -m unittest insights.tests.test_nse_participant_api -v`
(2 tests), then both Python suites. No React rebuild or user database
deletion is necessary. No broker credentials, signals or DB schema are
modified by this patch.
