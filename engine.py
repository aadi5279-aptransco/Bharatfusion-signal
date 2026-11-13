"""Causal research rules. No calibrated probabilities and no order execution."""
from __future__ import annotations
import numpy as np
import pandas as pd

IST = 'Asia/Kolkata'
COLS = ['open', 'high', 'low', 'close', 'volume']


def clean(frame):
    f = frame.copy()
    if not isinstance(f.index, pd.DatetimeIndex) or f.index.tz is None:
        raise ValueError('Timestamp index must be timezone-aware')
    f.index = f.index.tz_convert(IST)
    f = f[COLS].astype(float).sort_index()
    f = f[~f.index.duplicated(keep='last')]
    if not np.isfinite(f.to_numpy()).all():
        raise ValueError('Non-finite OHLCV')
    if ((f[['open','high','low','close']] <= 0).any(axis=1) | (f.volume < 0) |
        (f.high < f[['open','close','low']].max(axis=1)) |
        (f.low > f[['open','close','high']].min(axis=1))).any():
        raise ValueError('Invalid OHLCV')
    return f.between_time('09:15','15:29')


def bars(frame, minutes, now):
    """Session anchored. Reject partial/gapped bins, including 15:15-16:15 hour."""
    f = clean(frame)
    now = pd.Timestamp(now).tz_convert(IST)
    f = f[f.index + pd.Timedelta(minutes=1) <= now]
    if minutes not in (3,5,15,30,60,240):raise ValueError('Unsupported candle interval')
    r = f.resample(f'{minutes}min', origin='start_day', offset='9h15min')
    b = r.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    return b[(r.size() == minutes) & (b.index + pd.Timedelta(minutes=minutes) <= now)].dropna()


