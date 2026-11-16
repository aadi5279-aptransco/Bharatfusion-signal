"""Explainable prior-session setups. Thresholds are research defaults, not fitted accuracy."""
import math
import pandas as pd
from insights.config import IST
from insights.indicators import clean_bars

VERSION = 'premarket-setups-v2'


def prepare(frame, now):
    if not isinstance(frame, pd.DataFrame) or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Timezone-aware daily candles required')
    t = pd.Timestamp(now)
    if t.tzinfo is None: raise ValueError('Timezone-aware scan time required')
    t = t.tz_convert(IST)
    f = frame.copy(); f.index = f.index.tz_convert(IST)
    f = f[f.index.date < t.date()] if (t.hour, t.minute) < (15, 40) else f[f.index.date <= t.date()]
    f = clean_bars(f)
    if not all(math.isfinite(v) for v in f.to_numpy().flat): raise ValueError('Non-finite daily data')
    if len(f) < 55: raise ValueError('Need at least 55 completed daily candles')
    if pd.Index(f.index.date).has_duplicates: raise ValueError('Multiple bars for one daily session')
    return f


def evaluate(f):
    x=f.iloc[-1]; prev=f.iloc[-2]; c=float(x.close)
    tr=pd.concat([f.high-f.low,(f.high-f.close.shift()).abs(),(f.low-f.close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.ewm(alpha=1/14,adjust=False).mean().iloc[-1])
    ranges=f.high-f.low; prior=f.iloc[-21:-1]
    hi=float(prior.high.max()); lo=float(prior.low.min())
    e20=float(f.close.ewm(span=20,adjust=False).mean().iloc[-1]);e50=float(f.close.ewm(span=50,adjust=False).mean().iloc[-1])
    mean_vol=float(prior.volume.mean());rv=float(x.volume)/mean_vol if mean_vol>0 else 0
    turnover=float((prior.close*prior.volume).mean())
    nr7=bool(ranges.iloc[-1]>0 and ranges.iloc[-1]<ranges.iloc[-7:-1].min())
    inside=bool(x.high<prev.high and x.low>prev.low)
    compact=bool(atr>0 and f.high.tail(5).max()-f.low.tail(5).min()<=2*atr)
    liquid=c>=20 and turnover>=5e7 and float(x.close*x.volume)>=2e7
    metrics=dict(atr=round(atr,3),average_turnover_cr=round(turnover/1e7,3),rvol=round(rv,2),nr7=nr7,inside_day=inside,compact_5day=compact)
    exclusions=[];setups=[]
    if not liquid: exclusions.append('Liquidity gate: close >=20, prior 20-day average turnover proxy >=5 crore, latest >=2 crore')
    if atr<=0: exclusions.append('Positive ATR required')
    # Exclude abnormal raw-data jumps; split adjustments cannot be inferred here.
    abnormal=abs(c/float(prev.close)-1)>.20
    if abnormal: exclusions.append('Daily jump >20%; corporate-action/data review required')
    if exclusions: return dict(setups=[],setup_score=0,setup_metrics=metrics,setup_exclusions=exclusions)
    for side,aligned,level,distance,broken,location in (
        ('BUY',c>e20>e50,hi,(hi-c)/atr,c>hi,(c-float(x.low))/max(float(x.high-x.low),.00001)),
        ('SELL',c<e20<e50,lo,(c-lo)/atr,c<lo,(float(x.high)-c)/max(float(x.high-x.low),.00001))):
        labels=[];points=0
        if aligned and 0<=distance<=.5 and (nr7 or inside or compact):
            labels.append('Compression near 20-day '+('resistance' if side=='BUY' else 'support'));points=65
        if aligned and broken and abs(distance)<=.75 and rv>=1.5 and location>=.7:
            labels.append('Volume-confirmed 20-day '+('breakout' if side=='BUY' else 'breakdown'));points=max(points,75)
        if labels:
            trigger=max(float(x.high),level) if side=='BUY' else min(float(x.low),level)
            setups.append(dict(direction=side,strategy=' + '.join(labels),score=min(100,points+(10 if nr7 else 0)+(5 if inside else 0)+(10 if rv>=1.5 else 0)),watch_above=round(trigger,2) if side=='BUY' else None,watch_below=round(trigger,2) if side=='SELL' else None,reason=f'EMA20/50 aligned; distance {distance:.2f} ATR; RVOL {rv:.2f}; close location {location:.2f}'))
    if nr7 or inside:
        setups.append(dict(direction='BOTH',strategy='NR7 / inside-day range expansion watch',score=55+(10 if nr7 and inside else 0),watch_above=round(float(x.high),2),watch_below=round(float(x.low),2),reason='Direction remains unconfirmed until the range breaks after market opens'))
    if not setups: exclusions.append('No compression-near-level or volume-confirmed continuation setup; daily percentage alone is insufficient')
    return dict(setups=setups,setup_score=max((s['score'] for s in setups),default=0),setup_metrics=metrics,setup_exclusions=exclusions)


def fetch_daily(broker, item, now):
    """Pace this batch and retry a rejected data request once; never invent candles."""
    import time
    from insights.brokers.dhan import DhanReadOnly, BrokerUnavailable
    for attempt in range(2):
        if isinstance(broker,DhanReadOnly):time.sleep(.25 if attempt==0 else 1.0)
        try:return broker.daily(item,now,days=180)
        except BrokerUnavailable:
            if attempt:raise
