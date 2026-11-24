"""Compatibility definitions for existing positional strategies.

Pure calculations moved here so tabs do not own morphology/trendline formulas.
Legacy PDF rules retain their versioned semantics; they are not relabelled as
patterns-v1 confirmation or profitability evidence.
"""
import math
from dataclasses import dataclass
from zoneinfo import ZoneInfo
import pandas as pd
IST=ZoneInfo('Asia/Kolkata')

def checked(frame):
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Timezone-aware OHLCV required')
    cols=['open','high','low','close','volume']
    if not set(cols).issubset(frame):raise ValueError('Missing OHLCV columns')
    f=frame[cols].astype(float).sort_index().copy();f.index=f.index.tz_convert(IST)
    if f.empty or f.index.has_duplicates:raise ValueError('Invalid candles')
    if (f[['open','high','low','close']]<=0).any().any():raise ValueError('Nonpositive prices')
    if (f.high<f[['open','close','low']].max(axis=1)).any() or (f.low>f[['open','close','high']].min(axis=1)).any():raise ValueError('Invalid OHLC')
    if not f.map(math.isfinite).all().all() or (f.volume<=0).any():raise ValueError('Missing/nonfinite values or zero volume')
    return f

def descending_trendline(high,n=5):
    p1=p2=None
    for i in range(n,len(high)-n):
        if high[i]==max(high[i-n:i+n+1]):
            p1=p2 if p2 is not None and high[i]<p2[1] else None
            p2=(i,float(high[i]))
    return p1,p2

def check_signal(frame,pivot_n=5,ema_len=9,vol_len=20,vol_mult=1.5,stop_lookback=10,rr=3.0):
    f=checked(frame)
    if len(f)<max(60,max(vol_len,stop_lookback)+4*pivot_n):return None
    p1,p2=descending_trendline(f.high.to_numpy(),pivot_n)
    if p1 is None or p2[0]-p1[0]<2*pivot_n:return None
    t=len(f)-1;slope=(p2[1]-p1[1])/(p2[0]-p1[0])
    line=p2[1]+slope*(t-p2[0]);prior_line=line-slope
    ema=float(f.close.ewm(span=ema_len,adjust=False).mean().iloc[-1])
    avg=float(f.volume.iloc[-vol_len-1:-1].mean());price=float(f.close.iloc[-1])
    if not (price>line and f.close.iloc[-2]<=prior_line and price>ema and f.volume.iloc[-1]>vol_mult*avg):return None
    stop=float(f.low.iloc[-stop_lookback-1:-1].min());risk=price-stop
    # PDF optional safeguards, explicit: <=15% stop risk and >= INR 1cr mean traded value.
    turnover=float((f.close*f.volume).iloc[-vol_len-1:-1].mean())
    if not 0<risk/price<=.15 or turnover<10000000:return None
    return dict(entry=price,sl=stop,t1=price+1.5*risk,t2=price+rr*risk,risk_pct=risk/price*100,
        ema9=ema,trendline=line,volume_ratio=float(f.volume.iloc[-1])/avg,
        pivot1_at=f.index[p1[0]].isoformat(),pivot2_at=f.index[p2[0]].isoformat(),
        pivot1_price=p1[1],pivot2_price=p2[1],trendline_bars=p2[0]-p1[0])


@dataclass(frozen=True)
class MorningStarSpec:
    small_body_ratio: float = .30
    middle_overlap: float = .25
    penetration: float = .50
    final_body_ratio: float = .50


def positional_morning_star(f, spec=MorningStarSpec()):
    a,b,c=f.iloc[-3],f.iloc[-2],f.iloc[-1]
    body=(f.close-f.open).abs();avgbody=body.iloc[-23:-3].mean()
    down=f.close.iloc[-4]<f.close.iloc[-8] and a.close<f.sma20.iloc[-3]
    return bool(a.close<a.open and a.open-a.close>=avgbody and abs(b.close-b.open)<=(a.open-a.close)*spec.small_body_ratio
        and max(b.open,b.close)<=a.close+(a.open-a.close)*spec.middle_overlap and c.close>c.open
        and c.close>=a.close+spec.penetration*(a.open-a.close) and c.close-c.open>=spec.final_body_ratio*(a.open-a.close) and down)
