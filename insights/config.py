"""Local-only configuration. Never log or serialize credentials."""
from __future__ import annotations
import os
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
ROOT = Path(os.getenv('BHARATSIGNAL_INSIGHTS_HOME', str(Path.home() / '.bharatsignal-insights')))
API_BIND = '127.0.0.1'  # fixed: do not expose Dhan-linked research service to LAN
API_PORT = int(os.getenv('INSIGHTS_PORT', '8765'))

# This new module has *no* code path for order submission.
if os.getenv('ENABLE_ORDER_PLACEMENT', 'false').lower() in ('true','1','yes'):
    raise RuntimeError('Market Insights is READ-ONLY. Set ENABLE_ORDER_PLACEMENT=false')

WATCHLIST = [x.strip().upper() for x in os.getenv('INSIGHTS_WATCHLIST','').split(',') if x.strip()]
MAX_SYMBOLS = max(1, min(200, int(os.getenv('INSIGHTS_MAX_SYMBOLS', '30'))))


def credentials_available():
    return bool(os.getenv('DHAN_CLIENT_ID') and os.getenv('DHAN_ACCESS_TOKEN'))


# Official NSE 2026 exchange closures; supplement a user-reviewed calendar.
# Always block these dates, even if the configured calendar is incomplete.
_KNOWN_2026_NSE_CLOSURES = frozenset({
    '2026-01-15', '2026-01-26', '2026-03-03', '2026-03-26',
    '2026-03-31', '2026-04-03', '2026-04-14', '2026-05-01',
    '2026-05-28', '2026-06-26', '2026-09-14', '2026-10-02',
    '2026-10-20', '2026-11-10', '2026-11-24', '2026-12-25',
})

def is_market_session(now, holidays=None):
    """Holiday calendar must be supplied; unknown holiday status fails closed."""
    local = now.astimezone(IST)
    if holidays is None:
        return False
    if local.year == 2026 and local.date().isoformat() in _KNOWN_2026_NSE_CLOSURES:
        return False
    return local.weekday() < 5 and local.date().isoformat() not in holidays and (9,15) <= (local.hour,local.minute) <= (15,30)
