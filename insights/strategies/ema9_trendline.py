"""EMA9 descending trendline breakout, from the user-provided specification.
Written prior-volume rule takes precedence over the PDF's unshifted sample.
"""
from __future__ import annotations
import math
from datetime import datetime,timedelta
import pandas as pd
from insights.config import IST,is_market_session
from insights.stock_scanner import session_date
from insights.indicators import clean_bars

NAME='EMA9 Trendline + Volume'

def checked(frame):
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Timezone-aware OHLCV required')
    f=clean_bars(frame);f.index=f.index.tz_convert(IST)
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

def last_session(d,holidays):
    for _ in range(15):
        if is_market_session(datetime(d.year,d.month,d.day,10,tzinfo=IST),holidays):return d
        d-=timedelta(days=1)
    raise ValueError('Cannot establish period close')

def hourly_close(now,holidays):
    if holidays is None:raise ValueError('Verified holiday calendar required')
    today_session=is_market_session(now.replace(hour=10,minute=0),holidays)
    base=pd.Timestamp(now).normalize()
    closes=[base+pd.Timedelta(hours=10,minutes=15)+pd.Timedelta(hours=i) for i in range(6)] if today_session else []
    finished=[t for t in closes if t<=pd.Timestamp(now)]
    if finished:return finished[-1]
    prev=last_session(now.date()-timedelta(days=1),holidays)
    return pd.Timestamp(datetime(prev.year,prev.month,prev.day,15,15,tzinfo=IST))

def require_known_sessions(f,now,holidays):
    # Only the configured current-year holiday calendar is authoritative.
    dates={x.date() for x in f.index}
    start=max(f.index[0].date(),datetime(now.year,1,1).date());end=f.index[-1].date()
    while start<=end:
        if is_market_session(datetime(start.year,start.month,start.day,10,tzinfo=IST),holidays) and start not in dates:
            raise ValueError('Missing session: '+start.isoformat())
        start+=timedelta(days=1)


def completed(frame,timeframe,now,holidays):
    f=checked(frame)
    if holidays is None:raise ValueError('Verified holiday calendar required')
    if timeframe=='1H':
        mins=f.index.hour*60+f.index.minute
        f=f[(mins>=555)&(mins<=855)&((mins-555)%60==0)&(f.index+pd.Timedelta(hours=1)<=pd.Timestamp(now))]
        expected=hourly_close(now,holidays)
        if f.empty or f.index[-1]+pd.Timedelta(hours=1)!=expected:raise ValueError('Stale/misaligned 1H candles')
        require_known_sessions(f,now,holidays)
        # Reject holes within each available session, excluding the deliberately omitted last 15m stub.
        for _,g in f.groupby(f.index.date):
            start=g.index[0].normalize()+pd.Timedelta(hours=9,minutes=15)
            if not g.index.equals(pd.date_range(start,g.index[-1],freq='h')):raise ValueError('Missing hourly candles')
        return f
    expected=session_date(now,holidays)
    f.index=f.index.normalize();f=f[f.index.date<=expected]
    if f.index.has_duplicates or f.empty or f.index[-1].date()!=expected:raise ValueError('Stale/duplicate daily candles')
    require_known_sessions(f,now,holidays)
    if timeframe=='1D':return f
    if timeframe not in ('1W','1M'):raise ValueError('Unknown EMA9 timeframe')
    rule='W-FRI' if timeframe=='1W' else 'ME'
    groups=f.resample(rule);bars=groups.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    # Drop the initial bucket: source history may start partway through it.
    bars=bars.iloc[1:]
    if bars.empty:return bars
    closed=[]
    for end in bars.index:
        end_session=last_session(end.date(),holidays)
        if end_session<=expected:
            group=groups.get_group(end)
            if group.empty:raise ValueError('Missing weekly/monthly period')
            if end.year==now.year and group.index[-1].date()!=end_session:raise ValueError('Missing period-end daily candle')
            if (end.date()-group.index[-1].date()).days>7:raise ValueError('Missing period-end history')
            closed.append(end)
    bars=bars.loc[closed]
    if bars.empty:return bars
    if bars.isna().any().any():raise ValueError('Missing weekly/monthly period')
    bars.attrs['last_closed_at']=(groups.get_group(bars.index[-1]).index[-1]+pd.Timedelta(hours=15,minutes=40)).isoformat()
    return bars

