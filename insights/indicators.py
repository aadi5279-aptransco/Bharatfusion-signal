"""Price-only calculations: require complete, chronological licensed candles."""
from __future__ import annotations
import math
import pandas as pd


def clean_bars(frame):
    if frame is None or not isinstance(frame,pd.DataFrame):raise ValueError('Missing Dhan candles')
    cols=['open','high','low','close','volume']
    if not set(cols).issubset(frame.columns):raise ValueError('Missing OHLCV columns')
    f=frame[cols].copy().astype(float).sort_index()
    if f.empty or f.index.has_duplicates or not f.index.is_monotonic_increasing:raise ValueError('Invalid candle ordering')
    if not f.notna().all().all() or not (f[['open','high','low','close']]>0).all().all() or (f.volume<0).any():raise ValueError('Invalid candle values')
    if (f.high<f[['open','close','low']].max(axis=1)).any() or (f.low>f[['open','close','high']].min(axis=1)).any():raise ValueError('Invalid OHLC')
    return f


def add_features(frame):
    f=clean_bars(frame)
    if len(f)<201:raise ValueError('Need 201 completed candles for EMA200')
    c=f.close
    for span in (9,20,21,50,200):f[f'ema{span}']=c.ewm(span=span,adjust=False).mean()
    tr=pd.concat([(f.high-f.low),(f.high-c.shift()).abs(),(f.low-c.shift()).abs()],axis=1).max(axis=1)
    f['atr']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    up=f.high.diff();down=-f.low.diff()
    plus=up.where((up>down)&(up>0),0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    minus=down.where((down>up)&(down>0),0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    dx=100*(plus-minus).abs()/(plus+minus).replace(0,float('nan'))
    f['adx']=dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    d=f.index.date
    tp=(f.high+f.low+f.close)/3
    f['vwap']=(tp*f.volume).groupby(d).cumsum()/f.volume.groupby(d).cumsum().replace(0,float('nan'))
    f['rvol']=f.volume/f.volume.shift(1).rolling(20).mean().replace(0,float('nan'))
    f['resistance']=f.high.shift(1).rolling(20).max()
    f['support']=f.low.shift(1).rolling(20).min()
    return f


def index_bias(frame, symbol, vix=None):
    """Scores only facts observed in candles. Missing confirmations are not guessed."""
    try:f=add_features(frame)
    except ValueError as e:return dict(symbol=symbol,bias='UNAVAILABLE',score=None,reasons=[],warnings=[str(e)])
    x=f.iloc[-1];close=float(x.close);score=0;reasons=[];warnings=[]
    if x.ema20>x.ema50>x.ema200 and close>x.ema20:
        score+=35;reasons.append('EMA20 > EMA50 > EMA200 with close above EMA20')
    elif x.ema20<x.ema50<x.ema200 and close<x.ema20:
        score-=35;reasons.append('EMA20 < EMA50 < EMA200 with close below EMA20')
    else: reasons.append('EMAs are not fully aligned')
    if not math.isfinite(x.adx):warnings.append('ADX unavailable')
    elif x.adx>=22 and abs(score)>=30:
        score+=20*(1 if score>0 else -1);reasons.append(f'ADX {x.adx:.1f} confirms trend strength')
    else:reasons.append('ADX below confirmation threshold or trend unaligned')
    if math.isfinite(x.vwap):
        score+=15 if close>x.vwap else -15
        reasons.append('Last close above session VWAP' if close>x.vwap else 'Last close below session VWAP')
    else:warnings.append('Session VWAP unavailable')
    high=f.high.shift(1).tail(20).max();low=f.low.shift(1).tail(20).min()
    if close>high:score+=20;reasons.append('Breaks previous 20-candle high')
    elif close<low:score-=20;reasons.append('Breaks previous 20-candle low')
    else:reasons.append('Within previous 20-candle range')
    if vix is None:warnings.append('India VIX missing; risk filter not scored')
    elif vix>22:warnings.append('Elevated India VIX; caution')
    # FII/DII are not available from OHLCV; never infer institutional flow.
    warnings.append('FII/DII not scored without licensed data')
    score=max(-100,min(100,score))
    bias='Uptrend' if score>=40 else 'Downtrend' if score<=-40 else 'Sideways'
    return dict(symbol=symbol,bias=bias,score=score,reasons=reasons,warnings=warnings,close=round(close,2),asof=str(f.index[-1]))


def risk_levels(entry,atr,direction, stop=None):
    entry=float(entry);atr=float(atr)
    if not math.isfinite(atr) or atr<=0:raise ValueError('ATR unavailable')
    sign=1 if direction in ('BUY','CE') else -1
    risk=max(atr,0.002*entry)
    sl=float(stop) if stop is not None else entry-sign*risk
    risk=sign*(entry-sl)
    if risk<=0 or risk/entry>.06:raise ValueError('Invalid or excessive stop risk')
    return dict(entry=round(entry,2),sl=round(sl,2),t1=round(entry+sign*1.5*risk,2),t2=round(entry+sign*2.5*risk,2),rr=1.5)
