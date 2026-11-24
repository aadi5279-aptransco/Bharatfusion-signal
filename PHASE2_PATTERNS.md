# Phase 2 — shared deterministic pattern engine

This change builds on Phase 1 commit `a9d471ee7d325128578ad07b453c9db6042331d8`.
Phase 3 models, training, automated orders and profitability claims are not included.

## Where it is in the application

Every tab now has a collapsed **Shared pattern engine · inspect a stock or index** panel.
Expand it, enter a Dhan-mapped symbol (for example NIFTY or a mapped company/ticker),
choose a timeframe and select **Check patterns**. This explicit inspection shares
one backend and one definition catalogue across all tabs. It does not start another
full-universe background scanner or silently replace existing strategy gates.

Each result includes direction, rule score, detection time in IST, confirmation
state, reasons, pattern geometry, invalidation and eligible entry/stop/target levels.
This is an underlying-price pattern view. Index levels are NOT option premiums.
It has one pattern target (measured move or configured R multiple), not two targets
invented from the Phase 3 execution optimizer.

**Geometry confirmed is different from entry ready.** The current application does
not have the complete dated circuit/ban/surveillance contract identified in Phase 1.
The app adapter therefore shows closed geometry but suppresses executable levels
when eligibility or tick size is unverified. It does not mark all stocks safe, infer
missing index volume or invent prices. The pure engine returns levels when its
verified-input contract is met. Existing research plans in other panels retain their
existing labels and behaviour; this update does not certify or repair their fills.

## Code ownership

| File | Responsibility |
|---|---|
| `patterns/types.py` | Frozen typed bars, context, pivots and output schema |
| `patterns/config.py`, `patterns/defaults.json` | Validated deterministic thresholds and example configuration |
| `patterns/math.py` | SMA-seeded Wilder ATR, EMA context, decimal tick rounding, confirmed ATR pivots |
| `patterns/candles.py` | All new candlestick morphology definitions |
| `patterns/charts.py` | All new chart geometry definitions and measured moves |
| `patterns/engine.py` | As-of filtering, trend/location, liquidity, confirmation and level generation |
| `patterns/legacy.py` | Existing PDF Morning Star and EMA9 geometry moved out of tab code with compatibility semantics |
| `insights/pattern_engine.py` | DataFrame/session adapter and the single application inspection entry point |
| `web/src/patterns.js` | Shared inspector, loading/error/empty states and IST display |

The new engine is pure: no broker calls, real-clock reads, database writes or global
mutable configuration. The application adapter owns those boundaries. Existing SMC,
OI and indicator strategies are not rewritten as new Phase 2 patterns. The legacy
PDF Morning Star is explicitly a compatibility definition, not silently relabelled
as the stricter new confirmed Morning Star.

## Catalogue and explicit geometry

| Family | Implemented definitions |
|---|---|
| Single candles | Doji, Dragonfly, Gravestone, Hammer, Inverted Hammer, Hanging Man, Shooting Star, bullish/bearish Marubozu, Spinning Top |
| Two candles | Bullish/bearish Engulfing, Piercing, Dark Cloud, bullish/bearish Harami, Tweezer Top/Bottom |
| Three candles | Morning/Evening Star, Three White Soldiers/Black Crows, Three Inside Up/Down |
| Reversals | Double/Triple Top/Bottom; Head and Shoulders/inverse, Rounding Bottom |
| Trendline formations | Rising/Falling Wedge, Bull/Bear Flag, Bull/Bear Pennant, Ascending/Descending/Symmetrical Triangle, Rectangle |
| Bases/breakouts | Cup and Handle, 52-week breakout, ATH breakout, Darvas Box, VCP, NR4, NR7, Inside Bar, Opening Range Breakout |

These are versioned quantitative definitions of discretionary labels, not a claim
that every chart technician will draw the same shape. Synthetic geometry tests
establish the implementation's defined cases, not predictive accuracy on live charts.

- Default Doji body <=10% of range; small body <=30%; long >=60%; Marubozu >=90%.
  Hammer-type long wick >=2 bodies and opposite wick <=10% of range. Candidate range
  must be 0.2–4 prior ATR. Tweezer tolerance is 0.1 ATR. Star body <=30% of first body.
- Candle trend is measured BEFORE the pattern: ten-bar change >=0.5 ATR. Reversal
  patterns require opposing prior trend; Marubozu requires aligned trend. Location
  must overlap a prior S/R, key EMA, prior VWAP or prior-day H/L within 1 ATR.
- Gaps are explicit. Default is a documented relaxed gap policy; strict gap checks
  for Piercing/Dark Cloud/Stars are configurable. First two intraday ending bars
  receive an opening caution. Neutral shapes do not create a directional entry
  until a closed breakout supplies direction.
- Default candle confirmation is the next closed bar beyond the pattern plus
  1.3x prior-20-bar volume. Either requirement can be disabled explicitly in config.
  Chart confirmation always needs the first closed breakout and 1.5x prior volume.
- Confirmed swing pivots require three left and three right bars and at least
  1 ATR separation from the previous opposite pivot. A confirmed pivot is never
  moved to a later extremum. Ambiguous outside-bar pivots are ignored.
- Double/triple extrema must be within 0.5 ATR; neckline is formed from intervening
  pivots. H&S uses unequal head depth and a fitted neckline through the two valleys
  (or peaks for inverse). Target is head/formation depth projected from neckline.
