"""Read-only coverage diagnostics for immutable 5-minute snapshots.

Weekday grids are hypothetical regular sessions, NOT exchange-calendar evidence.
No result from this module approves training or changes the saved snapshot.
"""
from datetime import datetime, timedelta
from insights.config import IST

def timestamp(value):
    t = datetime.fromisoformat(value)
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError('Snapshot timestamps must be timezone-aware')
    return t.astimezone(IST)

def assess(payload):
    manifest = payload['manifest']
    if manifest.get('timeframe') != '5m':
        raise ValueError('Readiness supports 5-minute snapshots only')
    end = timestamp(manifest['as_of'])
    days = manifest['requested_days']
    if type(days) is not int or not 1 <= days <= 30:
        raise ValueError('Invalid snapshot window')
    start = end - timedelta(days=days)
    actual = {timestamp(row['time']) for row in payload['rows']}
    sessions = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day.date() <= end.date():
        if day.weekday() < 5:
            opening = day.replace(hour=9, minute=15)
            grid = [opening + timedelta(minutes=5*i) for i in range(75)]
            expected = [t for t in grid if t >= start and t+timedelta(minutes=5) <= end]
            if expected:
                present = sorted(t for t in expected if t in actual)
                missing = [t for t in expected if t not in actual]
                observed = bool(present)
                sessions.append({
                    'date': day.date().isoformat(), 'expected_regular_bars': len(expected),
                    'present': len(present), 'missing_regular_bars': len(missing),
                    'first_missing': missing[0].isoformat() if missing else None,
                    'last_missing': missing[-1].isoformat() if missing else None,
                    'missing_before_first': sum(t < present[0] for t in missing) if observed else None,
                    'missing_after_last': sum(t > present[-1] for t in missing) if observed else None,
                    'classification': ('OBSERVED_SESSION_GAPS' if missing else 'OBSERVED_GRID_COMPLETE')
                                      if observed else 'NO_ROWS_CALENDAR_UNVERIFIED',
                })
        day += timedelta(days=1)
    known_gaps = sum(s['missing_regular_bars'] for s in sessions if s['present'])
    unobserved = [s['date'] for s in sessions if not s['present']]
    reasons = list(manifest.get('blockers', []))
    if known_gaps:
        reasons.append(f'{known_gaps} regular-grid candles absent within observed sessions')
    if unobserved:
        reasons.append('Whole weekdays without rows require holiday/session/source verification')
    if payload.get('quarantine'):
        reasons.append('Quarantined rows need review')
    reasons.append('Calendar and point-in-time provenance must be independently verified')
    return {
        'version': 'readiness-v1', 'status': 'COVERAGE_REVIEW' if known_gaps or unobserved or payload.get('quarantine') else 'PROVENANCE_REVIEW',
        'training_ready': False, 'evaluated_as_of': end.isoformat(),
        'missing_in_observed_sessions': known_gaps,
        'weekdays_without_rows': unobserved, 'sessions': sessions,
        'reasons': list(dict.fromkeys(reasons)),
        'scope': 'Regular weekday grid only; absent weekdays may be holidays. Audit is as of snapshot capture, not current time.',
    }
