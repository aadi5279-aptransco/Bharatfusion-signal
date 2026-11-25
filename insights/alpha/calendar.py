"""Scoped published closures; not a general exchange-calendar certification."""
SOURCE = 'https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf'
HOLIDAYS = frozenset('2026-01-26 2026-03-03 2026-03-26 2026-03-31 2026-04-03 2026-04-14 2026-05-01 2026-05-28 2026-06-26 2026-09-14 2026-10-02 2026-10-20 2026-11-10 2026-11-24 2026-12-25'.split())

def published_holiday(instrument, day):
    return instrument.get('segment') == 'NSE_EQ' and day.isoformat() in HOLIDAYS
