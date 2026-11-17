# Dated Pre-Market watchlists and ATM option premium entries

This cumulative update builds on the NIFTY 500 and notification fixes. It changes the Pre-Market follow-through schedule and Index Options presentation and pricing. It does not place orders or establish a profitable strategy.

## Pre-Market 8 AM

- The name of the tab stays the same. On a running backend, the latest completed trading-session watchlist can be prepared after hours, overnight, or on weekends/holidays. Today's finalized daily candle is requested from 15:40 IST onward; 15:30–15:39 waits for daily-data completion. Before open or on a non-trading day, the most recent verified trading session is used.
- Valid watchlists are saved by source trading date under the configured data folder: `premarket_archive/YYYY-MM-DD.json`. `premarket_watch.json` retains the most recent snapshot. This is separate from the next session's live entries.
- A valid current dated cache is reused. Failed preparation can retry on a later five-minute bucket; Pre-Market preparation runs before the separate after-close long-term job so that the latter's failure does not suppress it.
- After open the saved candidate/gainer/loser symbols are frozen for that trading day. The live monitor checks those stocks, not a newly changing full exchange universe.
- First cutoff: **09:30 IST**, using candles closed by then, including the 09:15–09:30 opening period. The 09:30-start five-minute candle becomes usable at **09:35**. Further checks run every five minutes through **15:25**. A late start checks the latest cutoff without pretending to have performed missed earlier scans.
- Separate BUY breakout and SELL breakdown sections show entry reference, T1, T2, SL, strategy and reasons. Stocks with no valid setup remain in diagnostics rather than receiving fabricated entries.
- Checks include session liquidity/turnover, RVOL, ADX, VWAP, EMA20/50, RSI, opening/red-bar confirmation, daily/15m momentum and prior-day range breaks. Longer-term rules remain contextual with their own horizons; missing derivatives OI or fundamentals are not invented.
- Results use completed candles. A missing session bar or stale prior-day history blocks that stock. Source errors are visible and retryable. Each cycle has a soft 240-second budget; slow network calls and shared scanner workload can delay completion. Results older than 10 minutes, future-dated results and closed-market results are not promoted as current entries.
- Dhan's short history cache now changes at candle boundaries, so a newly completed five-minute bar cannot be hidden by a cache entry from the prior period.

The pre-market discovery universe and existing strategy filters are retained; this update does not silently expand that tab to all NIFTY 500 stocks. Intraday and Positional retain their NIFTY 500 functionality from the preceding update.

## Index Options: contract strike versus premium entry

The main panel displays separate CE and PE assessments for mapped NIFTY, BANKNIFTY and SENSEX indices. **Strike is the ATM contract identifier. Entry, T1, T2 and SL are prices of that option contract, not index/strike levels.** Both CE and PE plans are option-buying scenarios: their targets are above premium entry.

1. Select the nearest listed strike to chain spot for the nearest current available expiry. Exact contract security IDs come from Dhan; no synthetic strike or premium is created.
2. Require a confirmed opening, red-bar or Fibonacci directional watch, agreeing 5m/15m trends, and no opposing 60m trend. Before 10:15, the prior completed session's last hourly bar may provide context, so an unfinished current hourly candle is not required or used.
3. Block conflicting strategy directions, loss of two-close trigger sustain, large rejection wicks, indecision candles and price more than 2.5 ATR from EMA9. Check chain spot against underlying candles and PCR against direction.
4. Require positive ATM OI and actual premium history for that selected contract. Fetch its market-depth quote and require positive two-sided depth, spread at most 2%, positive traded volume and a last-trade timestamp no older than 120 seconds at receipt. A recent trade does not timestamp every individual depth order or guarantee an executable fill.
5. Entry reference is the best ask. SL is the lower of the option's latest three-candle low and entry minus option ATR14. Risk must be 3–35% of premium; the quote must remain within 2 ATR of the completed option candle. T1 = entry + 1.5R; T2 = entry + 2.5R. Reject invalid or collapsed rounded price levels.
6. Missing evidence produces WAIT with specific blockers and no entry/targets. Cautions cover false moves, expiry-day decay, high absolute IV and slippage. These are deterministic filters, not a calibrated probability or a guarantee against false moves.

Underlying first-5m/red-bar/Fibonacci charts remain available in a collapsed evidence section explicitly labelled **index levels, not option entry prices**. Legacy fixed-percentage premium plans no longer populate the Index Options main result list. Other tabs retain their existing strategies.

## Install on your existing Windows application

1. Close the running app with **Logout / Exit**.
2. Download the complete ZIP for this update and **Extract All** into a separate folder.
3. Open the extracted folder containing `UPDATE_SESSION_PREMIUM.bat`.
4. Double-click that file if your installed app is at `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`.
5. For another installed location, open CMD in the extracted folder and run:

```bat
UPDATE_SESSION_PREMIUM.bat "C:\Users\YourName\BharatSignal"
```

6. Wait for package installation, backup/copy, tests and frontend build to pass. Your `.env`, Dhan credentials and saved databases are preserved. Do not proceed if validation reports a failure.
7. Run `START_INSIGHTS.bat` from the installed application folder and press **Ctrl+F5** in the browser.

For a new PC, use this complete ZIP with the fresh-installation guide and `INSTALL_INSIGHTS.bat`, not the update script. Python/Node installation and Dhan configuration remain necessary.

## Verify after installation

- Start the backend in the evening. Pre-Market should show the completed trading date and saved watchlist. Verify `premarket_archive` under the app's data directory (default `%USERPROFILE%\.bharatsignal-insights`).
- Leave the backend running. On the next verified trading day, check Pre-Market at 09:30/09:35 and later, including after 10:00. The assessment cutoff should advance every five minutes. BUY and SELL appear separately only when their rules pass.
- In Index Options, compare the displayed ATM strike with the separate premium entry. The entry should correspond to the selected option's ask. Read last trade time, spread, pricing reasons and WAIT/caution messages.
- During missing/stale option data, the app must withhold premium levels rather than substituting an index value. No broker orders should be sent.

Automated tests cover date selection, archive restoration, continuous scheduling, legacy behavior, actual-contract premium levels for CE/PE, stale/wide quotes, receipt latency, missing history, rejection/conflict filters and cache boundary behavior. Live Dhan market-session testing and Windows execution still require your installed environment. No claim of perfect entries, guaranteed targets or proven profitability is made.

Dhan public data references checked:
https://dhanhq.co/docs/v2/market-quote/
https://dhanhq.co/docs/v2/historical-data/
