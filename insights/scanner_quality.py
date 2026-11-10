"""Conservative candle and cached-context freshness checks.

These rules prevent historical Dhan data from becoming a live signal.
A valid current-session candle is necessary but never sufficient for a trade.
"""
from __future__ import annotations

import pandas as pd


def current_completed_bar(value, now, interval_minutes=5, max_lag_minutes=20):
    """True only if a finished candle is recent, today, and timezone-aware."""
    try:
        timestamp = pd.Timestamp(value)
        current = pd.Timestamp(now)
        if timestamp.tzinfo is None or current.tzinfo is None:
            return False
        timestamp = timestamp.tz_convert(current.tz)
        age = (current - timestamp).total_seconds() / 60
        return (
            timestamp.date() == current.date()
            and interval_minutes <= age <= max_lag_minutes
            and (9, 15) <= (timestamp.hour, timestamp.minute) <= (15, 25)
        )
    except (TypeError, ValueError, AttributeError):
        return False


def recent_frame(frame, now, interval_minutes=5, max_lag_minutes=20):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return False
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        return False
    return current_completed_bar(frame.index[-1], now, interval_minutes, max_lag_minutes)


def recent_context(item, now, max_lag_minutes=20):
    if not isinstance(item, dict):
        return False
    return (
        item.get("session_date") == pd.Timestamp(now).date().isoformat()
        and current_completed_bar(item.get("asof"), now, 5, max_lag_minutes)
        and item.get("bias") != "UNAVAILABLE"
    )
