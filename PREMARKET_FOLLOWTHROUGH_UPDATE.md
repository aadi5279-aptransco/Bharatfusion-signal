# Pre-Market opening follow-through

Adds a lower section in **Pre-Market 8 AM** for 09:45 and 10:00 IST breakout/breakdown assessments. It freezes only the displayed gainers and losers, deduplicates symbols and persists that watchlist for the trading day. It never substitutes a full-universe scan. The previous session must match the configured exchange calendar; mixed or stale watchlists cannot qualify.

## Schedule and interpretation

- From 09:15, an independent worker freezes the valid morning list and warms daily history for those stocks.
- At/after 09:45 it fetches and trims all inputs to completed candles ending no later than 09:45.
- At/after 10:00 it repeats the process using the same symbols and the new 10:00 cutoff. Both reports remain visible below the original lists.
- A start after 10:00 runs only the 10:00 assessment. After 10:15 neither pass is backfilled. This update implements the requested two assessments, not continuous monitoring after 10:00.
- These are scan start/cutoff times, not guaranteed delivery deadlines. Broker response time and other scans can delay completion. Each report displays its cutoff, completion time, per-stock errors and progress. A busy Dhan lock or missing data marks that stock unavailable for the pass; it does not invent data. Failed stocks alone may be retried, up to three attempts within eight minutes of the cutoff; successful stocks are not rescanned for that pass.
- The same broker lock is respected per data call to prevent overlapping Dhan requests. Existing scan rules and schedules are unchanged, but this adds data requests for up to 20 watchlist stocks and shares the broker's rate limits. Keep the backend running before 09:15.

## Morning entries

Reuses first-five-minute opening range, first-red-bar Fibonacci and the exact Daily + 15m Momentum Query in both directions. Also adds a symmetric first-15-minute range rule requiring two completed five-minute closes beyond the range. Qualifying entries additionally require:

- Stock price at least ₹20, session volume at least 1 lakh and turnover proxy at least ₹1 crore.
- Five-minute RVOL at least 1.5, ADX at least 20.
- Price/VWAP and EMA20/EMA50 alignment in the entry direction; RSI at least 55 for BUY or at most 45 for SELL.
- Complete contiguous opening-session candles, completed indicator history and fresh prior-session daily data.
- Finite positive entry/SL/T1/T2, targets on the correct side and risk no more than 6% of entry.

Results show stock, strategy, BUY breakout / SELL breakdown, cash-stock entry, T1, T2, SL and reasons. Existing strategy target rules are retained. The added 15m range strategy uses the confirmed close, a structural/ATR stop and 1.5R/2.5R targets. Conflicting confirmed directions suppress an entry. No guarantee of fills, profitable trades or multibagger returns is implied. Price levels are research references, not broker orders or option premiums; confirm the instrument tick size and current executable price before trading.

Metrics include RSI, ATR, opening gap, session volume, turnover proxy, RVOL, ADX, VWAP and EMA20/50. RVOL is the existing previous-20-bars heuristic, not a matched-time institutional-flow measure. These checks do not establish actual bid/ask liquidity or aggressor order flow.

## Strategy coverage is explicit

The report evaluates existing 09:45 Fibonacci/SMC evidence, daily swing, swing opportunities, swing guide, positional daily templates, R1/S1 Supertrend and Gann/wave context. Longer-term matches are context, not automatically converted to morning intraday prices. No missing benchmark or derivatives information is inferred.

Strategies with incompatible requirements are shown separately: the legacy opening-range VWAP strategy starts at 10:15 and requires benchmark/sector comparisons; BTST needs the closing window; 12:45 Fibonacci needs that later reference; derivatives need contract/premium/OI inputs; Multibagger/QGLP require dated fundamentals; EMA9 requires the positional scanner's adjusted-data confirmation. Executed order-flow research remains Index Options only. The UI therefore shows what was checked, what matched, and what is unavailable or not due, rather than claiming every strategy is applicable at 09:45.

Saved assessments older than ten minutes, from another date or outside the verified session are labelled historical. Their levels remain visible for review but are excluded from new research notifications. Current completed matches can notify as **Pre-Market 8 AM** using the existing notification inbox. The same strategy/symbol/direction is deduplicated for the day, so the 10:00 table may change without another identical alert. Stops/targets in saved reports are not continuously monitored after the two passes; always verify current conditions.

## Install

1. Stop the application/backend.
2. Download this branch ZIP and extract into a separate folder.
3. Run `UPDATE_PREMARKET_FOLLOWTHROUGH.bat`. Default target: `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`.
4. Wait for backups, tests and frontend build to pass. Do not restart on a validation failure.
5. Run `START_INSIGHTS.bat` from the installed project, press Ctrl+F5, and open **Pre-Market 8 AM**.
6. Confirm the previous-session list and configured holiday calendar before 09:15. At 09:45 and 10:00 check the lower section's report status, source errors, cutoff and reasons. No confirmed entry is a valid result.

New files: `insights/premarket_followthrough.py`, `web/src/premarket_followthrough.js`, `insights/tests/test_premarket_followthrough.py`. Integrations: service lifecycle, a cached API endpoint, tab rendering and notification source registration. Persistent state: `premarket_followthrough.json` under the application's existing data directory. This cumulative update preserves prior features and credentials.
