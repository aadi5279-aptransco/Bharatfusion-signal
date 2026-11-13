"""Two independent 5-minute cash/spot option-direction research setups.

1. First 09:15-09:20 candle low=Fib 0 and high=Fib 1.
   Two *subsequent completed* candle closes above 1 suggest CE, below 0 PE.
2. First strictly RED completed 5m candle after 09:20.
   For a red bar, reverse the Fib orientation: high=0, low=1.
   Thus 0.44 is the UPPER boundary and 0.56 the LOWER boundary.
   Two completed closes above 0.44 suggest CE; below 0.56 suggest PE.
   The 0.44–0.56 price band is NO_TRADE.

No volume/MTF/OI gate silently suppresses these directional watches;
option contract/fresh premium validation is a separate, transparent layer.
Only *regular session* completed 5-minute candles are read, no look-ahead.
"""
from __future__ import annotations
import math
import pandas as pd

VERSION="opening-redbar-v1"
FIRST="First 5m 0/1 Break"
REDBAR="First Red Bar Fib 0.44/0.56"


def _base(key,now):
    return dict(key=key,strategy=FIRST if key=="first5" else REDBAR,
                state="WAITING",side=None,
                research_only=True,version=VERSION,spot_entry=None,
                spot_sl=None,spot_t1=None,spot_t2=None,
                option_contract=None,quote_freshness="NOT VERIFIED",
                asof=pd.Timestamp(now).isoformat())


def _session(frame,now):
    t=pd.Timestamp(now)
    if t.tzinfo is None or frame is None or not isinstance(frame,pd.DataFrame):
        return None
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:
        return None
    if frame.index.has_duplicates or not {"open","high","low","close","volume"}.issubset(frame.columns):
        return None
    f=frame.sort_index().copy()
    f=f[(f.index.date==t.date())&(f.index+pd.Timedelta(minutes=5)<=t)]
    f=f[(f.index.hour*60+f.index.minute>=555)&
        (f.index.hour*60+f.index.minute<=925)&
        ((f.index.hour*60+f.index.minute-555)%5==0)]
    if f.empty or (f.index[0].hour,f.index[0].minute)!=(9,15):
        return None
    try:
        cols=["open","high","low","close","volume"]
        f[cols]=f[cols].astype(float)
    except (ValueError,TypeError):return None
    if not f[cols].notna().all().all() or not (f[cols[:4]]>0).all().all():
        return None
    if (f.high<f[["open","low","close"]].max(axis=1)).any() or (
        f.low>f[["open","high","close"]].min(axis=1)).any():return None
    if not (f.index.to_series().diff().dropna()==pd.Timedelta(minutes=5)).all():
        return None
    return f


def _sustain(post,threshold,side):
    if len(post)<2:return False
    closes=post.close.iloc[-2:]
    return bool((closes>threshold).all() if side=="CE" else (closes<threshold).all())


def _calculate(f,now,key):
    out=_base(key,now)
    if f is None:return dict(out,reason="Missing valid consecutive completed session 5m spot/cash candles")
    if key=="first5":
        ref=f.iloc[0]
        reference_at=f.index[0]
        hi=float(ref.high);lo=float(ref.low)
        if hi<=lo:return dict(out,state="NO_TRADE",reason="Zero or invalid first candle range")
        upper,lower=hi,lo
        fib={"0":round(lo,4),"1":round(hi,4)}
        orientation="0=first candle low, 1=first candle high"
        post=f.iloc[1:]
        zone="Inside first candle range (0–1)"
    elif key=="redbar":
        # The first five-minute candle is excluded from the search.
        candidates=f.iloc[1:]
        red=candidates[candidates.close<candidates.open]
        if red.empty:
            return dict(out,reason="Waiting for first strictly red 5m candle after 09:20")
        reference_at=red.index[0]
        ref=red.iloc[0]
        hi=float(ref.high);lo=float(ref.low)
        if hi<=lo:return dict(out,state="NO_TRADE",reason="First red candle has no price range")
        # Descending Fib orientation makes 0.44 upper and 0.56 lower.
        upper=hi-.44*(hi-lo);lower=hi-.56*(hi-lo)
        fib={"0":round(hi,4),"0.44":round(upper,4),
             "0.56":round(lower,4),"1":round(lo,4)}
        orientation="0=red candle HIGH, 1=red candle LOW; 0.44 upper / 0.56 lower"
        post=f[f.index>reference_at]
        zone="Between Fib 0.44 (upper) and Fib 0.56 (lower)"
    else:raise ValueError("Unknown 5m strategy key")
    out.update(fib=fib,reference_at=reference_at.isoformat(),
               reference_high=round(hi,4),reference_low=round(lo,4),
               orientation=orientation,no_trade_zone=zone,
               trigger_ce=round(upper,4),trigger_pe=round(lower,4),
               spot_price=round(float(f.close.iloc[-1]),2),
               signal_at=f.index[-1].isoformat())
    if len(post)<2:
        return dict(out,reason="Waiting for two completed 5m closes AFTER reference candle")
    # No overlapping CE/PE condition. A single wick does not qualify.
    ce=_sustain(post,upper,"CE")
    pe=_sustain(post,lower,"PE")
    if ce==pe:
        return dict(out,state="NO_TRADE",
                    reason="No unambiguous two-close sustain outside trigger levels")
    side="CE" if ce else "PE"
    last=float(f.close.iloc[-1])
    stop=(lo if ce else hi)
    sign=1 if ce else -1
    risk=sign*(last-stop)
    if risk<=0 or risk/last>.06:
        return dict(out,state="WATCH",side=side,
                    reason="Sustained break detected; structural stop distance unsuitable")
    first_r=1.5;second_r=2.5
    return dict(out,state="DIRECTION_READY",side=side,
                spot_entry=round(last,2),spot_sl=round(stop,2),
                spot_t1=round(last+sign*first_r*risk,2),
                spot_t2=round(last+sign*second_r*risk,2),
                stop_distance_pct=round(risk/last*100,2),
                reason="Two COMPLETED 5m closes beyond reference; conditional underlying research only; option premium unverified")


def evaluate(frame,now):
    """Always return both strategy states, including waiting/no-trade reasons."""
    return [_calculate(_session(frame,now),now,key) for key in ("first5","redbar")]