- Envelope patterns require at least three confirmed touches on each fitted side,
  bounded fit error and contained prior candles. Converging widths distinguish
  wedges/triangles; parallel countertrend channels require an earlier >=3 ATR pole
  for flags. Pennants need both a pole and convergence.
- Rounded bases use declining then rising third-means and a central minimum, not
  one instantaneous low. Cup/handle requires approximately matched rims, bowl depth
  and a separate handle retracing at most 33% of depth. These are deterministic
  approximations; human visual validation remains appropriate.
- VCP uses three shrinking alternating swings, upward price progress and drying
  volume. Darvas requires confirmed internal top/bottom and a later breakout.
- NR4/NR7 use the prior candle's strict narrowest range; Inside Bar uses a prior
  mother candle. ORB requires the actual 09:15 opening grid, not the first available
  bars of a truncated download.
- 52-week high uses 252 prior completed daily sessions (an explicit session-count
  proxy). ATH requires `Context(all_time_history=True)` from a verified full-history
  caller. A short rolling history is never advertised as all-time history.
- Chart targets project measured height from the breakout boundary, not from a
  chased entry. If the proposed entry has already exhausted the target, no plan is
  issued. Tick rounding is directional; stop/entry/target ordering is rechecked.
- Rule scores are deliberately fixed evidence tiers: candles 40 forming/80 confirmed,
  charts 45 forming/85 confirmed. They are not probabilities or optimized trade ranks.

## Time and output contract

Supported: `5m`, `15m`, `1h`, `daily`, `weekly`; monthly is also supported defensively.
Every Bar supplies aware `time` and `closed_at`. Only `closed_at <= asof` is visible.
Intraday bars must be aligned to the regular 09:15 grid and end no later than 15:30.
The final incomplete hourly stub is rejected. Daily adapter bars become available
at 15:40. Weekly/monthly aggregation verifies all expected sessions in each bucket
and discards incomplete buckets. Weekly bars are conservatively released after the
calendar week, monthly after month-end; no special-session calendar is guessed.
Unknown historic calendars/special sessions remain Phase 0/1 limitations.

Output fields:

```
pattern, direction, score, bar_index, time, confirmed, context,
entry, stop, target, invalidation, start, end, levels, trendlines,
timeframe, available_at, version, score_type
```

`available_at` is the confirmation/detection close, not the earlier pivot timestamp.
`bar_index` is relative to the supplied closed frame. Trendline slope/intercept use
that same index coordinate system. Keep the input frame identity when exporting.
Signals are conditional next-bar research references, never recorded fills.
The engine returns the latest snapshot; durable issuance/immutable outcome events
are a separate unresolved Phase 1 concern, not claimed by this package.

## Configuration

Defaults are shown in `patterns/defaults.json`. Core callers pass a frozen
`PatternConfig(...)`. The app accepts an optional JSON path via
`INSIGHTS_PATTERNS_CONFIG` in local `.env`. Unknown names, invalid values and
invalid types fail explicitly. Do not change the sample file and assume it was
loaded; set the path explicitly. Custom settings change rule definitions and
must be versioned with research results.

## Install this GitHub revision on Windows

1. Exit the running app using **Logout / Exit**. Keep your existing project and
   `.env` as a backup. Do not share `.env` or Dhan credentials.
2. Download the **Phase 2 PR branch**, not the older default branch, as ZIP and
   extract it into a separate directory.
3. In CMD, go to the newly extracted source directory. Use your existing Python
   environment to run the bundled installer, replacing the project path if needed:

```bat
"H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights\.venv\Scripts\python.exe" tools\install_fii_holdings_update.py --project "H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights"
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
PHASE2_CHECK.bat
cd web
npm run build
cd ..
START_INSIGHTS.bat
```

The updater now includes `patterns/` and keeps backups; it preserves credentials
and databases. Despite the historical installer filename, it installs the complete
Insights module set. Node/npm are needed for this source-update build. This is not
a new standalone installer for a computer without Python/Node.

4. Open the app, expand the shared inspector, select a symbol/timeframe and check
   the results. A source error, no pattern, forming geometry and eligibility-pending
   geometry are distinct outcomes. No setup is a valid outcome.
5. Review this Phase 2 change before authorizing Phase 3. The Phase 1 Intraday
   confidence/journal bug, full charge engine and other unrelated findings are
   not silently fixed by this PR.

## Verification

Offline verification performed during development:

- Pattern tests: 22 tests, including positive fixtures for every catalogue label,
  as-of prefix equivalence, future perturbation, pivot delay, malformed inputs,
  circuit/liquidity rejection, gaps, tick rounding and target confirmation.
- Insights suite: 428 tests passed, including 8 new adapter/API tests and existing
  positional/EMA9 compatibility tests.
- Core suite: 3 tests passed.
- Python compilation and Vite production build passed.

These are synthetic and regression results. No live Dhan data, profitability
backtest, full-market throughput test or visual browser certification was performed.
Existing Phase 0 live-data acceptance remains separate.

References for terminology and temporal contracts: [TA-Lib catalogue](https://ta-lib.org/functions/),
[TA-Lib configurable candle settings](https://ta-lib.org/api/candle-settings/),
[pandas resampling documentation](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.resample.html).
This is an independent implementation with explicitly documented definitions, not
an assertion of numerical equivalence to TA-Lib's discretionary candle settings.