def make_row(frame,item,timeframe,adjusted=False):
    signal=check_signal(frame)
    if signal is None:return None
    stamp=frame.index[-1]
    # Resampled labels can fall on holidays/weekends; readiness starts only after period end.
    end=pd.Timestamp(frame.attrs['last_closed_at']) if frame.attrs.get('last_closed_at') else stamp+pd.Timedelta(hours=1) if timeframe=='1H' else stamp.normalize()+pd.Timedelta(hours=15,minutes=40)
    r=dict(key=f"{item['segment']}:{item['id']}:EMA9:{timeframe}:{stamp.isoformat()}",
        symbol=item.get('ticker') or item['symbol'],company=item['symbol'],exchange=item['segment'].split('_')[0],security_id=str(item['id']),
        strategy=NAME,timeframe=timeframe,trade_type='POSITIONAL',side='BUY',signal_at=stamp.isoformat(),signal_end=end.isoformat(),
        entry_basis='Closed signal candle reference; next-candle execution may differ.',
        target_basis='T1: added 1.5R planning level; T2: PDF target at 3R.',
        exit_rule='Stop below previous 10 candles; 3R target. Optional EMA/trailing exits are disabled (PDF default).',
        reason=f"Fresh descending-line breakout; close > EMA9 {signal['ema9']:.2f}; volume {signal['volume_ratio']:.2f}× prior 20-bar mean; confirmed lower highs {signal['trendline_bars']} bars apart.",
        adjustment_status='USER-CONFIRMED ADJUSTED SOURCE' if adjusted else 'ADJUSTMENT UNVERIFIED — RESEARCH ONLY',
        status='WAITING FOR PRICE' if adjusted else 'ADJUSTMENT UNVERIFIED — RESEARCH ONLY',last_price=None,price_at=None)
    r.update({k:round(v,6) if isinstance(v,float) else v for k,v in signal.items()})
    for k in ('entry','sl','t1','t2','risk_pct'):r[k]=round(r[k],2)
    if not 0<r['sl']<r['entry']<r['t1']<r['t2']:return None
    return r

def price_path_complete(row,five,now,holidays):
    if five is None or five.empty:return False
    start=pd.Timestamp(row['signal_end']).tz_convert(IST);end=five.index[-1].tz_convert(IST)
    if start>end:return False
    expected=[]
    for day in pd.date_range(start.normalize(),end.normalize(),freq='D'):
        if not is_market_session(day.to_pydatetime().replace(hour=10,minute=0),holidays):continue
        for t in pd.date_range(day+pd.Timedelta(hours=9,minutes=15),periods=75,freq='5min'):
            if start<=t<=end and t+pd.Timedelta(minutes=5)<=pd.Timestamp(now):expected.append(t)
    return bool(expected) and set(expected).issubset(set(five.index))


class EMA9Scanner:
    """Long histories refresh once per completed day; hourly once per closed hour."""
    def __init__(self,broker,call,adjusted=False):
        self.broker=broker;self.call=call;self.adjusted=adjusted;self.cache={}
    def scan(self,item,now,holidays):
        key=item['segment']+':'+str(item['id']);rows=[];checks=[]
        for group in ('daily','hourly'):
            token=session_date(now,holidays) if group=='daily' else hourly_close(now,holidays).isoformat()
            cache_key=(key,group);cached=self.cache.get(cache_key)
            if cached and cached[0]==token:
                rows.extend(cached[1]);checks.extend(cached[2]);continue
            found=[];coverage=[]
            timeframes=('1D','1W','1M') if group=='daily' else ('1H',)
            try:
                raw=self.call(lambda:self.broker.daily(item,now,days=3650)) if group=='daily' else self.call(lambda:self.broker.history(item,now,minutes=60,lookback_days=90))
                for tf in timeframes:
                    try:
                        f=completed(raw,tf,now,holidays)
                        row=make_row(f,item,tf,self.adjusted) if len(f)>=60 else None
                        if row:found.append(row)
                        coverage.append(dict(symbol=item['symbol'],timeframe=tf,bars=len(f),status='CHECKED' if len(f)>=60 else 'INSUFFICIENT HISTORY (need 60 closed bars)'))
                    except (ValueError,TypeError,KeyError) as exc:coverage.append(dict(symbol=item['symbol'],timeframe=tf,status=str(exc)[:180]))
                self.cache[cache_key]=(token,found,coverage)
            except TimeoutError:raise
            except Exception as exc:
                coverage=[dict(symbol=item['symbol'],timeframe=tf,status='SOURCE ERROR: '+str(exc)[:140]) for tf in timeframes]
            rows.extend(found);checks.extend(coverage)
        return rows,checks
