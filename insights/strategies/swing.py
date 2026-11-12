"""Completed daily-candle swing setups; no future-bar data or broker orders.

All entries are *research reference closes*, not broker fill prices.
Return rows only for a confirmed close; target2 is 3R, target1 is 2R.
"""
from __future__ import annotations
import math
import pandas as pd

NAME='Daily swing research'
VERSION='1.0'


def _rsi(close, period=14):
    diff=close.diff()
    gains=diff.clip(lower=0).ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    losses=(-diff.clip(upper=0)).ewm(alpha=1/period,adjust=False,min_periods=period).mean()
    result=100-100/(1+gains/losses.replace(0,float('nan')))
    return result.where(losses>0,100).where(gains>0,0)


def _atr(f,period=14):
    tr=pd.concat([f.high-f.low,(f.high-f.close.shift()).abs(),
        (f.low-f.close.shift()).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/period,adjust=False,min_periods=period).mean()


def _adx(f,period=14):
    high_move=f.high.diff()
    low_move=-f.low.diff()
    plus=high_move.where((high_move>low_move)&(high_move>0),0.0)
    minus=low_move.where((low_move>high_move)&(low_move>0),0.0)
    atr=_atr(f,period)
    pdi=100*plus.ewm(alpha=1/period,adjust=False,min_periods=period).mean()/atr.replace(0,float('nan'))
    mdi=100*minus.ewm(alpha=1/period,adjust=False,min_periods=period).mean()/atr.replace(0,float('nan'))
    dx=100*(pdi-mdi).abs()/(pdi+mdi).replace(0,float('nan'))
    return dx.ewm(alpha=1/period,adjust=False,min_periods=period).mean()


def _supertrend(f,period=10,multiplier=3):
    atr=_atr(f,period)
    middle=(f.high+f.low)/2
    upper=middle+multiplier*atr
    lower=middle-multiplier*atr
    final_upper=upper.copy()
    final_lower=lower.copy()
    trend=pd.Series(index=f.index,dtype=float)
    line=pd.Series(index=f.index,dtype=float)
    start=period+1
    for i in range(start,len(f)):
        if not math.isfinite(float(atr.iloc[i])):continue
        prev=i-1
        final_upper.iloc[i]=(upper.iloc[i] if upper.iloc[i]<final_upper.iloc[prev]
            or f.close.iloc[prev]>final_upper.iloc[prev] else final_upper.iloc[prev])
        final_lower.iloc[i]=(lower.iloc[i] if lower.iloc[i]>final_lower.iloc[prev]
            or f.close.iloc[prev]<final_lower.iloc[prev] else final_lower.iloc[prev])
        if not math.isfinite(float(trend.iloc[prev])):
            trend.iloc[i]=1. if f.close.iloc[i]>final_upper.iloc[i] else -1.
        elif trend.iloc[prev]>0:
            trend.iloc[i]=-1. if f.close.iloc[i]<final_lower.iloc[i] else 1.
        else:
            trend.iloc[i]=1. if f.close.iloc[i]>final_upper.iloc[i] else -1.
        line.iloc[i]=final_lower.iloc[i] if trend.iloc[i]>0 else final_upper.iloc[i]
    return trend,line


def scan(frame,symbol,asof=None):
    """Return distinct confirmed long-only swing setups sorted by R:R/strength.

    Caller supplies exclusively completed daily candles. asof is used to
    reject a future/partial daily candle if accidentally included.
    """
    if frame is None or not isinstance(frame,pd.DataFrame) or len(frame)<260:
        return []
    required={'open','high','low','close','volume'}
    if not required.issubset(frame.columns):return []
    f=frame.sort_index().copy()
    if not isinstance(f.index,pd.DatetimeIndex) or f.index.tz is None:return []
    if asof is not None:
        boundary=pd.Timestamp(asof)
        if boundary.tzinfo is None:return []
        f=f[f.index.date<=boundary.date()]
    if len(f)<260 or f.index.has_duplicates:return []
    try:
        f[list(required)]=f[list(required)].astype(float)
    except (TypeError,ValueError):return []
    if not f[list(required)].notna().all().all():return []
    if (f[['open','high','low','close']]<=0).any().any() or (f.volume<0).any():return []
    close=f.close
    ema21=close.ewm(span=21,adjust=False).mean()
    ema50=close.ewm(span=50,adjust=False).mean()
    ema200=close.ewm(span=200,adjust=False).mean()
    sma200=close.rolling(200).mean()
    atr=_atr(f);adx=_adx(f);rsi=_rsi(close)
    st_dir,st_line=_supertrend(f)
    c=float(close.iloc[-1]);a=float(atr.iloc[-1])
    if not math.isfinite(a) or a<=0:return []
    vol20=float(f.volume.iloc[-21:-1].mean())
    vol50=float(f.volume.iloc[-51:-1].mean())
    volume_ratio=float(f.volume.iloc[-1])/vol50 if vol50>0 else None
    strength=round(max(0,min(100,
        (float(adx.iloc[-1]) if math.isfinite(float(adx.iloc[-1])) else 0)*1.1+
        max(0,(c/float(ema50.iloc[-1])-1)*100)*3)),1)
    trend_ok=(c>ema50.iloc[-1] and ema21.iloc[-1]>ema50.iloc[-1]
              and ema50.iloc[-1]>ema50.iloc[-6])
    rows=[]
    def add(strategy,stop,reason,trail=None):
        if stop is None or not math.isfinite(float(stop)):return
        stop=float(stop)
        risk=c-stop
        if risk<=0 or risk/c<.002 or risk/c>.15:return
        # Entry observed at daily close. No price level is an execution order.
        rows.append(dict(symbol=symbol,strategy=strategy,entry=round(c,2),
            stop=round(stop,2),target=round(c+2*risk,2),
            target_3r=round(c+3*risk,2),risk_reward=2.0,trend_strength=strength,
            volume_ratio=round(volume_ratio,2) if volume_ratio is not None else None,
            asof=f.index[-1].date().isoformat(),status='RESEARCH ONLY — DAILY CLOSE',
            trail_rule=trail or 'Review stop as new daily candles complete',
            reason=reason,optional_above_sma200=bool(c>sma200.iloc[-1])))

    # 1) 21/50 trend pullback with re-cross / bullish previous-day-high break.
    if trend_ok:
        touch=any(float(f.low.iloc[j])<=float(ema21.iloc[j])*1.008
                  and float(f.high.iloc[j])>=float(ema50.iloc[j])*.992
                  for j in range(-8,-1))
        recross=(close.iloc[-2]<=ema21.iloc[-2] and c>ema21.iloc[-1])
        bullish_high=(c>float(f.high.iloc[-2]) and c>float(f.open.iloc[-1]))
        if touch and (recross or bullish_high):
            # Tightest valid candidate among 50 EMA, swing low, 1.5 ATR.
            stops=[float(ema50.iloc[-1])*.995,
                float(f.low.iloc[-11:-1].min())*.995,c-1.5*a]
            valid=[x for x in stops if x<c]
            if valid:add('21/50 EMA trend pullback',max(valid),
                '21 EMA reclaim or prior-day bullish high break after pullback; 50 EMA rising',
                'Exit on completed daily close below EMA21 or trail by daily swing low')

    # 2) Prior 20-session consolidation breakout, huge volume, near 52w high.
    max20=float(f.high.iloc[-21:-1].max())
    high52=float(f.high.iloc[-253:].max())
    if (c>max20 and vol50>0 and volume_ratio>=1.5 and c>=.85*high52):
        stop=min(float(f.low.iloc[-1]),float(f.low.iloc[-21:-1].min()))*.995
        add('Consolidation breakout',stop,
            'Close above preceding 20-day high; volume >=1.5x prior 50-day average; within 15% of 52-week high')

    # 3) RSI dip into 40-50, then crosses back above 50 while long trend holds.
    r_prev=float(rsi.iloc[-2]);r_now=float(rsi.iloc[-1])
    prior_dip=bool(((rsi.iloc[-12:-1]>=40)&(rsi.iloc[-12:-1]<=50)).any())
    if (c>ema50.iloc[-1]>ema200.iloc[-1] and prior_dip
        and math.isfinite(r_prev) and r_prev<=50 and r_now>50 and r_now<70):
        add('RSI pullback in uptrend',float(f.low.iloc[-11:].min())*.995,
            'RSI(14) previously 40–50 and crosses above 50 while EMA50 > EMA200',
            'Consider previous high and RSI>70 turning down for profit management')

    # 4) Supertrend(10,3) flips bullish with EMA agreement.
    if (math.isfinite(float(st_dir.iloc[-2])) and st_dir.iloc[-2]<0
        and st_dir.iloc[-1]>0 and c>ema21.iloc[-1]>ema50.iloc[-1]):
        add('Supertrend(10,3) + EMA',float(st_line.iloc[-1])*.995,
            'Completed daily Supertrend flip to BUY with EMA21 above EMA50',
            'Trail using completed daily Supertrend line')

    # Optional crossover variant; ADX and volume must confirm.
    if (ema21.iloc[-2]<=ema50.iloc[-2] and ema21.iloc[-1]>ema50.iloc[-1]
        and c>ema50.iloc[-1] and math.isfinite(float(adx.iloc[-1]))
        and adx.iloc[-1]>20 and vol20>0 and f.volume.iloc[-1]>vol20):
        add('EMA21/50 crossover + ADX',c-1.5*a,
            'Daily bullish EMA crossover; ADX>20 and volume above prior 20-day mean')

    return sorted(rows,key=lambda r:(-r['risk_reward'],-r['trend_strength'],-(r['volume_ratio'] or 0),r['symbol']))
