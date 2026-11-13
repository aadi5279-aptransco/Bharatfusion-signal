"""Conservative Gann price levels, time-cycle markers and swing-wave evidence.

These are mathematical/structural heuristics, not independently validated
predictors. No future bars, Elliott wave certainty, or institutional claims.
"""
from __future__ import annotations
import math
import pandas as pd

VERSION="gann-wave-evidence-v1"


def _pivots(frame, left=2, right=2):
    """Only label a pivot once right-side confirming candles have completed."""
    f=frame.sort_index()
    extrema=[]
    if len(f)<left+right+5:return []
    for i in range(left,len(f)-right):
        local_high=f.high.iloc[i-left:i+right+1]
        local_low=f.low.iloc[i-left:i+right+1]
        hi=float(f.high.iloc[i]);lo=float(f.low.iloc[i])
        if hi>=float(local_high.max()) and hi>float(f.high.iloc[i-1]) and hi>float(f.high.iloc[i+1]):
            extrema.append(dict(kind="HIGH",price=hi,asof=f.index[i].isoformat(),position=i,confirmed_after=f.index[i+right].isoformat()))
        elif lo<=float(local_low.min()) and lo<float(f.low.iloc[i-1]) and lo<float(f.low.iloc[i+1]):
            extrema.append(dict(kind="LOW",price=lo,asof=f.index[i].isoformat(),position=i,confirmed_after=f.index[i+right].isoformat()))
    filtered=[]
    for point in extrema:
        if filtered and filtered[-1]["kind"]==point["kind"]:
            prior=filtered[-1]
            more_extreme=(point["price"]>prior["price"] if point["kind"]=="HIGH"
                          else point["price"]<prior["price"])
            if more_extreme:filtered[-1]=point
        else:filtered.append(point)
    return filtered[-10:]


def assess(frame, now=None):
    """Price-only optional confirmation for a completed 5m instrument frame."""
    unknown=dict(version=VERSION,status="UNAVAILABLE",gann={},time_cycle={},
                 wave={},reason="Need completed, ordered, timezone-aware OHLCV")
    if frame is None or not isinstance(frame,pd.DataFrame) or len(frame)<45:
        return unknown
    if not {"high","low","close"}.issubset(frame.columns):
        return unknown
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None or frame.index.has_duplicates:
        return unknown
    f=frame.sort_index().copy()
    if now is not None:
        t=pd.Timestamp(now)
        if t.tzinfo is None:return unknown
        # All bar timestamps must refer to candles that have completed.
        f=f[f.index+pd.Timedelta(minutes=5)<=t]
    if len(f)<45:return unknown
    try:f[["high","low","close"]]=f[["high","low","close"]].astype(float)
    except (ValueError,TypeError):return unknown
    if f[["high","low","close"]].isna().any().any():return unknown
    p=float(f.close.iloc[-1])
    if p<=0 or not math.isfinite(p):return unknown
    root=math.sqrt(p)
    # Square-of-nine price levels use square-root increments; calibration
    # to tick size / market instrument is NOT claimed.
    levels=sorted([(root+step)**2 for step in (-1,-.5,-.25,.25,.5,1) if root+step>0])
    below=[x for x in levels if x<p]
    above=[x for x in levels if x>p]
    gann=dict(method="Square-of-nine sqrt-price increments — heuristic",
              support=round(max(below),2) if below else None,
              resistance=round(min(above),2) if above else None,
              distances_pct={
                  "support":round((p/max(below)-1)*100,2) if below else None,
                  "resistance":round((min(above)/p-1)*100,2) if above else None})
    last=f.index[-1]
    session=f[f.index.date==last.date()]
    elapsed=int((last.hour*60+last.minute)-(9*60+15))
    cycles=(30,45,60,90,120,180)
    tolerance=5
    active=[m for m in cycles if elapsed>0 and (elapsed % m <=tolerance
           or m-elapsed%m <= tolerance)]
    times=dict(anchor="09:15 IST regular cash session",
               elapsed_minutes=elapsed,near_cycle_minutes=active,
               note="Time-cycle windows alone are NOT reversal signals")
    pivots=_pivots(f)
    highs=[x["price"] for x in pivots if x["kind"]=="HIGH"]
    lows=[x["price"] for x in pivots if x["kind"]=="LOW"]
    structure="UNDETERMINED"
    if len(highs)>=2 and len(lows)>=2:
        if highs[-1]>highs[-2] and lows[-1]>lows[-2]:
            structure="RISING SWINGS"
        elif highs[-1]<highs[-2] and lows[-1]<lows[-2]:
            structure="FALLING SWINGS"
        else:structure="MIXED / CORRECTIVE"
    wave=dict(structure=structure,confirmed_pivot_count=len(pivots),
              recent_confirmed_pivots=pivots[-6:],
              wave_count="UNVERIFIED — Elliott 1–5/A–B–C counts are subjective",
              note="Confirmed swing-pivot geometry, not predictive wave labeling")
    return dict(version=VERSION,status="EVIDENCE ONLY",
                price_asof=last.isoformat(),gann=gann,
                time_cycle=times,wave=wave,
                warning="Gann/wave/time cycles are not calibrated win probabilities")


def annotate(signal, frame, now=None):
    """Keep the original strategy's gates/entry intact; attach independent evidence."""
    row=dict(signal)
    layer=assess(frame,now)
    row["gann_wave"]=layer
    side=row.get("direction",row.get("side"))
    up=side in ("BUY","CE")
    down=side in ("SELL","PE")
    wave=layer.get("wave",{}).get("structure")
    if wave in ("RISING SWINGS","FALLING SWINGS"):
        row["wave_alignment"]=("ALIGNED" if
            ((up and wave=="RISING SWINGS") or (down and wave=="FALLING SWINGS"))
            else "CONTRADICTS")
    else:row["wave_alignment"]="UNAVAILABLE/MIXED"
    return row
