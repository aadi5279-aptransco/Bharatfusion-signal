# European market dashboard update

Adds DAX (Germany), CAC 40 (France), EURO STOXX 50 (Eurozone) and FTSE 100 (UK) to Dashboard. The UK is European context, not an EU member.

Each card displays index points, point/% change versus the provider's previous close, quote time and fetch time in IST, delayed/stale status, normal session hours in IST and the provider's session window. Normal hours adjust automatically for European daylight saving (typically 12:30 IST opening in summer and 13:30 in winter). Exchange holidays and exceptional closures are NOT independently verified; scheduled hours are labelled accordingly, never presented as a confirmed open exchange.

The feed is Yahoo Finance's public chart endpoint, not Dhan and not a guaranteed real-time service. Quotes are explicitly delayed. It requires no new key but may be unavailable or rate-limited. A licensed real-time feed would be required for guaranteed real-time coverage. No causal prediction of NIFTY or automatic trade filter is inferred from European changes. Data is for personal dashboard context only; observe provider usage terms.

## Isolation

A separate daemon worker fetches the four symbols with an 8-second per-request timeout, then waits 60 seconds. It never acquires the Dhan scan lock, modifies strategy inputs or changes entries/targets/SL. The dashboard polls only the cached local API. Each source failure is contained to its own card. Last successful data remains timestamped and marked stale on errors, old quotes or missed refreshes. The worker runs independently of Indian trading hours and stops with the service. Closing Dashboard stops its browser polling; other tabs do not mount the component.

## Install

1. Stop the running backend/application.
2. Download this branch's ZIP and extract to a separate folder outside the installed project.
3. Double-click `UPDATE_EUROPE_MARKETS.bat`. Default destination: `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`. For another folder, run `UPDATE_EUROPE_MARKETS.bat "YOUR_PROJECT_PATH"` from CMD in the extracted folder.
4. The cumulative updater backs up replaced files, preserves credentials/database, runs tests and builds the frontend. It also installs the existing order-flow dependency so earlier updates remain supported. Do not restart if validation fails.
5. Run `START_INSIGHTS.bat` from your existing installation. Press Ctrl+F5 and open Dashboard.
6. Allow approximately one minute for the European cards. Check quote time, not just fetch time. On weekends, old last-session values are expected and must say stale/last available.

The key additions are `insights/europe_markets.py`, `web/src/europe_markets.js` and `insights/tests/test_europe_markets.py`. Service lifecycle, one read-only API route and Dashboard mounting are the only integrations. Existing trading logic is unchanged.

Primary references:
- https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html
- https://cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours
- https://www.londonstockexchange.com/en/resources/faqs/personal-investing

Validation covers percentage calculations, missing/invalid values, daylight saving, weekends, stale data, source failures and API isolation. Live source availability on your Windows network remains dependent on the provider/network.
