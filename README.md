# BharatSignal Fusion 0.7.1 — background research scanner

## New in 0.7.1: RSI strategy

The new **RSI strategy** tab runs independently of the Institutional/ScanX filter. It scans the application's mapped F&O cash underlyings plus available ScanX cash additions; it is not an all-NSE cash-market scan. Source membership in ScanX is not required for existing F&O stocks.

Its exact filter is **monthly RSI14 >60 AND weekly RSI14 >60 AND 39 < daily RSI14 <44**, with strict boundaries. All RSI readings use completed candles, Wilder smoothing with arithmetic-mean seed, and at least 30 completed monthly/weekly bars. The current incomplete day/week/month is excluded. The selected-row details show the RSI dates. Unlike Institutional stocks, this tab does not require a daily cross above 40 and does not use provisional daily RSI.

RSI matches remain visible as a watchlist while waiting for two additional confirmations from completed 15m Dhan OHLCV candles:

1. Price rebound: green close above VWAP, close > EMA9 > EMA21, and close above the previous 15m candle's high.
2. Strength: relative volume >=1.5 times the previous 20 completed 15m bars' mean, and ADX14 >=20.

Indicators are calculated locally from Dhan data, not downloaded as a special Dhan signal. These are testable confirmation rules, not a demonstrated best-performing indicator combination. The default ML requirement on the older technical screen does not add an undocumented ML gate to this RSI strategy.

Entry is the confirming 15m close. SL is below the lowest low of the last three contiguous completed 15m candles, buffered by max(₹0.05, 0.1 ATR14). A stop wider than 4% is rejected; a tight stop is never invented. T1 uses prior resistance at least 1.5R away, otherwise 1.5R; T2 uses later resistance at least 2.5R away and beyond T1, otherwise a corresponding R fallback. These are underlying cash-stock prices, not option premiums. The stop is on a 15m closing basis.

The entry window is 09:30–15:15 IST, subject to actual confirmation availability. Stale candles, price beyond the reference-entry tolerance of 0.25R, an already-breached stop/reached T1, zero affordable quantity, or a failed/unknown F&O ban check block entry. Quantity is capped at ten shares and the configured risk/capital budget. Research levels are not automatic broker orders or guaranteed loss caps. Paper-watch exits for this new strategy are not yet implemented.

The new tab keeps the eight-column layout and cached navigation. The existing five-minute worker performs the analysis without a new scan on tab clicks. All mapped stocks now receive multi-year daily-history warmup for this screen, so the first pass may be substantially slower. History is cached and normally updated once per session; incomplete-history and feed failures remain explicit. Long passes skip missed refresh slots rather than overlap. Model work remains on its existing separate queue. Keep the app open and the PC awake.

To use it: install the update, start Dhan live once, wait for initial history loading, then select RSI strategy. Select a row to inspect RSI, price and strength checks, volume, ADX and confirmation time. Enable Show all waiting rows for exclusions. Use Ctrl+PageDown / Ctrl+PageUp to move between tabs if the window is narrow. No claim of improved accuracy or profitability has been validated for this new rule.

## New in 0.7: Institutional stocks and AI selected stocks

Both tabs use the same eight-column layout and existing five-minute background scheduler. Selecting a tab only reads cached results. Keep the app open and the PC awake. Long scans skip missed time slots; initial backfill and CPU/network delays can exceed five minutes. No guarantee of zero buffering or stock selection at an exact time.

### Institutional stocks

