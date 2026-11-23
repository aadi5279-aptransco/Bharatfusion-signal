"""Evidence checks for Phase 0; never fill, shift or invent market candles."""
import pandas as pd
from insights.config import IST

def result_status(result):
    if result is None:
        return 'UNAVAILABLE'
    if isinstance(result, dict) and result.get('warnings'):
        return 'REVIEW'
    return 'PASS'

def candle_evidence(frame, period, now, item, download_quality=None):
    if frame.empty:
        raise ValueError('Empty candle result')
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Timezone-aware DatetimeIndex required')
    stamps = frame.index.tz_convert(IST)
    now = pd.Timestamp(now).tz_convert(IST)
    warnings = []
    if not stamps.is_monotonic_increasing or stamps.has_duplicates:
        warnings.append('UNSORTED_OR_DUPLICATE_TIMESTAMPS')
    derivative = item.get('kind') in ('future', 'option')
    if derivative and 'oi' not in frame:
        warnings.append('REQUESTED_OI_MISSING')
    # A transparent baseline for EMA200 research; each strategy may require more.
    if len(frame) < 200:
        warnings.append('BELOW_200_BAR_RESEARCH_BASELINE')
    sessions = []
    if period < 1440:
        minute = stamps.hour * 60 + stamps.minute
        off_grid = ((minute - 555) % period != 0) | (stamps.second != 0)
        outside = (minute < 555) | (minute >= 930)
        partial = (minute < 930) & (minute + period > 930)
        if off_grid.any():
            warnings.append('OFF_REGULAR_SESSION_GRID')
        if outside.any():
            warnings.append('OUTSIDE_REGULAR_SESSION_REFERENCE')
        if partial.any():
            warnings.append('SESSION_END_PARTIAL_BARS_REQUIRE_REVIEW')
        # Evaluate only observed dates. No inference that absent dates are holidays.
        for day in sorted(set(stamps.date)):
            observed = stamps[stamps.date == day]
            start = pd.Timestamp(day, tz=IST) + pd.Timedelta(minutes=555)
            close = pd.Timestamp(day, tz=IST) + pd.Timedelta(minutes=930)
            until = min(close, now)
            expected = pd.date_range(start, close, freq=str(period)+'min', inclusive='left')
            expected = expected[expected + pd.Timedelta(minutes=period) <= until]
            missing = expected.difference(observed)
            sessions.append(dict(date=str(day), rows=len(observed),
                first=observed[0].isoformat(), last=observed[-1].isoformat(),
                missing_full_grid_bars=len(missing),
                first_missing=missing[0].isoformat() if len(missing) else None,
                last_missing=missing[-1].isoformat() if len(missing) else None))
        if any(s['missing_full_grid_bars'] for s in sessions):
            warnings.append('OBSERVED_SESSION_COVERAGE_INCOMPLETE')
    quality = dict(rows=len(frame), first=stamps[0].isoformat(), last=stamps[-1].isoformat(),
        timezone=str(stamps.tz), zero_volume=int((frame['volume'] == 0).sum()),
        sessions=sessions, coverage_scope='Observed dates only; holidays and special sessions not certified')
    return dict(rows=len(frame), first=quality['first'], last=quality['last'],
        timezone=quality['timezone'], oi_available='oi' in frame,
        instrument={k:item.get(k) for k in ('id','segment','instrument','kind','expiry','strike','side')},
        returned_quality=quality, download_quality=download_quality or {},
        warnings=warnings, strategy_readiness='NOT CERTIFIED',
        research_baseline_bars=200, research_baseline_met=len(frame)>=200)
