# Positional tab: five-minute background research

This update includes the previous Scanner, FII holdings, BTST import and swing fixes. It adds `insights/positional.py` and `web/src/positional.js`, integrated into the existing backend startup and sidebar.

## Windows installation

1. Stop the application/backend. Download this branch using GitHub **Code → Download ZIP** and extract it into a separate folder such as `H:\Positional_Update`.
2. In the extracted folder, double-click **UPDATE_POSITIONAL.bat**. It uses your existing project:
   `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`.
   If your folder is different, open CMD in the extracted folder and run:
   ```bat
   UPDATE_POSITIONAL.bat "H:\your\actual\project"
   ```
3. The updater creates a source backup in `update_backups`, copies the complete Insights modules and web source, then runs the Insights/root tests and production frontend build. Your `.env`, credentials and databases are preserved. Copy errors roll back; validation failures leave backed-up new sources for diagnosis. Do not start the application if the updater reports a failure.
4. Once it reports tests/build passed, run **START_INSIGHTS.bat** from your existing application folder. Refresh the browser with **Ctrl+F5** and open **Positional**.
5. The background scanner starts automatically. Opening this tab is not required for scanning. Keep the Python backend running; closing the backend or sleeping the PC stops scanning.

No new runtime dependencies are added. If your existing environment is missing dependencies, use `requirements-insights.txt` and `npm ci` as described in `SCANNER_UPDATE.md`.

## What appears in the tab

Stock/company and exchange, BUY/SELL side, strategy name, entry reference, Target 1, Target 2, SL, percentage risk, last completed 5m close/time, signal time, readiness status, exact reason, target basis and exit rules. Intraday R1/S1 rows are separated from positional/swing rows.

There are no automatic orders or assumed trade fills. READY means the last completed 5m close is at/beyond the trigger by at most 1%. A price more than 1% beyond it is marked EXTENDED. SL/target touches use observed OHLC, with SL taking precedence if ordering is ambiguous. Missing, stale or incomplete price history cannot produce READY.

## Strategies from Trading_Strategies.pdf

| Strategy | Implemented signal | Stop and exits |
| --- | --- | --- |
| Morning Star | Completed daily red/star/green sequence after a downtrend; green closes at/above first body's midpoint | Below star low; reject stop distance over 6%; five-session exit guidance |
| Supertrend + RSI | Completed daily RSI14 >60, Supertrend(10,3) green and below close, volume > prior session | 3% initial stop; five-session exit guidance; red daily Supertrend exit review |
| R1 breakout and S1 mirror | Completed 15m close crosses prior-day classic R1/S1 with matching Supertrend direction | Stop no wider than 2%, closer candle extreme allowed; T1 ±2%, T2 R2/S2; runner at cost/ST reversal; square off 15:15 IST |

The PDF leaves some pattern terms qualitative. This implementation defines a large first body as at least the preceding 20-body average, star body ≤30% of the first body, star body near the first close, and the final green body ≥50% of the first. Downtrend requires the pre-pattern close below its value four sessions earlier and the first candle below SMA20.

The daily PDF strategies do not specify two fixed targets. **T1 = 1.5R and T2 = 2.5R are explicit app extensions**, where R is entry minus SL. Entries use signal close as a reference, not a guaranteed next-day fill. PDF daily watches persist for up to five completed sessions after the signal, including SL/target touch checks against later daily bars. Older signals become TRACK ONLY, never new READY entries. Expiry counts from the signal date; your actual five-day holding exit must count from your fill date.

R1/S1 is **intraday only**, with new setups from 09:30 to 14:30 IST. The app chooses the PDF's stop-entry option: 0.1% beyond the breakout high/low. It conservatively skips opening gaps beyond R1/S1, moves already exceeding 4%, and setups without room for R2/S2 beyond T1. It does not implement the optional gap-retest entry. Fifteen-minute bars require exactly three contiguous completed 5m candles; incomplete candles cannot trigger a setup.

## Additional published setups

- **Donchian 20D breakout (adapted):** close above the prior 20-session high, excluding the signal candle; SMA50 > SMA200 with close above both; volume ≥1.5 times the preceding 20-session average. Stop: 2×Wilder ATR14. Targets: 1.5R/2.5R. Review exit under the prior 10-day low.
  Source: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/price-channels