The app reads the public [Insti Footprints Screener_HA](https://scanx.trade/stock-screener/insti-footprints-screenerha-453307) snapshot once per scan cycle, validates screener ID 453307 and its filters, then independently checks each mapped candidate with Dhan candles. ScanX candidates outside F&O are included when present in the Dhan NSE EQ instrument master. A failed/stale source, changed schema/filters or incomplete paginated result blocks institutional membership; the app never substitutes the entire F&O universe. Public-page access is not a guaranteed supported API. Source timestamps are interpreted as IST, with at most 15 minutes age and five minutes clock tolerance. Fetching the page again does not by itself prove that the site's underlying data refreshed.

The source filters retrieved during development were: NSE equity; market cap >=₹1,000 crore; changes in FII and DII holdings >=0; FII and DII holdings each >=2%; last-quarter YoY profit growth >=15%; five-year ROCE growth >=10%; debt/equity 0–0.5; three-month price change >=10%; promoter holding change <=10,000 (the unusually broad bound is retained exactly as configured). These holdings are periodic disclosures, not evidence of institutions placing live orders.

The additional chart rules are:

- RSI14 of the last completed monthly candle >60, and last completed weekly candle >60. At least 30 completed bars of each timeframe are required; the first potentially partial source period is discarded. Up to 2,200 calendar days of daily history are requested for ScanX candidates and cached.
- Current partial daily RSI is in 39–44. This is a watchlist zone, not automatically a buy.
- Entry requires the previous completed daily RSI <=40 and the current partial daily RSI >40 (still <=44), a green daily candle, and accumulated volume >=1.5x the previous 20 completed daily sessions' mean volume. No extrapolated end-of-day volume is used.
- Intraday crosses are labelled PROVISIONAL because the daily candle can change before close. Each five-minute check can remove the setup. Signals do not repaint previously stored completed monthly/weekly bars, but the current-day signal is deliberately provisional.
- Entry is the latest closed-minute price. Structural SL is below the current-session low by 0.1 daily ATR, minimum ₹0.05 buffer. Reject if risk exceeds 4% rather than shrinking the SL. Targets use prior resistance at >=1.5R and >=2.5R (or corresponding R fallbacks). Closing-basis daily stop is research guidance, not an order.

The source can select young companies without 30 monthly candles. These correctly show insufficient-history reasons when Show all waiting rows is enabled. A candidate may also fail the RSI/volume filters, leaving no entries. Future-dated or stale ScanX snapshots are rejected even if their stock list looks plausible.

### AI selected stocks

This is a cash-equity research screen, using the F&O underlying universe plus mapped ScanX additions. It implements two precisely bounded SMC-style hypotheses, not every interpretation of SMC and not a claimed best-performing strategy:

1. **Sell-side sweep + CHoCH:** within the last five completed 15m bars, a candle sweeps a pre-existing 20-bar low and reclaims it. The preceding five-bar closes were descending. A fresh green displacement candle closes above that pre-sweep five-bar high; its body is >=0.6 ATR.
2. **BOS + first FVG retest:** a 15m close breaks the prior 20-bar high, a three-candle bullish fair-value gap forms, then its first retest rejects upward and closes above the preceding candle's high. A preceding bearish candle identifies an order-block proxy for structural risk. An already mitigated gap is rejected.

Both require prior completed daily close > EMA50, completed 60m close > EMA9 > EMA21, 15m RVOL >=1.5, ADX >=20, green candle and close above VWAP. Swing ranges use only past data; no future pivot bars. The sweep must originate below the prior range midpoint (discount context). These are chart-pattern proxies, not proof of hidden institutional activity. Other named SMC concepts are not silently claimed as implemented.

SL uses the relevant sweep/origin/FVG structural low plus 0.1 ATR, minimum ₹0.05 buffer. Risk >4% is rejected. T1/T2 use prior resistance with 1.5R/2.5R minimum distances and fallbacks. Entries require fresh data and price within 0.25R of the reference; already-breached SL or reached T1 invalidates eligibility. Entry window ends at 15:15 IST. Cash quantity is capped at ten shares and the configured risk/capital budget, not automatically sent to Dhan.

F&O-underlying candidates require the current ban-list check to pass, using the exchange ticker (not the company display name). Non-F&O ScanX cash stocks show this check as not applicable. A missing report/ticker does not pass.

The existing calibrated LightGBM/XGBoost **3m** model must also pass its checks for AI selected stocks to be ready. A matched setup without a valid model remains visible with a WAIT-ML reason. New SMC candidates have priority in the existing bounded top-20 auto-training queue, with daily attempt limits; model training is not restarted every five minutes. The 3m model predicts a different ATR target event, so its probability is supporting context and is **not** the win probability of these SMC setups. No dedicated SMC/institutional profitability backtest or accuracy improvement has been demonstrated. Kronos remains separate forecast context.

These two tabs currently provide research levels only. Paper-watch exit tracking for their distinct holding rules is not implemented; selecting Track selected explains this rather than applying an unrelated exit rule. Existing strategy paper watches are unchanged.

Select any displayed row for RSI, volume, source timestamp and model evidence. Enable Show all waiting rows to inspect exclusions. New screens require live history and do not fabricate demonstration buy recommendations.

## Simpler tables in 0.6.1

The research tables now show eight columns: Stock/Index, Setup, Trade, Entry, T1, T2, SL and Status/Why. Select a strategy row for expiry, quantity, timestamps, underlying levels, ban/delivery/event checks and full reasons in plain text. The visible status explains why there is no entry instead of saying only BLOCKED. Long reasons can be read in full in the selected-row panel.

A pattern match is not necessarily a current entry. Historical/expired triggers, moved prices, missing quotes, unknown safety checks or excessive lot risk may block it. The underlying rules are unchanged. Stock-option prices remain premium estimates; unavailable premiums stay blank rather than being replaced with the underlying stock's price. 125D cash rows show cash prices. Five-minute background refresh and cached tab navigation are unchanged.

## Install this update

1. Close the running application.
2. Extract BharatSignal_Fusion_Kronos_v0.7.1.zip.
3. Copy the files inside BharatSignal_Fusion into your existing application folder. Replace matching files; keep your existing .venv folder.
4. Double-click UPDATE_CHECK.bat. Wait for the checks to pass.
5. Double-click START.bat. The title should show 0.7.1.
6. Select DHAN LIVE, enter your Dhan client ID and token locally, then click **Connect / Start background** once. Keep the PC awake and connected.

No new dependencies from 0.5.2. For a new installation, run INSTALL.bat, INSTALL_AI.bat and INSTALL_KRONOS.bat as needed before START.bat. Never send your token in chat.

## Five-minute background updates and instant cached tabs

The first scan starts immediately after connection. Subsequent market scans use a 300-second start grid: a scan starting at 09:20 targets 09:25 next, even if it finished at 09:22. Only one full scan runs at a time. A scan that runs past its next slot skips missed slots rather than launching overlapping scans. Slow API calls, initial history backfill, rate limits, model computation and network speed can delay coverage; five-minute delivery and zero buffering cannot be guaranteed.

Tabs only display results already in memory. Clicking Stock options, BTST stocks, Intraday Top 10 or Indices never starts a fresh scan or waits for Dhan. Existing rows remain visible during refresh. Only the visible table is updated, with unchanged rows reused. New results arrive instrument by instrument. Data timestamps and expired-entry labels distinguish cached results from current eligible entries. Stop invalidates entries while retaining historical rows.

News and quote/depth collectors also run on independent five-minute schedules. Daily historical data and dated safety reports are reused rather than downloaded repeatedly; unavailable reports retry after five minutes. ML training and Kronos run on separate bounded queues, reusing valid models and forecasts for the same candle. Training is not restarted every five minutes: the existing daily attempt limits and model-validity checks apply. The app must remain open; this is not an installed Windows background service. First launch needs history/model warmup before results exist.

## Tabs and strategies

| Tab | What it displays |
| --- | --- |
| Dashboard | Cached sector strength, index bias and coverage |
| Stock options | Bear-trap CE / bull-trap PE patterns on genuine futures 15m candles, mapped ATM option and expiry, current ask, estimated premium T1/T2/SL, separate underlying levels, risk and blocking reasons |
| BTST stocks | 125-day cash breakout and BTST consolidation patterns, entry/targets/structural SL and safety checks |
| Intraday Top 10 | Existing four-completed-15m-candle indicator ranking, earliest 10:15 IST |
| Indices | Existing support/resistance research plans and targets |
| AI / News / Risk | Selected-symbol model evidence, FinBERT sentiment and important news alerts |
| Kronos forecasts | Instrument dropdown, cached predicted chart and K1/K2; manual prediction button remains available |
| Activity / Coverage | Background refresh countdown, errors, warmup, model queue and alerts |

Select a row to inspect its full evidence. Enable **Show all waiting rows** to see why instruments did not qualify. No qualifying candidates is a valid result; the app does not fill tables with invented buy signals. New trap/BTST live screens require genuine data and are not simulated recommendations in DEMO. Export table exports the visible strategy table when one of those tabs is selected.

### Stock options: operational interpretation

Default mode follows the written trap rules: first candle red for CE / green for PE; second candle opposite colour; no close beyond the first candle's invalidation extreme; second or later qualifying candle must close on the required side of VWAP. A subsequent completed 15m close beyond that candle's high/low confirms the trigger. This deliberately uses closing confirmation, not an intrabar touch. Entry freshness expires after ten minutes or 15:15, whichever comes first. SL is the immediately previous candle's low/high. Targets use favourable first-candle/pivot structure at least 1R away, then 1R/2R fallbacks.

**Strict trap scanner** additionally requires the opening wick equality, opening gap beyond the previous completed session's low/high and the second/third-candle sequence. The ambiguous scanner reference [=-1] is interpreted as the previous completed session. The supplied VWAP above-or-below clause does not add directional confirmation; the written directional VWAP rule is applied. These are disclosed interpretations of conflicting rules, not an exact reproduction of an unidentified scanner platform.

Nearest mapped future expiry and nearest listed ATM stock option are used; expiry-day contracts are excluded. Maximum one lot, and zero quantity if its structural risk or premium cost exceeds the configured budget/capital. Stops are never artificially tightened to make a trade fit. Premium targets/SL use current quote Greeks with constant volatility/time and basis assumptions. They are estimates, separate from underlying levels and Kronos forecasts, not guaranteed option prices.

### BTST stocks: exact definitions and safety setup

125D uses a 15:15 partial daily snapshot above the previous 125 completed sessions' high, volume greater than 2x their mean, and RSI14 below 70. Entry window is 15:15–15:25 exclusive. T1/T2 are 1R/2R information; the holding rule is five observed trading sessions, counting entry as day one, with an alert after 15:25 on day five. Default closing-basis daily SL takes priority. The optional **125D time-only exit** paper setting records SL breaches as information instead, while retaining monetary-loss alerts.

BTST selects at the 15:05 snapshot above PDH and the consolidation high, volume at least 2x daily SMA10 (includes the current snapshot), and RSI14 strictly 55–65. The formula Volume > Volume*0.35 is always true for positive volume and is not a meaningful filter. Consolidation is defined as one day with range <=2%, or two overlapping days with combined range <=3%. A completed five-minute close above the zone between 15:10 and 15:20 must also have close > EMA9 > EMA21 and ADX >=20. Underlying targets are +1.5% and +3%; SL is below the zone on a five-minute closing basis. Next-session time-exit alert is 11:15. Dates are observed from market data, not a complete holiday calendar.

Safety checks fail closed when data is unknown. The app attempts dated NSE ban and delivery reports automatically. Current-day delivery >40% is required by default; final delivery reports may be unavailable during the entry window, so this can legitimately block all BTST entries. **Allow prior-day delivery proxy** is an explicit alternative, clearly labelled with its report date, not current-day confirmation.

BTST and 125D also require a recently reviewed event calendar. Copy risk_calendar_template.json, genuinely review RBI/FED, company results, elections and Budget events, fill the reviewer/time/coverage fields and event records, then use **Import risk data**. Coverage must span four days for BTST or ten days for 125D and be reviewed within 24 hours. A blank template cannot pass. The same button imports dated NSE ban/delivery CSVs if automatic downloads fail. News sentiment alone cannot establish absence of a major upcoming event.

Important returned news (RBI/FED, earnings, Budget/elections) is checked every five minutes, deduplicated and shown with source/time and possible impact. Coverage is the returned macro/major-company/rotating-stock feed, not every publication or an exhaustive event calendar. Impact labels are hypotheses.

**Track selected (paper)** is optional and places no orders. Paper positions are monitored during background scans for targets, structural closing stops, time exits and a ₹2,000 loss alert. Periodic observation, gaps, fees and slippage mean this is not a guaranteed maximum loss or an automatic broker exit. Cash quantity is capped at ten shares and options at one lot, subject to a lower configured risk limit.

The new strategy filters are deterministic rules. Existing 3m ML probabilities and Kronos projections remain separate research context: they have not been validated as win probabilities for these new trap/BTST rules or option premiums. No live-market results or accuracy guarantees are claimed.

## Automatic ML training

Keep Auto train Top 20 + major indices (3m ML) checked. After each full scan, the selected candidates and five mapped major indices enter a bounded/coalesced queue of at most 25 instruments. One instrument trains at a time, with separate LONG and SHORT models and 12 Optuna trials per direction. The scan/UI remain on separate workers; CPU contention can still slow scanning and Kronos. This may take a long time for the first universe; it is not simultaneous training of 25 instruments.

Training uses genuine cached history. DEMO never trains live models. At least 800 labelled bars with both outcome classes in every segment are required. Current eligible models are reused; failed/untrained/expired/drifting models are queued. Automatic attempts are limited to once per instrument/3m timeframe per IST date, persisted across restarts in auto_training_attempts.json. Manual Train selected ML can retry after correcting data/dependency problems. Stop clears pending auto jobs; a running fit may finish before the worker stops. The optional after-close retuning feature is separate and may retrain up to three due instruments.

All GUI ML inference/training is explicitly 3m, including when the chart dropdown is 15/60/240. This avoids pretending that one 240m bar per day supports a ten-bar same-session ML target. The chart timeframe controls technical analysis, displayed closed candles and Kronos forecasts; it does not change the ML target interval.

The ML target is +1.5 ATR before -1 ATR within ten 3m bars, from the next bar open, with conservative stop-first ambiguity and no overnight labels. Chronological 60/15/10/15 splits purge overlapping label horizons. Optuna tunes within the first 75%; final fit uses 60%; calibration uses the following separate 10% after the tuning region; final 15% is test data. Gates require >=100 test examples, AUC >=0.55, Brier better than a training-prevalence baseline and positive calibration coefficient. Live agreement additionally requires calibrated P >=0.65, both raw P >=0.5 and disagreement <=0.20. These checks do not establish profitable trading. Repeated overlapping holdouts are not independent forward evidence.

Models older than seven days or with at least three >5-standard-deviation feature outliers block the gate. Missing required order-book features block inference. Book features are used only when >=80% of the initial training region has real received snapshots; otherwise models use OHLCV only. Historical books are never fabricated. Native JSON/text models are saved locally; no pickle or bundled trained stock models.

## Chart timeframe and Kronos limits

3/5/15/60/240 candles are session-anchored at 09:15 IST. Partial/gapped bars are excluded. A normal session contains one complete 240m bar, 09:15-13:15; the remaining 135 minutes are not relabelled as a 240m candle. High-timeframe views request up to 89 calendar days initially, but 60 complete chart bars may still be unavailable. WARMUP is valid.

Kronos requires >=60 complete input candles and forecasts only complete remaining bars in the same session. Thus a 240m forecast has no next complete bar in the normal session and correctly reports unavailable. No next-day trading date/holiday session is invented. 60m forecasts may also be unavailable late in the session.

K1 is the favourable extreme of median predicted closes over the first half of the available horizon; K2 is the favourable extreme over the entire horizon. Only values beyond the last observed close in the forecast direction appear. K1 and K2 may be equal or unavailable. They are separate from the 1.5R/2.5R technical plan targets and are not promised fills. Stale/mismatched forecasts do not populate current table K1/K2. Historical forecasts remain labelled historical in the chart.

Three sampled paths form a gold median line and shaded min/max envelope. The envelope is not a calibrated confidence interval. Official Kronos-mini source and pinned model provenance remain in vendor/Kronos. Dhan turnover amount is approximated from OHLC × volume.


## Retained limits and verification

Dhan access must be verified on your account. No credentials are bundled. The app sends no orders and does not manage positions or exits. There is no full holiday/special-session calendar. Missing recent entire sessions cannot reliably be distinguished from holidays. This is periodic REST scanning, not tick streaming. Intraday history/backfill and model training can take substantial time.

Automatic models must pass statistical validation; model counts and test counts are not trading accuracy. FinBERT uses available feed text, not all filings. Unknown/stale/unmatched sentiment reduces paper-risk sizing. TreeSHAP explains LightGBM output, not causation. There is no established live profitability or improved accuracy. See BUILD_VERIFICATION.json for software checks and remaining limitations.
