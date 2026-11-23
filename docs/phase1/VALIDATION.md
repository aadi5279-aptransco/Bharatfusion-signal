# Phase 1 — validation and reproduction guide

## What was and was not verified

- Source reviewed at `147e27b35fe5848f4ac8c460a5fe3d82d418f691`; branch head rechecked against `feature/phase0-dhan-data-20261122`.
- Existing Phase 0 CI evidence: [workflow run 45114668190](https://github.com/aadi5279-aptransco/Bharatfusion-signal/actions/runs/45114668190), previously inspected, reported 420 Insights tests plus 3 core tests passing. That is an existing suite result, **not an execution of this audit's reproductions** and not live-market certification.
- The pasted user reports establish observed local PASS/REVIEW/UNAVAILABLE results, including unresolved BANKNIFTY futures mapping. They do not independently prove source adjustment, complete calendars or option-history lineage.
- No local execution environment was available for this audit. No new Python tests, browser checks, full-market soak, penetration test or live Dhan call was run.
- The docs-only GitHub diff must be checked before publication. No application installation is necessary to read these reports.
- Every finding in AUDIT.md has a specific reproduction. V1–V4 below give small isolated executable recipes for the strongest deterministic cases. Expected results are source-derived, not claimed runtime observations.

## Run safely on Windows

Use a separate checkout of the audited revision, not your production database. Open CMD in the application project folder. The commands below assume its existing Python virtual environment works:

```bat
cd /d H:\BharatSignal_Fusion_Ready\BharatSignal_Fusion_Insights
.venv\Scripts\python.exe
```

Paste one Python recipe at a time at the Python prompt. Alternatively save a recipe in a temporary file outside production and run it with that interpreter. These recipes do not need Dhan credentials. The Journal recipe creates a temporary database and removes it automatically. Exit the Python prompt using `exit()`.

Do not paste edited code into the live application for this phase. If the checkout differs from the audited SHA, record its SHA and report that difference with the result.

## V1 — nullable confidence integration (F01)

```python
import tempfile
from pathlib import Path
from insights.db import Journal

with tempfile.TemporaryDirectory() as folder:
    journal = Journal(Path(folder) / "audit.sqlite")
    row = dict(
        strategy="audit", version="1", symbol="TEST", direction="BUY",
        signal_at="2026-11-23T10:00:00+05:30",
        entry=100, sl=95, t1=110, t2=115, rr=2,
        confidence=None, reasons=["synthetic fixture"],
    )
    try:
        journal.record(row)
    except TypeError as exc:
        print(type(exc).__name__, str(exc))
    else:
        print("No TypeError: compare checkout against audited revision")
```

Expected on baseline: TypeError converting None to float. The production chain sets this field in momentum_query, preserves it through ai_rank/cycle_wave, calls record before appending and catches TypeError as unavailable. A repair must not substitute an invented probability merely to satisfy the database.

Follow-up integration acceptance: feed a qualified broker fixture through scan_intraday, verify it appears once, has a nullable calibrated probability plus separate heuristic score, and does not count as a source error.

## V2 — unfilled entry counted by backtester (F03)

```python
import pandas as pd
from insights.backtest import evaluate_trades

ix = pd.date_range("2026-11-23 09:15", periods=6, freq="5min",
                   tz="Asia/Kolkata")
frame = pd.DataFrame(
    dict(open=[111]*6, high=[112]*6, low=[111]*6,
         close=[111]*6, volume=[100000]*6), index=ix)

def candidate(observed):
    return dict(direction="BUY", entry=100, sl=95, t1=110)

result = evaluate_trades(frame, candidate, "audit",
                         warmup=1, hold_bars=1, costs_bps=0)
print(result["samples"], result["win_rate"], result["avg_r"])
```

Expected on baseline: positive samples, 100% win rate and +2R average, despite every possible next-bar fill being above the target. This fixture isolates the simulator's entry assumption, not a realistic predictive strategy. A corrected simulator must reject/reprice the plan or apply a clearly defined order fill; it must not claim +2R from an unavailable entry.

For F02 use the same price path via a mock broker in reconcile_outcomes, with an OPEN temporary Journal row. Assert that an entry event must precede an outcome event. For gaps through SL, use the next available fill instead of assuming the stop price.

## V3 — session end boundary (F09)

```python
from datetime import datetime
from insights.config import IST, is_market_session

at = datetime(2026, 11, 23, 15, 30, 30, tzinfo=IST)
print(is_market_session(at, set()))
```

Expected on baseline: True, because seconds are ignored and the 15:30 minute is inclusive. This is a synthetic ordinary-session test with an empty holiday set, not certification of the date's exchange calendar. The desired interval must explicitly distinguish normal trading, session-end events and post-close work.

## V4 — unknown previous OI becomes reported positive change (F17)

```python
from insights.strategies.options import chain_metrics

chain = {"oc": {"100": {"ce": {"oi": 100}, "pe": {"oi": 80}}}}
m = chain_metrics(chain)
print(m["call_change"], m["put_change"])
```

Expected on baseline: 100 and 80. Desired: unavailable change with a reason when previous_oi is absent. Current OI still exists and may be useful independently.

## Temporal correctness matrix required before Phase 2 acceptance

| Test | Fixture and expected invariant |
|---|---|
| Prefix replay | At each time t, pass only bars closed by t. Store output with detection/confirmation time. Appending future bars must not revise previously emitted immutable events. A function intentionally evaluating the latest bar will naturally produce a different latest output; compare the historical event stream, not just its last result. |
| Future perturbation | Change all bars after t drastically and recompute events through t. Every feature, pivot-confirmation event, eligibility decision and level through t must be identical. |
| Pivot delay | A pivot at i with N right bars must not be available until i+N closes. Drawing at i must retain confirmed_at=i+N; entries occur later according to fill rules. |
| Streaming vs batch | Replay candle-by-candle then compare with batch as-of evaluation using identical closed inputs/config. Include restarts and cache reuse. |
| Current 5/15/60m | At one second before/at/after each close, exclude/include exactly the correct completed interval. Cash final hourly stub must have an explicit policy. |
| Running daily | Reconstruct intraday daily features only from bars available at that scan. Never substitute final daily high/low/close/volume. |
| Weekly/monthly | Midweek/month, Friday/month-end before and after close, holiday period-end, year crossing, first partial source bucket and missing last session. No partial bar silently enters a completed-period pattern. |
| Session grids | Missing 09:15 bar, interior gap, off-grid 11:56 aggregate, after-session 15:35, weekend/Muhurat and interruptions; classify reject/warn/allowed by actual session metadata. |
| Benchmark alignment | Missing/stale Nifty or sector bars must not become neutral/zero relative strength without an explicit unavailable flag. |
| Knowledge time | Fundamentals and corporate actions join on publication/known_at; point-in-time constituents; revisions never overwrite the dataset used by an old model. |
| Fill timing | Signal at t cannot fill before next eligible bar. Test opening gaps, spread, stop entry never touched and stop+target in same bar. |
| Immutability | Repeated resolver calls cannot rewrite closed events. Provider corrections produce new evidence events and a review state, not silent performance revision. |

## Numerical fixtures

Validate Wilder RSI/ATR/ADX against an independently specified reference, including SMA seed, first valid index, flat/all-up/all-down series, gaps, zero volume and NaN/infinity. Specify EMA first-observation vs SMA seed and tolerance after warm-up; do not call either convention universally wrong.

Test session-reset VWAP on two IST dates with different prices/volumes, on equivalent UTC timestamps, and with zero-volume cash-index bars. Verify identical economic results and no denominator fabrication. Test Supertrend first finite band, alternating direction and gap crossings. For OBV use unchanged-price bars (zero signed contribution), and test pivots/CPR using the prior completed session rather than current highs/lows.

## Operational and UI validation (not run)

1. Slow/failing mock Dhan requests across an entire 500-symbol session; record per-job start/end, queue age, timeout, retries, quota and peak memory.
2. Restart at 09:46/10:01 and after close; duplicate service instances; cancellation and shutdown while a request is in flight.
3. Make discovery fail then recover inside one hourly slot; verify retry and stale-list policy.
4. Throttle HTTP beyond the UI polling interval; respond out of order; verify latest payload wins and no stale entry-ready state persists.
5. Exercise empty/no-setup/source-error/stale/partial states separately on every tab; verify IST labels and Indian number formatting.
6. Verify all mutation routes reject foreign Origin/Host under local test_client conditions; confirm guarded local exit still works.
7. Corrupt one cached file and one historical payload in an isolated root; confirm quarantine/clear error without credentials in logs.
8. Reconcile a sample of published signals across all tabs, notification IDs and append-only outcome events; verify costs, horizons and duplicate policy.

## Live evidence still needed

- Sanitized BANKNIFTY master candidate fields and mapping result from the audited revision.
- Verified interpretation of derivative timestamps/grid, including 15:35/15:39 and 11:56 aggregates.
- A market-session observation showing each timeframe's forming candle appears only after its completion.
- Exchange holiday/special-session and dated eligibility records, not only a configured-calendar label.
- Independent corporate-action reconciliation and actual option contract-history lineage.
- Browser/full-load/overnight soak and paper-forward result evidence.

Do not send tokens, client secrets, .env contents or full authenticated responses. Preserve evidence timestamps and instrument IDs necessary to reproduce the mapping.

## Acceptance and approval

Phase 1 acceptance means the architecture and audit are reviewable, not that findings are fixed. The documentation may be merged without changing runtime behaviour. Runtime repairs and Phases 2/3 require the user's next phase approval. Nothing in this report asserts perfect entries, guaranteed targets or profitable live trading.
