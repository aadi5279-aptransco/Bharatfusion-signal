"""Only application adapter for /patterns. No pattern formulas belong in tabs."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timedelta
import math
import json
import os
from pathlib import Path
import pandas as pd
from patterns import Bar, Context, PatternConfig, scan, CANDLE_NAMES, CHART_NAMES
from insights.config import IST

INTERVALS={'5m':5,'15m':15,'1h':60}
TIMEFRAMES=tuple(INTERVALS)+('daily','weekly','monthly')


def bars_from_frame(frame, timeframe, now, holidays):
    if timeframe not in TIMEFRAMES:raise ValueError('Unsupported pattern timeframe')
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Timezone-aware dated OHLCV required')
    f=frame.copy();f.index=f.index.tz_convert(IST)
    if f.index.has_duplicates or not f.index.is_monotonic_increasing:raise ValueError('Duplicate or unordered candles')
    if not {'open','high','low','close','volume'}.issubset(f):raise ValueError('OHLCV columns missing')
    if holidays is None:raise ValueError('Configured exchange calendar required')
    regular=lambda d:d.weekday()<5 and d not in holidays
    if timeframe in INTERVALS:
        minutes=INTERVALS[timeframe]
        closed=f.index+pd.Timedelta(minutes=minutes)
        f=f[closed<=now]
        if any(not regular(d) for d in f.index.date):raise ValueError('Non-regular session requires reviewed session data')
        result=[]
        for t,r in f.iterrows():
            result.append(Bar(t.to_pydatetime(),(t+pd.Timedelta(minutes=minutes)).to_pydatetime(),
                *(float(r[k]) for k in ('open','high','low','close','volume')),
                circuit_locked=bool(r.get('circuit_locked',False)),eligible=bool(r.get('eligible',True))))
        return tuple(result)
    f=f[f.index.normalize()+pd.Timedelta(hours=15,minutes=40)<=now]
    f.index=f.index.normalize()
    if f.index.has_duplicates:raise ValueError('Duplicate daily sessions')
    if any(not regular(d) for d in f.index.date):raise ValueError('Unreviewed special-session daily candle')
    if timeframe=='daily':
        return tuple(Bar(t.to_pydatetime(),(t+pd.Timedelta(hours=15,minutes=40)).to_pydatetime(),
            *(float(r[k]) for k in ('open','high','low','close','volume')),
            circuit_locked=bool(r.get('circuit_locked',False)),eligible=bool(r.get('eligible',True))) for t,r in f.iterrows())
    # Explicit start/end buckets. A weekly bar is released only after Sunday,
    # a monthly bar only after calendar month-end. This conservatively avoids
    # guessing a special session during the remainder of the period.
    groups={}
    for t,r in f.iterrows():
        start=t-pd.Timedelta(days=t.weekday()) if timeframe=='weekly' else t.replace(day=1)
        groups.setdefault(start,[]).append((t,r))
    result=[]
    for start,rows in sorted(groups.items()):
        end=start+pd.Timedelta(days=7) if timeframe=='weekly' else start+pd.offsets.MonthBegin(1)
        if end>now:continue
        expected=[d.date() for d in pd.date_range(start,end-pd.Timedelta(days=1),freq='D') if regular(d.date())]
        if [t.date() for t,r in rows]!=expected:continue # Never aggregate incomplete periods.
        rs=[r for t,r in rows]
        result.append(Bar(start.to_pydatetime(),end.to_pydatetime(),float(rs[0].open),
            max(float(r.high) for r in rs),min(float(r.low) for r in rs),float(rs[-1].close),
            sum(float(r.volume) for r in rs),any(bool(r.get('circuit_locked',False)) for r in rs),all(bool(r.get('eligible',True)) for r in rs)))
    return tuple(result)


def evidence(frame,timeframe,now,holidays,*,tick_size=None,eligibility_verified=False,all_time_history=False,config=None):
    """Morphology can be shown without inventing executable metadata.

    Confirmation describes closed geometry + volume. Unknown exchange eligibility
    or tick size suppresses plans at the adapter boundary, with explicit reasons.
    """
    empty=dict(engine='patterns-v1',timeframe=timeframe,patterns=[],confirmed=0,
               entry_ready=0,score_type='RULE SCORE — NOT PROBABILITY',research_only=True)
    try:
        b=bars_from_frame(frame,timeframe,now,holidays)
        if not b:return dict(empty,status='INSUFFICIENT COMPLETED HISTORY')
        known_tick=isinstance(tick_size,(int,float)) and math.isfinite(tick_size) and tick_size>0
        # Placeholder only for internal geometry; every computed plan is stripped
        # when tick metadata is absent. Never display an assumed tick-based entry.
        ctx=Context(tick_size=tick_size if known_tick else .01,all_time_history=all_time_history)
        result=scan(b,timeframe,now,config=config,context=ctx)
        rows=[]
        for item in result:
            row=item.to_dict();reasons=[]
            if not known_tick:reasons.append('Instrument tick size unverified')
            if not eligibility_verified:reasons.append('Dated circuit/ban/surveillance eligibility unverified')
            row['geometry_confirmed']=row['confirmed']
            row['entry_ready']=bool(row['confirmed'] and not reasons)
            if reasons:
                row.update(confirmed=False,status='forming',entry=None,stop=None,target=None)
                row['context']+=reasons
            rows.append(row)
        return dict(empty,status='READY — PATTERN RESEARCH',patterns=rows,
                    confirmed=sum(r['geometry_confirmed'] for r in rows),entry_ready=sum(r['entry_ready'] for r in rows),
                    asof=b[-1].closed_at.isoformat(),bars=len(b),
                    note='Closed pattern evidence is not a fill. Unknown eligibility suppresses entry levels. Scores are not win probabilities.')
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        return dict(empty,status='UNAVAILABLE',reason=str(exc)[:180])


def inspect(service,symbol,timeframe,now,holidays):
    if not isinstance(symbol,str) or not 0<len(symbol.strip())<=64:raise ValueError('Choose a mapped stock or index')
    if timeframe not in TIMEFRAMES:raise ValueError('Choose 5m, 15m, 1h, daily, weekly or monthly')
    if not service._job_lock.acquire(blocking=False):
        return dict(status='BUSY — background scan in progress; retry shortly',patterns=[])
    try:
        item=service._lookup(symbol.strip())
        if item is None and getattr(service,'nifty500',None) is not None:
            normalize=lambda v:''.join(c for c in str(v).upper() if c.isalnum())
            members,_=service.nifty500.resolve(now)
            matches=[x for x in members if normalize(symbol) in (normalize(x.get('symbol','')),normalize(x.get('ticker','')))]
            identities={(x['segment'],str(x['id'])) for x in matches}
            if len(identities)==1:item=matches[0]
        if item is None:raise ValueError('Symbol not found unambiguously in Dhan/NIFTY 500 mapping')
        if timeframe in INTERVALS:
            frame=service.broker.history(item,now,minutes=INTERVALS[timeframe],lookback_days=30)
        else:frame=service.broker.daily(item,now,days=1600 if timeframe=='monthly' else 800 if timeframe=='weekly' else 450)
        config=load_config()
        result=evidence(frame,timeframe,now,holidays,tick_size=item.get('tick_size'),config=config)
        return dict(result,symbol=item['symbol'],catalogue=list(CANDLE_NAMES+CHART_NAMES))
    finally:service._job_lock.release()


def load_config():
    path=os.getenv('INSIGHTS_PATTERNS_CONFIG')
    if not path:return PatternConfig()
    raw=Path(path).read_text(encoding='utf-8')
    if len(raw)>64000:raise ValueError('Pattern config too large')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('Pattern config must be an object')
    try:return PatternConfig(**value)
    except (TypeError,ValueError) as exc:raise ValueError('Invalid pattern config: '+str(exc)) from None
