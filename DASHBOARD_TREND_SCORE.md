# Dashboard trend scoring update

The old score required full EMA20/50/200 alignment before granting EMA and ADX points. Missing VWAP removed another 15 potential points, and the total possible score was 90 despite the meter's /100 label. This can understate emerging trends. Today's exact observation cannot be replayed without your Dhan candle snapshot.

All dashboard index cards now use the same price-only model on completed 5-minute candles (minimum 201). Each rule awards its weight positively, negatively, or zero:

| Rule | Maximum points |
| --- | ---: |
| Close versus EMA20 | 20 |
| EMA20 versus EMA50 | 20 |
| EMA50 versus EMA200 | 10 |
| EMA20 change over three bars | 20 |
| ADX >=22 with directional movement agreeing with EMA slope | 15 |
| Break of previous 20-bar range | 15 |

Uptrend starts at +40, Downtrend at -40; otherwise Sideways. Price comparisons use a neutral band of max(10% of ATR14, 0.001% of close). The score is a transparent rule model, not a calibrated probability or backtested accuracy claim. Indicator contributions appear below the meters. Cash-index volume/VWAP is not required. ADX measures strength; directional movement supplies direction: https://www.fidelity.com/viewpoints/active-investor/average-directional-index-ADX

The card separately shows points and percentage since the session's first available candle open. This is NOT the official change from previous close. A positive daily move can coexist with flat or declining recent candles. Historical/stale status is evaluated per index. Existing trade-strategy bias/score fields remain unchanged; the new dashboard model is in `indices[].trend`.

## Windows installation
1. Close the running application/backend.
2. Download this branch's ZIP from GitHub and extract it into a separate folder (not over the installed application).
3. Double-click `UPDATE_DASHBOARD_TREND_SCORE.bat` in the extracted folder. Default target is `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`. For a different location, run the BAT from CMD with your project path in quotes as its argument.
4. The installer backs up replaced source files, copies the cumulative application update, runs Python tests and builds the web frontend. It preserves credentials and databases. Stop if validation fails.
5. Start `START_INSIGHTS.bat` in your existing project and press Ctrl+F5 in the browser.
6. On Dashboard, click Refresh Market Data. Old cached snapshots retain the old meter until refreshed. Confirm the same signed score in the gauge and rule breakdown, see the session-open move and candle timestamp, and check each index's stale/historical label.

## Manual verification (CMD in your existing project)
```
.venv\Scripts\python.exe -m unittest insights.tests.test_dashboard_trend -v
.venv\Scripts\python.exe -m unittest discover -s insights\tests -q
.venv\Scripts\python.exe -m unittest discover -s tests -q
cd web
npm run build
```

Changed runtime files: `insights/dashboard_trend.py`, `insights/service.py`, `web/src/main.js`, `web/src/trend_meter.js`. Regression tests: `insights/tests/test_dashboard_trend.py`.
