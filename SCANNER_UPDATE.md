# Indian Stock Scanner update

This branch includes the earlier FII holdings, stock-deal, BTST import and swing fixes, plus a Finviz-style Indian equity scanner.

## Install on your existing Windows application

1. Stop the backend and close the application. Download this branch using GitHub **Code → Download ZIP**.
2. Extract the ZIP into a separate folder, e.g. `H:\Scanner_Update`. Do not extract over the installed project.
3. Open the extracted folder containing `UPDATE_SCANNER.bat`. Double-click it. It targets `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights` by default. For another location, open CMD in the extracted folder and run:
   ```bat
   UPDATE_SCANNER.bat "H:\your\actual\project"
   ```
4. The updater backs up replaced source files under the installed project's `update_backups`, copies the complete Insights Python modules and frontend JavaScript/CSS (including the new scanner module), runs both test suites and builds the web app. It preserves `.env`, credentials, settings, databases and unrelated local files. If validation fails, keep the output and resolve the error before restarting. Source-copy failures roll back; test/build failures leave the backed-up new sources in place for diagnosis.
5. After **Update installed and tests/build passed**, run `START_INSIGHTS.bat` in your existing project. In the browser press **Ctrl+F5** and open **Scanner** in Market Insights.

The updater requires your existing working Python environment and installed web dependencies. If dependencies are missing, in CMD run these from your existing project, then rerun the updater:
```bat
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
.venv\Scripts\python.exe -m pip install -r requirements-insights.txt
cd web
npm ci
```

## First scan and verification

1. Open **Data universe & refresh**. Start with **F&O cash stocks**, **NSE**, batch size **25**. Click **Load / refresh first batch**. Dhan credentials and active data access are required.
2. Wait for COMPLETE; the table refreshes every 10 seconds. Check loaded count, candle date and source errors. Holiday configuration is used for freshness; a missing calendar is shown as unknown.
3. Select **Video: liquid uptrend**. It applies F&O eligibility, close ≥ ₹50, previous 20-session average volume ≥20 lakh and price above SMA20/50/200. Zero matches is valid; reset filters to inspect the loaded universe.
4. Change Descriptive / Fundamental / Technical groups, sort a column, change table views, save a named preset and export the filtered CSV. Presets are local to your browser.
5. Click **Load next batch** to include more stocks. Choose **All listed cash stocks** for the broader mapped NSE/BSE universe, then restart from the first batch. Maximum batch size is 500. Counts and filters cover loaded stocks only. Changing the universe or crossing a calendar day requires a new first batch. Failed stocks are listed; three consecutive source errors stop the batch. Cancel stops between requests.

## Data interpretation

- This is a completed-daily-candle screener, not a live intraday screener. Current-day candles are excluded before 15:40 IST. Table polling reads saved results; it does not fetch live prices. Cached features are reused for the latest expected completed session.
- Relative volume divides the latest completed volume by the preceding 20-session average, excluding that latest session. Day change compares completed closes. SMA200 and 52-week levels remain blank without sufficient history. Missing fields cannot pass filters.
- Sector, industry, index membership and fundamentals require a dated CSV import. Dhan OHLCV does not provide these values here. Open **Import sector, index and fundamental data**, download the template, fill it from your source and upload. Required columns: Exchange (NSE/BSE), Security ID (Dhan cash ID), As of (YYYY-MM-DD), Source (HTTPS URL). Optional columns: Sector, Industry, Indices (pipe-separated), Market cap cr, PE, ROE, Debt equity, Dividend yield. Amounts are INR crore and percentages are numeric percentages. Imports replace metadata only. Dates older than 180 days or in the future are rejected; stored metadata expires after 180 days. Source URLs are recorded, not independently verified.
- The video's US Healthcare sector is not automatically assigned to Indian companies. Select a sector after importing metadata. Some broad-universe rows use Dhan company names where no ticker is mapped. The existing Analyse tab may not support every broader-universe stock.
- No orders are placed.

## Manual checks

From the installed project folder:
```bat
.venv\Scripts\python.exe -c "import insights.service; print('Service import OK')"
.venv\Scripts\python.exe -m unittest discover -s insights\tests -q
.venv\Scripts\python.exe -m unittest discover -s tests -q
cd web
npm run build
```