def features(b):
    f = b.copy()
    c = f.close
    f['ema9'] = c.ewm(span=9, adjust=False, min_periods=9).mean()
    f['ema21'] = c.ewm(span=21, adjust=False, min_periods=21).mean()
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/9, adjust=False, min_periods=9).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/9, adjust=False, min_periods=9).mean()
    f['rsi'] = (100 - 100/(1 + gain/loss.replace(0,np.nan))).where(loss > 0,100).where((gain+loss)>0,50)
    tr = pd.concat([f.high-f.low,(f.high-c.shift()).abs(),(f.low-c.shift()).abs()],axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    f['atr'] = atr
    up, down = f.high.diff(), -f.low.diff()
    plus = up.where((up>down)&(up>0),0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr*100
    minus = down.where((down>up)&(down>0),0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr*100
    f['adx'] = ((plus-minus).abs()/(plus+minus).replace(0,np.nan)*100).ewm(alpha=1/14,adjust=False,min_periods=14).mean().fillna(0)
    session = f.index.date
    f['vwap'] = (((f.high+f.low+c)/3*f.volume).groupby(session).cumsum() /
                 f.volume.groupby(session).cumsum().replace(0,np.nan))
    f['rvol'] = f.volume / f.volume.shift(1).rolling(20).mean().replace(0,np.nan)
    f['resistance'] = f.high.shift(1).rolling(20).max()
    f['support'] = f.low.shift(1).rolling(20).min()
    return f


def analyze(frame, symbol, kind='stock', minutes=3, now=None, threshold=75):
    now = pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now).tz_convert(IST)
    b = bars(frame,minutes,now)
    result = dict(symbol=symbol,kind=kind,action='WAIT',score=0,close=None,entry=None,stop=None,t1=None,t2=None,
                  candle='',bias='WARMUP',reasons=[],blockers=[],chart=[],htf={})
    if len(b)<60:
        # Fail closed with *all* applicable blockers. Weekend/out-of-window
        # status must remain visible even when history is too short to score.
        result['blockers']=['Need at least 60 complete entry-timeframe candles']
        minute=now.hour*60+now.minute
        if now.weekday()>=5 or not 9*60+30<=minute<15*60:
            result['blockers'].append('Outside entry window 09:30–15:00 IST weekdays')
        return result
    f=features(b); x=f.iloc[-1]; stamp=f.index[-1]
    result.update(close=float(x.close),candle=stamp.isoformat(),chart=[{'time':t.isoformat(),**{k:float(v) for k,v in row.items()}} for t,row in b.tail(90).iterrows()])
    htf={}
    for m in (15,30,60):
        h=bars(frame,m,now)
        if len(h)<30: htf[str(m)]='WARMUP'
        else:
            e=features(h).iloc[-1]
            htf[str(m)]='BULL' if e.close>e.ema9>e.ema21 else 'BEAR' if e.close<e.ema9<e.ema21 else 'MIXED'
    result['htf']=htf
    direction = 1 if x.ema9>x.ema21 else -1
    bias='BULL' if direction==1 else 'BEAR'
    result['bias']=bias
    reasons=[]; blockers=[]; earned=0; possible=0
    def vote(name, condition, weight):
        nonlocal earned,possible
        possible+=weight
        if condition: earned+=weight; reasons.append(name)
    vote('EMA 9/21 aligned', direction*(x.close-x.ema9)>0,15)
    vote('RSI momentum', 52<=x.rsi<=72 if direction==1 else 28<=x.rsi<=48,10)
    vote('ADX >= 20', x.adx>=20,10)
    for m in (15,30,60): vote(f'{m}m {bias.lower()} trend',htf[str(m)]==bias,10)
    if kind=='stock':
        vote('Session VWAP aligned',direction*(x.close-x.vwap)>0,10)
        vote('Relative volume >= 1.5',x.rvol>=1.5,10)
        if not np.isfinite(x.rvol) or x.rvol<1.0: blockers.append('Volume confirmation absent')
    # Explicit range-break/retest approximation, not proprietary SMC.
    retest=False
    for j in range(max(21,len(f)-6),len(f)-1):
        a=f.iloc[j]
        if f.index[j].date()!=stamp.date(): continue
        level=a.resistance if direction==1 else a.support
        broke=a.close>level if direction==1 else a.close<level
        subsequent=f.iloc[j+1:]
        held=(subsequent.close>=level-x.atr*.2).all() if direction==1 else (subsequent.close<=level+x.atr*.2).all()
        touch=x.low<=level+x.atr*.2 and x.close>level if direction==1 else x.high>=level-x.atr*.2 and x.close<level
        if broke and held and touch and (kind!='stock' or a.rvol>=1.5): retest=True
    vote('Range break and retest held',retest,15)
    prev=f.iloc[-2]
    sweep_up=x.low<x.support and x.close>x.support
    sweep_down=x.high>x.resistance and x.close<x.resistance
    if sweep_up: reasons.append('Downside range sweep reclaimed (price proxy)')
    if sweep_down: reasons.append('Upside range sweep rejected (price proxy)')
    if (direction==1 and sweep_down) or (direction==-1 and sweep_up): blockers.append('Opposing liquidity-sweep proxy')
    if x.low>f.iloc[-3].high: reasons.append('Three-candle bullish gap (FVG proxy)')
    if x.high<f.iloc[-3].low: reasons.append('Three-candle bearish gap (FVG proxy)')
    if not retest: blockers.append('Waiting for confirmed range break/retest')
    if any(v=='WARMUP' for v in htf.values()): blockers.append('Higher-timeframe history incomplete')
    if sum(v==bias for v in htf.values())<2: blockers.append('Fewer than 2 higher timeframes aligned')
    if x.adx<20: blockers.append('Weak trend / possible chop')
    age=(now-(stamp+pd.Timedelta(minutes=minutes))).total_seconds()
    if age>max(180,minutes*60) or age<0: blockers.append('STALE candles')
    minute=now.hour*60+now.minute
    if now.weekday()>=5 or not 9*60+30<=minute<15*60:
        blockers.append('Outside entry window 09:30–15:00 IST weekdays')
    if not np.isfinite(x.atr) or x.atr<=0: blockers.append('Invalid ATR')
    if abs(x.close-x.ema21)>2*x.atr: blockers.append('Extended more than 2 ATR from EMA21')
    score=round(100*earned/possible)
    if score<threshold: blockers.append(f'Agreement below {threshold}/100')
    if not blockers:
        risk=max(x.atr, x.close-f.low.tail(5).min() if direction==1 else f.high.tail(5).max()-x.close)
        result.update(action='BUY SETUP' if direction==1 else 'SELL SETUP',entry=float(x.close),stop=float(x.close-direction*risk),
                      t1=float(x.close+direction*risk*1.5),t2=float(x.close+direction*risk*2.5))
    from screening import momentum_metrics
    result.update(momentum_metrics(b))
    result['context']=[{'time':t.isoformat(),**{k:float(v) for k,v in row.items()}} for t,row in b.tail(256).iterrows()]
    result.update(score=score,reasons=reasons,blockers=blockers,
                  rsi=round(float(x.rsi),1),adx=round(float(x.adx),1),rvol=round(float(x.rvol),2) if np.isfinite(x.rvol) else None)
    return result


def demo_frame(seed=1,days=14):
    rng=np.random.default_rng(seed)
    days=pd.bdate_range(end=pd.Timestamp.now(tz=IST).normalize()-pd.Timedelta(days=1),periods=days)
    idx=pd.DatetimeIndex([t for d in days for t in pd.date_range(d+pd.Timedelta(hours=9,minutes=15),periods=375,freq='min')])
    close=1000+np.cumsum(rng.normal(.025,.7,len(idx)))
    op=np.r_[close[0],close[:-1]]
    return pd.DataFrame(dict(open=op,high=np.maximum(op,close)+rng.uniform(.1,.8,len(idx)),low=np.minimum(op,close)-rng.uniform(.1,.8,len(idx)),close=close,volume=rng.integers(10000,80000,len(idx))),index=idx)
