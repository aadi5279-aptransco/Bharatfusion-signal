"""Independent swing-trade Gann/time-cycle and confirmed wave evidence.

Completed daily and completed weekly bars only. Original swing entries,
stops, targets, scan cadence and candidate eligibility are never modified.
Gann and Elliott-inspired concepts are heuristics, not calibrated forecasts.
"""
from __future__ import annotations
import math
import pandas as pd
from insights.config import IST
from insights.cycle_wave import _pivots

VERSION="swing-gann-wave-v1"
DAY_CYCLES=(20,30,45,60,90,120)
WEEK_CYCLES=(4,8,13,21,34)


def _missing(why):
    return dict(version=VERSION,status="UNAVAILABLE",reason=why,
                gann={},time_cycle={},wave={},alignment="UNAVAILABLE")


def _pattern(pivots):
    highs=[p["price"] for p in pivots if p["kind"]=="HIGH"]
    lows=[p["price"] for p in pivots if p["kind"]=="LOW"]
    if len(highs)<2 or len(lows)<2:return "UNDETERMINED"
    if highs[-1]>highs[-2] and lows[-1]>lows[-2]:return "RISING SWINGS"
    if highs[-1]<highs[-2] and lows[-1]<lows[-2]:return "FALLING SWINGS"
    return "MIXED / CORRECTIVE"


def assess(daily,asof):
    t=pd.Timestamp(asof)
    if t.tzinfo is None:return _missing("As-of timestamp has no timezone")
    t=t.tz_convert(IST)
    if daily is None or not isinstance(daily,pd.DataFrame):
        return _missing("Daily OHLCV unavailable")
    if not isinstance(daily.index,pd.DatetimeIndex) or daily.index.tz is None:
        return _missing("Need timezone-aware daily timestamps")
    if daily.index.has_duplicates or not {"open","high","low","close","volume"}.issubset(daily.columns):
        return _missing("Duplicate timestamps or missing daily OHLCV")
    f=daily.sort_index().copy()
    completed_today=(t.hour,t.minute)>=(15,40)
    f=f[(f.index.date<t.date()) |
        ((f.index.date==t.date()) & completed_today)]
    if len(f)<100:return _missing("Need at least 100 completed daily candles")
    try:f[["open","high","low","close","volume"]]=f[["open","high","low","close","volume"]].astype(float)
    except (ValueError,TypeError):return _missing("Non-numeric daily OHLCV")
    if f[["open","high","low","close","volume"]].isna().any().any():
        return _missing("Missing daily OHLCV")
    if (f[["open","high","low","close"]]<=0).any().any() or (f.volume<0).any():
        return _missing("Invalid daily OHLCV")
    if (f.high<f[["open","close","low"]].max(axis=1)).any() or (f.low>f[["open","close","high"]].min(axis=1)).any():
        return _missing("Inconsistent OHLC ranges")
    pivots=_pivots(f,left=3,right=3)
    dp=_pattern(pivots)
    weekly=f.resample("W-FRI").agg(dict(open="first",high="max",low="min",close="last",volume="sum")).dropna()
    # Exclude the current incomplete calendar week. On Friday, it
    # becomes complete only after the regular 15:30 exchange close.
    weekly=weekly[(weekly.index.date<t.date()) |
                  ((weekly.index.date==t.date()) &
                   (t.weekday()==4) & completed_today)]
    wp=_pivots(weekly,left=2,right=2) if len(weekly)>=30 else []
    weekly_pattern=_pattern(wp)
    last_pivot=pivots[-1] if pivots else None
    last_week=wp[-1] if wp else None
    day_age=len(f)-1-last_pivot["position"] if last_pivot else None
    week_age=len(weekly)-1-last_week["position"] if last_week else None
    close=float(f.close.iloc[-1])
    anchor=float(last_pivot["price"]) if last_pivot else close
    root=math.sqrt(anchor)
    levels=sorted((root+step)**2 for step in (-2,-1.5,-1,-.5,-.25,.25,.5,1,1.5,2) if root+step>0)
    support=max((p for p in levels if p<close),default=None)
    resistance=min((p for p in levels if p>close),default=None)
    alignment=("ALIGNED" if dp=="RISING SWINGS" and weekly_pattern=="RISING SWINGS"
               else "CONTRADICTS" if "FALLING SWINGS" in (dp,weekly_pattern)
               else "MIXED / UNVERIFIED")
    return dict(version=VERSION,status="EVIDENCE ONLY",
        timeframe="COMPLETED DAILY AND WEEKLY",
        price_asof=f.index[-1].isoformat(),alignment=alignment,
        gann=dict(method="Square-of-nine sqrt-price increments at confirmed swing pivot",
                  anchor=round(anchor,2),
                  support=round(support,2) if support is not None else None,
                  resistance=round(resistance,2) if resistance is not None else None),
        time_cycle=dict(anchor="Most recent confirmed daily and weekly swing pivots",
            daily_sessions_since_pivot=day_age,weekly_bars_since_pivot=week_age,
            daily_windows=list(DAY_CYCLES),weekly_windows=list(WEEK_CYCLES),
            near_daily_sessions=[p for p in DAY_CYCLES if day_age is not None and abs(day_age-p)<=2],
            near_weekly_bars=[p for p in WEEK_CYCLES if week_age is not None and abs(week_age-p)<=1],
            warning="Time-cycle proximity alone does not predict a reversal"),
        wave=dict(daily_structure=dp,weekly_structure=weekly_pattern,
                  daily_confirmed_pivots=pivots[-6:],weekly_confirmed_pivots=wp[-6:],
                  elliott_count="UNVERIFIED — no subjective 1–5/A–B–C certainty"),
        warning="Additional research layer only; not a win probability")


def annotate(row,daily,asof):
    """Do not change eligibility, ranking, entry, stop or either target."""
    result=dict(row)
    assessment=assess(daily,asof)
    result["swing_gann_wave"]=assessment
    result["gann_wave_alignment"]=assessment["alignment"]
    return result
