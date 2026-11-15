# Index Options: live order-flow pilot

This cumulative update adds order-flow research only to Index Options. Existing option-chain/OI/PCR strategies remain available. Existing resting-book ratios and OI strategies were not executed-trade delta, footprints or CVD. This is an additional engine, not a claim that those older strategies were broken.

## Install on your Windows computer

1. Stop the backend with Ctrl+C in its running command window, and close the application.
2. Download the ZIP of branch `feature/index-orderflow-live-test-20261115` from GitHub (Code > Download ZIP). Extract it into a NEW folder, outside your existing installation. Do not extract over the running application.
3. In the extracted folder, double-click `UPDATE_INDEX_ORDERFLOW.bat`. Its default destination is `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`. For another destination, open CMD in the extracted folder and run `UPDATE_INDEX_ORDERFLOW.bat "YOUR_PROJECT_FOLDER"`.
4. The updater installs websocket-client into your existing virtual environment, backs up replaced source files under `update_backups`, copies the cumulative Insights code, runs both test suites, and builds the frontend with npm. Internet access is required for pip; Node/npm must already be installed. Existing credentials, settings and database are preserved. Do not continue if validation fails; save the error output.
5. Run `START_INSIGHTS.bat` inside your EXISTING installation, then press Ctrl+F5 in the browser. Open **Index Options** and find the live order-flow panel.

The updated files are `insights/orderflow.py`, `insights/orderflow_replay.py`, `insights/brokers/dhan.py`, `insights/service.py`, `insights/api.py`, `insights/tests/test_orderflow.py`, `web/src/index_orderflow.js`, and `web/src/main.js`. Dependency and installation files are `requirements-orderflow.txt` and `UPDATE_INDEX_ORDERFLOW.bat` in the extracted update.

## What the panel computes

- Selects current mapped NIFTY, BANKNIFTY and SENSEX index futures with a valid instrument-master tick size. Missing mappings are shown; no guessed tick size is used.
- Uses Dhan v2 FULL WebSocket messages, including their five-level depth; this pilot uses the best bid/ask. It does not implement the separate 20/200-level depth heatmap.
- Infers trade side from the prior best quote, then price change. Dhan's sampled feed does not supply verified aggressor flags. Counts a cumulative-volume increase only once, assigns at most the observed last-traded quantity to that price, and marks the remainder unknown. Flat unclassifiable trades remain unknown.
- Builds one-minute footprints, delta and observed-segment CVD. Restart, reconnect, session change, cumulative-volume rollback or a reception gap above 30 seconds resets the observation window. This is not a reconstructed full-day CVD.
- Finds diagonal imbalances of at least 3:1 with a positive opposite-side denominator, stacked over at least three consecutive ticks. Zero-volume comparisons do not qualify.
- Finds absorption using volume at least 1.5 times the prior 20-bar average and range at most 0.7 times the prior average. Close position and delta determine direction. The defended-price proxy requires the same best-price level and at least 1,000 displayed quantity for 30 observations; this threshold needs live calibration. It is not proof of hidden orders or actual replenishment.
- Displays simple adjacent-bar price/CVD divergence as context, not a standalone entry.

## Entry, SL, target and reason rules

After at least 20 complete observed minute bars, a candidate requires at least 80% classified volume and either stacked imbalances with matching delta or absorption with the defended-price proxy. The immediately following closed minute must confirm the price direction and delta sign, with at least 80% classified volume. A partial first minute cannot trigger a signal.

Entry is the confirmation minute close. SL is one instrument tick beyond the setup bar's low for LONG or high for SHORT. Risk must be positive and at most 2% of entry. T1 is approximately 1.5R and T2 approximately 2.5R, rounded to the instrument tick grid. These risk multiples and confirmation gates are application additions, not promises from the PDF. The signal includes the triggering strategy and confirmation reason.

**All these levels are INDEX FUTURES reference prices, NOT CE/PE option premiums.** CE/PE labels express directional research only. Actual option entries depend on strike, expiry, premium, spread, volatility and execution. No orders are placed. No broker-held stop is created. A plan is suppressed after its observed SL or T1 is reached, when feed data is stale, outside the configured market session, or after 90 seconds. A reference entry at a past close is not a guaranteed available fill.

## Live test on 16 November 2026

Start before 09:15 IST if the configured exchange calendar confirms a trading session. Keep the backend running with a valid Dhan token and active data entitlement. The market-session/holiday check remains mandatory.

1. Check each mapped futures symbol/expiry and tick size. Resolve mapping warnings rather than substituting a spot index.
2. Confirm feed status, recent last-trade time and increasing recorded-packet counter. Market closed, disconnected, stale and missing-dependency states are separate from a valid no-signal result.
3. Allow at least 20 complete minutes plus the setup/confirmation process. Starting late or reconnecting restarts warm-up. A high unknown-volume fraction can legitimately prevent entries.
4. Compare displayed futures reference levels with the same futures contract in Dhan, not with option premiums. Record the reason, confirmation time and prices for paper evaluation.
5. Check recording warnings. Do not extend this pilot to other tabs until live observations and replay results have been reviewed.

Normalized observations are saved under `%USERPROFILE%\.bharatsignal-insights\index_orderflow\YYYY-MM-DD.jsonl`, or your configured `BHARATSIGNAL_INSIGHTS_HOME` root. Files stop growing around 250 MB per day and a warning is shown. Manage disk retention manually. Recordings contain market observations and contract identifiers, not account tokens. Each connection has a unique replay identifier, including across application restarts.

Replay from CMD in your installed project:

```bat
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
.venv\Scripts\python.exe -m insights.orderflow_replay "%USERPROFILE%\.bharatsignal-insights\index_orderflow\2026-11-16.jsonl"
```

Replay checks the research engine on recorded observations. It is not a fill/slippage simulator, historical tick backfill or profitability backtest. Automated tests and the frontend build verify implementation behavior; live credentials, connectivity, inference coverage and trading performance still need live validation. Perfect entries, error-free future operation and profitable targets cannot be guaranteed.

## Sources and scope

The uploaded `Dhan_OrderFlow_Analysis_Guide.pdf` supplies the footprint, delta/CVD, imbalance and absorption concepts. Protocol verification uses official documentation:

- https://dhanhq.co/docs/v2/live-market-feed/
- https://dhanhq.co/docs/v2/full-market-depth/
- https://dhanhq.co/docs/v2/annexure/
- https://dhanhq.co/docs/v2/instruments/

The official extended-depth documentation describes NSE equity/derivatives coverage; do not rely on the PDF's BSE 20-level assertion. This release uses the ordinary FULL feed only. No change to Intraday, F&O, Swing or Positional order-flow logic is included.
