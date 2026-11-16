# Pre-market setup selection and Birbull comparison

## What the evidence establishes
Your screenshot dated 16 November 2026 uses 13 November daily data, which is consistent with a Monday morning prior-session watchlist. It shows 40 assessed stocks out of 218 attempted (~18.3% coverage). That is not evidence that the other 178 stocks failed technical criteria; the old code combined broker/mapping failures and insufficient history without a per-stock explanation. ADANIENT is already visible as ADANI ENTERPRISES LIMITED. The screenshot alone cannot diagnose the other seven Birbull names.

Birbull's public pages describe price action, volume, momentum, resistance/consolidation breaks and several chart patterns. They do not disclose the screening thresholds or establish why the eight supplied names were selected on 16 November. Their webinar page marks its signal examples as illustrative. A single list cannot uniquely identify an algorithm. We have not recovered their private formula, independently verified the dated list, or replayed those eight stocks against licensed daily data in this development environment.

Sources checked:
- https://birbull.com/
- https://signup.birbull.com/
- https://dhanhq.co/docs/v2/ (Data APIs: 5 requests/second; this batch now adds spacing and one bounded retry. This does not govern other applications sharing the account.)

## What your existing code actually did
`insights/strategies/premarket.py` required 55 completed daily bars, requested 180 calendar days, and ranked a bounded mapped stock universe. It awarded:
- Absolute previous-day percentage move x7, capped at 40 points.
- A close beyond the prior 20 daily highs/lows: 25 points.
- Directionally aligned close/EMA20/EMA50: 20 points.
- Prior-session volume >=1.5x preceding 20-day average: 15 points.

It split positive and negative daily changes into two top-ten lists, ranked by score rather than percentage. Consequently the old labels “top gainers/losers” were misleading. A flat compression day could be omitted completely. The update preserves these momentum ranks under clearer labels and adds an independent setup shortlist.

## New research rules (not Birbull's formula)
Only completed, finite, valid daily OHLCV bars for the expected previous trading session qualify. The holiday calendar must be configured. UTC timestamps are converted to IST before selecting dates; future bars cannot enter a morning scan.

Liquidity gate: close >=Rs20, mean close x volume over prior 20 sessions >=Rs5 crore, last-session close x volume >=Rs2 crore. These are turnover proxies, not exact traded-value data. Reject raw daily jumps above 20% for corporate-action/data review; this does not certify adjusted data.

Candidate families:
1. Compression near a 20-day level: close within 0.5 daily ATR of resistance/support, aligned close/EMA20/EMA50, plus NR7, inside day or five-day high-low range <=2 ATR. Base score 65.
2. Volume-confirmed continuation: close beyond prior 20-day high/low, extension <=0.75 ATR, RVOL >=1.5, aligned EMAs, and close in directional outer 30% of the day's range. Base score 75.
3. Two-sided range expansion watch: strict NR7 (range smaller than each of prior six) or strict inside day (lower high AND higher low). No bullish/bearish prediction. Score 55; 65 if both apply.

For directional candidates add 10 for NR7, 5 for inside day and 10 for RVOL >=1.5, capped at 100. Rank at most 12 unique stocks by their highest setup score; ties use symbol order. Scores are heuristic ordering, not win probabilities. No claim of superior returns is established; thresholds need historical and forward validation.

Show watch-above/watch-below reference boundaries and the matched rule. These are NOT pre-market entry, target or stop orders. Selected stocks join the frozen prior-day momentum list for existing 09:45/10:00 analysis. A new prior-day range-break strategy requires two completed 5-minute closes and all existing liquidity/RVOL/ADX/VWAP/EMA/RSI gates. It calculates cash-stock entry, T1/T2 and SL only after confirmation; other existing strategies remain independently identified.

Every attempted symbol now has a diagnostic status: setup match, no setup, invalid/short history, stale data, or source error. Coverage below 90% is visibly flagged. The scan's universe cap and optional user watchlist remain in effect. Rejected broker requests are retried once; persistent entitlement, mapping or data issues are not bypassed. The exact cause of the screenshot's low coverage is still unverified.

## Install on Windows
1. Close the running application.
2. Download this update's GitHub ZIP and extract into a separate folder.
3. Run `UPDATE_PREMARKET_SETUPS.bat`. Default installed project: `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`. The updater backs up overwritten source files, preserves credentials/databases, runs tests and rebuilds the frontend. It includes the preceding dashboard and index-options fixes.
4. If validation succeeds, start the existing `START_INSIGHTS.bat`; press Ctrl+F5 in your browser.
5. The new setup list appears after the next pre-market/after-close scan. Old caches do not contain setup fields; the next 08:00 scan regenerates old-version caches. Existing same-day frozen monitoring lists stay frozen.

## Reproduce the eight-stock comparison on your Dhan account
This is read-only, uses the 08:00 IST cutoff on 16 November, and checks our rules rather than claiming Birbull's formula. Close the app first if using `--refresh-watchlist`. From Windows CMD:

```
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
.venv\Scripts\python.exe -m insights.premarket_compare --date 2026-11-16 --symbols EICHERMOT HINDUNILVR ASIANPAINT BHARTIARTL SHRIRAMFIN GRASIM HINDALCO ADANIENT --refresh-watchlist
```

The output is saved as `premarket_comparison.json` in your project folder. It records each stock's prior-day change, old momentum score, new setup evidence and watch levels, or a missing-data/mapping status. The optional refresh rebuilds the full capped watchlist cache for that historical date; restart the application to load it. Change `--date` for a different watchlist date. Do not interpret historical results as today's live entries. Symbols resolve through actual Dhan aliases, never guessed name matching.

After refresh, open Pre-Market 8AM and check “Breakout / breakdown setup candidates” and “Per-stock scan diagnostics.” Share the comparison JSON if a stock still appears absent; it contains no token fields.

## Verification
```
.venv\Scripts\python.exe -m unittest insights.tests.test_premarket_setups -v
.venv\Scripts\python.exe -m unittest discover -s insights\tests -q
.venv\Scripts\python.exe -m unittest discover -s tests -q
cd web
npm run build
```

New files: `insights/premarket_setups.py`, `insights/premarket_compare.py`, `insights/tests/test_premarket_setups.py`. Integration: premarket strategy, service, followthrough and Pre-Market UI.