- **Moving Momentum (adapted):** SMA20 > SMA150; slow Stochastic(14,3) below 20 during the preceding ten sessions; MACD(12,26,9) histogram crosses above zero. Stop below the last ten-session low; targets 1.5R/2.5R. The finite pullback window and target rules are app choices.
  Source: https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/moving-momentum

These published concepts are not evidence that this implementation is profitable or the best strategy. Strategy-specific win rates have not been measured. Source rules and app adaptations are separately identified above. News/earnings, surveillance lists and Nifty event filters are not automated in this tab.

## Scan schedule and coverage

- A dedicated worker starts a cycle on startup and each five-minute clock interval. It runs even while other tabs are open. It never overlaps its previous cycle or queues a backlog. The backend must remain open.
- Uses the existing mapped cash-stock universe (normally the application's F&O cash list), optionally filtered by `INSIGHTS_WATCHLIST`, capped by `INSIGHTS_MAX_SYMBOLS` (existing default 30, maximum 200). **This is not a scan of every NSE/BSE listing.** Mapped, selected, scanned, valid and omitted counts are shown.
- To adjust the universe, edit these settings in your existing `.env` while the backend is stopped, then restart:
  ```dotenv
  INSIGHTS_MAX_SYMBOLS=30
  INSIGHTS_WATCHLIST=RELIANCE,INFY,TCS
  ```
  Use the exact mapped symbol, ticker or Dhan security ID. Leave the watchlist empty for the capped default universe. These existing settings also affect other app scans; raising the limit increases broker load.
- During regular exchange sessions, selected stocks get fresh 5m history checks. Daily features are cached until the next completed daily session; daily signals cannot confirm before 15:40 IST. Outside market hours, cached daily research is reviewed but intraday requests/READY labels are disabled.
- A valid configured holiday calendar and Dhan credentials/data entitlement are required. Non-overlapping broker calls share the application's existing lock. Each scan has a 240-second budget including lock waits; if the broker or other scans prevent completion, the tab reports failure/partial coverage rather than claiming every stock was scanned. Lower the cap if scans regularly exceed the interval.
- Liquidity gate: close ≥₹20, preceding 20-session average volume ≥100,000, and average volume × close ≥₹1 crore. Stops must be 0.2–6% away. This can legitimately produce no setups.
- Results persist locally under the Insights data directory's `positional` subfolder. A failed scan marks prior results stale; a successful cycle replaces rows with its own evaluated data. GET requests and browser polling do not issue broker requests.

## Test on your PC

1. Start the backend and open Positional. After the first cycle, check status, selected/scanned counts and source errors. Outside market hours, expect closed-market labels.
2. During market hours, wait for two successive five-minute cycles. Check scan time and the 5m candle timestamps; navigating away must not stop the worker. Daily signal timestamps should remain the prior session until today's daily bar is complete.
3. Verify one candidate's daily chart and entry/SL calculations manually. Test strategy and stock filters and the READY-only checkbox. A zero-result list is valid; do not relax rules just to force output.
4. Run automated checks from CMD in the installed project:
   ```bat
   cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
   .venv\Scripts\python.exe -m unittest insights.tests.test_positional -v
   .venv\Scripts\python.exe -m unittest discover -s insights\tests -q
   .venv\Scripts\python.exe -m unittest discover -s tests -q
   cd web
   npm run build
   ```

Automated tests cover the strategies on constructed OHLCV, incomplete/future bars, stale data, stop/target checks, retained watch expiry, cached daily/repeated 5m requests, non-overlapping scheduling and API behavior. They are correctness tests, not a profitability backtest. Live Dhan and full interactive Windows UI verification require your running environment.

## EMA9 multi-timeframe addition

The latest update also adds **EMA9 Trendline + Volume** on 1H, 1D, 1W and 1M. See [EMA9_POSITIONAL_UPDATE.md](EMA9_POSITIONAL_UPDATE.md) for its exact rules, installer, 3R target, history coverage and adjusted-data confirmation requirements. Existing strategy rules above are unchanged.
