# Verified Codebase Audit — BharatSignal Fusion 0.7.1

Audit date: 2026-11-09. Input: user's `BharatSignal_Fusion1.zip` and individually accessible GitHub repository `aadi5279-aptransco/Bharatfusion-signal` (main).

## Existing stack

- Original launcher: `START.bat` → Python 3.11 `app.py`.
- UI: Tkinter/ttk desktop notebook and Tk Canvas dashboard (`app.py`, `market_dashboard.py`, `compact_view.py`, `forecast_chart.py`). Not a Flask/React fork of OpenAlgo.
- Data: Dhan v2 read-only REST transport (`data.py`), official Dhan-hosted detailed instrument master, in-process/multi-day Pandas OHLCV, local SQLite cache.
- Rules/strategies: `engine.py`, `timed_scans.py`, `breakout.py`, `strategy_rules.py`, `strategy_service.py`, `discovery_rules.py`, `rsi_strategy.py`, `option_research.py`.
- Additional features: `paper_watch.py` opt-in paper alerts, `market_safety.py` dated ban/delivery/event gates, `scanx_source.py` historical external-page dependency (not reused by Market Insights), `ml_engine.py` LightGBM/XGBoost, `sentiment.py` optional FinBERT, `kronos_adapter.py` optional forecasts, auto-training/forecast queues.
- Optional dependencies are in `requirements-ai.txt` and `requirements-kronos.txt`; mandatory `requirements.txt` lists NumPy/Pandas/tzdata.
- Original tests: `tests/` contains 11 test modules; **181 passed** using Python unittest in this environment before modification.

## Upgrade decisions

1. **Do not replace `app.py` or old modules.** A parallel `run_insights.py` entry point builds a localhost-only Flask API and serves a separately built React UI. Existing `START.bat` remains the original app.
2. **New DhanSDK plugin**, `insights/brokers/dhan.py`, only exposes historical candles, official instrument master mapping, option expiry/chain and read-only quotes. No order methods are wired into the new service.
3. **Separate SQLite**, default `~/.bharatsignal-insights/insights.sqlite`, storing immutable signal keys, observed outcomes, historical validation metadata. Original SQLite research/cache data remains untouched.
4. Pure deterministic research rules: `insights/indicators.py`, `insights/strategies/{equity,futures,options}.py`; explanations are produced only by triggered checks.
5. Five-minute background scheduler with 09:20/10:00/15:00 gates, verified holiday calendar required, and no overlapping jobs. Frontend reads cached snapshots. Incomplete or stale input yields no signal.
6. React supports six Market Insights tabs + Track Record, sidebar, dark/light UI, option OI charts and licensed completed-candle price charts.

## File list added

`run_insights.py`, `.env.example`, `.gitignore`, `requirements-insights.txt`, `INSTALL_INSIGHTS.bat`, `START_INSIGHTS.bat`, `INSIGHTS_README.md`, `AUDIT_INSIGHTS.md`, `insights_holidays.example.json`, `insights_sector_map.example.json`, `insights/{api.py,config.py,db.py,indicators.py,service.py,backtest.py,validate.py}`, `insights/brokers/{base.py,dhan.py,streaming.py}`, `insights/strategies/{equity.py,futures.py,options.py}`, `insights/tests/*`, `web/{index.html,package.json,vite.config.js,src/main.js,src/styles.css}`.

## Security and behavior caveats

- No order routes or calls exist in the new code; `ENABLE_ORDER_PLACEMENT=true` aborts startup.
- The user's `.env` file (plain text) is excluded from the distributed ZIP. Users must configure Dhan credentials locally; plain text `.env` is not encrypted at rest. Use Windows per-user access controls or OS credential storage if that is required.
- Dhan token renewal is only attempted for an active, eligible Web-generated token, not guaranteed for every login mechanism. No user credentials were provided during this audit.
- Historical broker data and WebSocket streaming were **not exercised against a real Dhan account**. The provided WebSocket collector is optional and not part of scheduled scans until account-level tests succeed.
- No exchange holiday calendar was assumed. The scheduler fails closed until one is configured.
- Intraday/BTST/options strategies remain **research-only and backtest-unvalidated**. The preliminary backtest CLI deliberately sets `eligible=0` until independent walk-forward tests and realistic trade data pass. Options premium freshness and licensed historical IV percentile are not established.
- External ScanX/NSE public-page use still exists in the preserved legacy application, but the new Market Insights pipeline does not scrape those sites.
- Flask and Node/Vite dependencies could not be downloaded in the sandbox; therefore the actual HTTP server and React build were **not runtime-tested** here. Python source compilation, Node JavaScript syntax, new unit tests and the original unit suite were checked.
