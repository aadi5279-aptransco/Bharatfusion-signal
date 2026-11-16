# F&O Stock Options: at most eight qualified stocks

The tab now publishes at most eight distinct underlyings, ranked after all stock-option rules. It never pads the list to eight. Conflicting CE/PE directions for the same stock are rejected. Separate unranked opening/Fibonacci tables are hidden in this tab; Index Options is unchanged. Related backend watches are restricted to selected stocks.

Existing liquidity discovery schedule and five-minute strategy cadence remain unchanged. Every plan still needs futures price/OI buildup, cash RVOL >=1.5, a directional 5-minute structure break, aligned 15-minute/60-minute trends and the existing option-chain PCR check. New guards require current completed 15m/60m bars, a mapped option ID, positive option volume and OI, and a bid/ask spread <=2% (previously <=5%). The 60m confirmation may therefore remain unavailable early in the session.

Rule-quality score: 60 for passing the existing confluence gates; min(15, cash RVOL x5); min(15, futures OI percentage change x5); max(0, 10 x (1-spread_percentage/2)). Minimum score 75; maximum 100. Sort descending, use tighter spread as tie-break, then deterministic symbol order. These are disclosed research defaults, not a calibrated probability or a demonstrated high-win-rate strategy.

Each pick shows rank, score, spread, reasons and the existing strike/expiry/entry/T1/T2/SL research scenario. Quote timestamps remain unverified, and premium targets/stops remain hypothetical. No executed trades or verified win probabilities are invented. Fewer than eight (including zero) is valid.

## Windows installation
1. Close the existing app/backend.
2. Extract this GitHub ZIP into a separate folder.
3. Run UPDATE_FO_TOP8.bat. Default target is H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights. For a different target, pass the quoted folder path to the BAT from CMD.
4. The updater backs up changed source, preserves credentials/databases, runs tests and rebuilds the frontend. If validation fails, keep the error output and do not restart yet.
5. Start the existing START_INSIGHTS.bat, press Ctrl+F5 and open F&O Stocks. Wait for the next scheduled market-session scan after liquidity discovery.
6. Check that the count is <=8, ranks are ordered, stocks are distinct and rule scores are >=75. No matching stocks should show an explicit no-qualifiers status.

Tests: python -m unittest insights.tests.test_fo_selection -v (use .venv\Scripts\python.exe on Windows). Coverage includes spread/OI/invalid-data guards, cap/deduplication, conflict rejection, no padding and service publication of only selected names.

Runtime changes: insights/fo_selection.py, insights/service.py, web/src/main.js.
