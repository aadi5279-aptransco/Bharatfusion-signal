> Version 0.2 update: Dhan's current OpenAPI specification exposes /data/companyinfo. The app now requests company overview, ratio and shareholding snapshots for momentum candidates, applies limited sector-aware fundamental checks, forecasts up to 20 qualifying stocks plus indices, and displays predicted charts. See README.md for the current implementation and limitations. Historical platform comparisons below remain public-page feature descriptions.

# Platform review and combined design

Reviewed public pages on 25 October 2026. This is a feature review, not a subscription-product test, verification of performance claims, or access to proprietary algorithms.

| Platform | Publicly described strengths | Useful design carried into this app |
|---|---|---|
| NeoTrader | Scoring/ranking of stocks and indices, trade dashboards, breakout filters, entry/exit/stop-loss levels, multi-timeframe assessments | Ranked stocks/indices, explained technical agreement, higher-timeframe context, reference entry/stop/targets |
| Super Investing | Scorecards spanning fundamentals, valuation, quality and technicals; screening; research summaries and sentiment context | Inspectable score components and evidence explanations; fundamental/news inputs deferred because Dhan candle data does not supply them |
| Birbull | Breakout and chart-pattern tools, entry/exit strategies, live charts, PC/mobile alerts | Breakout/retest filter, local candle chart and de-duplicated desktop sound/activity alerts |
| Kronos | Open financial candlestick foundation model with pretrained models and prediction API | Optional local future-close scenarios; same-session time alignment and separate experimental forecast panel |

The combination to pursue is **broad live scanning + transparent evidence + optional model forecasts + measured risk and validation**. Copying marketing accuracy claims or combining every indicator would not establish an edge.

## Implementation order

1. Delivered research version: mapped stock/index universe, background closed-candle scans, chart and rankings, evidence/WAIT reasons, reference targets, local journal and Kronos forecasts.
2. Local acceptance: verify timestamp/candle parity with Dhan during a live session; record complete scan latency and successful-symbol coverage; verify invalid-token, network outage and stale-data handling on the user's Windows PC.
3. Validation: fixed-rule cost-aware walk-forward trading simulator and forward paper journal; compare rules-only, Kronos-only and combined models on the same unseen periods. Model forecast accuracy alone is not trading profitability.
4. Production data service: WebSocket reconnection, incremental candle builders, full exchange calendars, quote/spread/turnover filters and point-in-time universe tracking.
5. Expand only with evidence: sector/relative strength, explicit BOS/CHoCH/CRT state machines, options risk analytics and licensed fundamentals/news sources. Add each feature only if out-of-sample evaluation supports it.

## Public sources

- NeoTrader: https://neotrader.in/
- Super Investing: https://www.superinvesting.ai/ (public search-indexed landing-page content; direct page extraction did not yield text)
- Birbull: https://birbull.com/
- Official Kronos source, API, model zoo and limitations: https://github.com/shiyu-coder/Kronos
- Kronos paper: https://arxiv.org/abs/2508.02739
- Dhan intraday candle intervals and payload: https://dhanhq.co/docs/v2/historical-data/
- Dhan master fields: https://dhanhq.co/docs/v2/instruments/
- Dhan API rate limits: https://dhanhq.co/docs/v2/
- Dhan quote snapshot API: https://dhanhq.co/docs/v2/market-quote/
- Dhan WebSocket API (future streaming upgrade): https://dhanhq.co/docs/v2/live-market-feed/

Website feature descriptions do not establish independently audited win rates. Price-volume patterns cannot identify the beneficial owner of trades. Neither the three commercial products nor Kronos's research benchmarks guarantee profitable NSE intraday results.


## Version 0.3 implementation
Added local LightGBM/XGBoost classifiers, chronological Optuna tuning, FinBERT feed sentiment, native TreeSHAP explanations and measured sector-index dashboard. These are original research features; no proprietary platform code, models, or accuracy claims are reproduced. See README for exact gates and limits.
