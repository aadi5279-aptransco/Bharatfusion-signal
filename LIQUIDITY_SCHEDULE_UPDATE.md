# Intraday, F&O Stocks and Swing Trades: scheduled liquidity lists

This update includes all previous Scanner, Positional, EMA9 and FII improvements.

## Schedule (IST)

| Time | Action |
| --- | --- |
| 09:45 | Quote discovery across the full available cash-stock master; save liquid-stock lists; evaluate their strategies |
| 10:00, 11:00, 12:00, 13:00, 14:00, 15:00 | Refresh the broad quote discovery and replace lists with the new liquid stocks |
| Each five-minute bucket from 09:45 through the trading session | Evaluate Intraday, F&O and Swing strategies only on their stored selections |

The existing holiday/session gate applies. The scheduler and broker jobs do not overlap. A delayed tick runs the current five-minute bucket; it does not replay every missed bucket. A late startup discovers the latest due liquidity slot only. These are target schedules: provider latency and other jobs can delay completion. Keep the backend running.

## Liquidity selection

- Uses the full available NSE/BSE cash master, not the old 30-stock discovery slice. Quotes are requested in batches of at most 500, separated by exchange to avoid security-ID collisions. There is no 500-stock total discovery cap.
- Valid positive quotes fetched within 120 seconds are required. Session volume must be at least 100,000 shares, price at least INR 20, and session volume × last price at least INR 1 crore.
- Rank by session volume × last price, then volume. This is a **turnover proxy**, not exact traded value, bid/ask depth or proof of execution liquidity. It intentionally does not require a bullish/bearish setup before selection.
- Intraday and Swing use the same top cash-equity list. F&O independently takes top liquid stocks with mapped futures/options. A quiet direction does not exclude an otherwise liquid stock.
- Each list is capped by the existing `INSIGHTS_MAX_SYMBOLS` setting (default 30; maximum 200). This caps strategy work, not broad discovery. Raising it increases strategy requests and can make cycles exceed five minutes.
- The full-master discovery for these three tabs does not apply `INSIGHTS_WATCHLIST`. Other modules retain their existing settings. If the provider only exposes a narrower instrument master, coverage reflects that actual universe; the application cannot claim exchange-wide coverage beyond its master.
- Each tab displays last successful refresh, mapped/quoted/missing counts, selected count and refresh errors. Quotes do not currently expose an exchange trade timestamp through the adapter, so a fresh HTTP quote is not proof of a recent trade in a suspended/illiquid instrument. Existing strategy freshness checks still apply.

## Between refreshes and failures

- No broad quote discovery, old gainers/losers fallback or full-universe stock-history fallback occurs in the three five-minute strategy paths.
- Stored lists are saved atomically in `liquidity_shortlists.json` under the existing Insights data directory and restored on restart. Identity includes exchange segment plus security ID.
- A failed scheduled quote refresh retains only the previous **same-day** selection, with a visible failure label. It is not retried every five minutes; the next scheduled broad slot retries. A successful scan with no liquid stocks clears the list. An empty list stays empty rather than expanding the universe.
- Missing quotes produce partial coverage and selections from observed valid quotes. Prior-day lists are not reused for a new trading day.
- Swing re-evaluates its existing strategies every five minutes using completed daily/weekly candles; it does not fabricate current-day completed bars. Its signals can remain unchanged during the session. The intraday Swing path does not run or overwrite Multibagger research.
- The after-close Multibagger research batch remains separate. Swing evaluation within that batch is restricted to the latest same-day liquidity selection. Index Options, Positional and Scanner retain their own schedules. Benchmark/index requests needed by strategies are distinct from broad stock discovery.

## Windows installation

1. Stop the running application/backend.
2. Download this branch's ZIP and extract it into a separate folder.
3. Double-click **UPDATE_LIQUIDITY_SCHEDULE.bat** in that extracted folder. It targets your existing installation:
   `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`.
   For another folder, pass its full path as the batch file's argument.
4. The updater backs up replaced source files, copies Insights/frontend code and the updated scheduler test, then runs both test suites and the frontend build. Credentials, settings, databases and other local test files are preserved. If validation fails, retain the output and resolve it before restarting.
5. After the success message, launch **START_INSIGHTS.bat** from your existing project, refresh the browser with **Ctrl+F5**, and inspect the new **Scheduled liquidity shortlist** panel in all three tabs.

## Verification

During a trading session, compare the liquidity refresh timestamp with the strategy update timestamp. Between 10:00 and 11:00, the strategy timestamp should advance every five minutes while the liquidity timestamp stays fixed; at 11:00 it should refresh. Check the selected/quoted/missing counts and any errors. The F&O selected set may differ from the cash selection.

Manual automated checks from the project folder:

```bat
.venv\Scripts\python.exe -m unittest insights.tests.test_liquidity_shortlist insights.tests.test_staged_scheduler -v
.venv\Scripts\python.exe -m unittest discover -s insights\tests -q
.venv\Scripts\python.exe -m unittest discover -s tests -q
cd web
npm run build
```

Correctness tests use controlled quote data. Live Dhan throughput and your Windows UI still need verification on your installation; no performance or profitability guarantees are implied.
