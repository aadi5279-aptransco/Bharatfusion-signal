# EMA9 + trendline + volume addition

This cumulative update preserves the Scanner, FII, Positional and earlier fixes. The new strategy is **EMA9 Trendline + Volume** inside the existing **Positional** tab, with separate **1H / 1D / 1W / 1M** rows and a timeframe filter.

## Install on Windows

1. Stop your running backend/application.
2. Download this branch's ZIP and extract it into a separate folder (do not overwrite your installed project manually).
3. Double-click **UPDATE_EMA9_POSITIONAL.bat** in the extracted folder. Its default destination is:
   `H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights`.
   For a different destination, run the batch file from CMD with the project folder as its argument.
4. Wait for **Update installed and tests/build passed**. The existing installer backs up replaced source files and preserves `.env`, settings and databases. If validation fails, keep the output and do not restart until resolved.
5. Start **START_INSIGHTS.bat** in your existing project. Press **Ctrl+F5** in the browser. Open **Positional**, choose **EMA9 Trendline + Volume**, and choose a timeframe or All timeframes. Leave READY-only unchecked to see research watches.

## Exact rules

- At least 60 closed OHLCV bars per timeframe. EMA9 seeds with the first close (`ewm(span=9, adjust=False)`).
- Pivot high: maximum over five bars on each side, usable only once its five right-hand bars close. Equal highs follow the PDF's reference tie behavior. Maintain the last two successively lower pivots; an equal/higher pivot resets the chain. Require at least ten bars between anchors (PDF optional safeguard).
- The latest close must be above the projected descending line, while the preceding close was at/below that same line at the preceding bar. Close must also exceed EMA9.
- Volume must be strictly greater than 1.5 times the **preceding 20 candles'** mean. This follows the written PDF rule. The sample code's unshifted average includes the breakout candle and is inconsistent with that rule; this implementation intentionally excludes it.
- SL is the lowest low of the **previous ten candles**, excluding the signal candle. Risk must be positive and no more than 15% of entry (PDF optional safeguard). Mean traded value of the preceding 20 bars must be at least INR 1 crore (app liquidity safeguard).
- Entry is the closed signal candle's price reference. **T2 is the specified 3R target. T1 is an explicitly added 1.5R planning level** to fit the application's two-target table. Neither price is a guaranteed fill. Optional EMA exit and swing-low trailing are disabled, matching the PDF's default `exit_on_ema=false`.
- Rows show timeframe, signal time, entry/SL/T1/T2, EMA9, trendline value, volume ratio, confirmed pivot timestamps/prices, and reason. The stable key includes exchange, security ID, timeframe and signal candle; polling/restarts replace that row rather than duplicating it. No alert delivery or order placement is added.

## Timeframes and data coverage

- The existing five-minute worker checks the selected stock universe. EMA9 daily history is requested with a ten-year lookback and cached until the next completed daily session. Hourly history uses a 90-day request and refreshes only when a new full hour closes. These are requested ranges, not a guarantee the provider supplies that much history.
- 1H uses provider 60-minute candles aligned to the Indian 09:15 session. The last 15-minute session stub is excluded. A missing/misaligned latest hour produces a diagnostic, not a signal.
- 1D ignores today's candle until 15:40 IST. 1W uses Friday-ending aggregation; 1M uses calendar month-end aggregation. Both use first open, maximum high, minimum low, last close and summed volume. The initial potentially partial bucket and the current unfinished bucket are excluded. A known Friday/month-end holiday allows the last trading session to close the bucket. Signal-end timing uses the last underlying daily candle, even when the period label falls on a holiday/weekend.
- Current-year missing sessions are checked against the configured holiday calendar. Earlier years' holiday calendars are not available through the current configuration, so internal historical session completeness cannot be fully verified. Missing entire periods, duplicates, nonfinite data and zero-volume candles are rejected. No interpolation or fabricated history is used.
- Insufficient monthly/weekly history is shown under **Rules and data coverage → EMA9 timeframe coverage**. Sixty monthly candles require about five years of usable history. A source error affects the reported timeframe; it does not silently create a result. Overall status may be PARTIAL when some timeframes lack sufficient history.
- Other Positional strategies keep their existing history lengths and risk rules. EMA9's extra initial history requests can lengthen a cycle; the existing non-overlap lock, 240-second budget and displayed coverage still apply.

## Adjusted-data requirement

The PDF requires split/dividend-adjusted OHLCV. The existing Dhan adapter does not expose an adjustment guarantee, and this update does not manufacture corporate-action adjustments. Therefore EMA9 matches default to **RESEARCH ONLY — VERIFY ADJUSTMENTS**, including their indicative levels. This limitation applies to the new EMA9 strategy only.

If you independently verify that your connected source provides the required adjusted history for the requested timeframes, you can record that confirmation in your existing `.env`:

```dotenv
INSIGHTS_EMA9_ADJUSTED_DATA_CONFIRMED=true
```

Restart the backend after changing it. This is a user attestation, **not** a switch that adjusts the prices. Do not enable it simply to clear the label. Even with confirmation, READY requires the complete post-signal 5m price path, a fresh close within the existing 1% entry-review band, and no observed SL/target touch. Older weekly/monthly signals may predate the available 5m history and remain WATCH. No multi-year profitability backtest or live Dhan verification has been performed for this implementation.

## Test

The updater runs the full tests/build. For focused checks, open CMD in your installed project:

```bat
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
.venv\Scripts\python.exe -m unittest insights.tests.test_ema9_trendline -v
.venv\Scripts\python.exe -m unittest insights.tests.test_positional -v
```

In the application, verify that older strategy filters still work, all four EMA9 timeframe diagnostics appear for scanned stocks, and no incomplete hour/week/month generates a signal. A zero-match result is valid. These tests check implementation correctness, not profitability.
