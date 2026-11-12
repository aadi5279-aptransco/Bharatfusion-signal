"""Exact bullish/bearish momentum cash query on incomplete-session daily proxy
and fully completed 15-minute candles. Only completed 5-minute inputs.
The daily proxy is provisional; no broker order may derive from the result.
"""
from __future__ import annotations
import math
import pandas as pd
from insights.scanner_quality import recent_frame
from insights.indicators import risk_levels

def _validate(frame,minimum):
    if frame is None or not isinstance(frame,pd.DataFrame) or len(frame)<minimum:return None
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None or frame.index.has_duplicates:return None
    cols=('open','high','low','close','volume')
    if not set(cols).issubset(frame.columns):return None
    try:f=frame.sort_index()[list(cols)].astype(float)
    except (ValueError,TypeError):return None
    if not f.notna().all().all() or (f.volume<0).any():return None
    if (f[['open','high','low','close']]<=0).any().any():return None
    if (f.high<f[['open','low','close']].max(axis=1)).any():return None
    if (f.low>f[['open','high','close']].min(axis=1)).any():return None
    return f

def _rsi(closes):
    if len(closes)<16:return None
    d=closes.diff()
    gains=d.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    losses=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    a=float(gains.iloc[-1]);b=float(losses.iloc[-1])
    if not math.isfinite(a) or not math.isfinite(b):return None
    if a==0 and b==0:return 50.0
    return 100.0 if b==0 else 100-100/(1+a/b)

def daily_gate(five,prior_daily,now,side):
    """Eight exact daily conditions using current session completed 5m OHLCV.

    SMA20 includes the partial current session and 19 completed previous
    sessions, consistent with Chartink's 'latest SMA' syntax.
    """
    if side not in ('BUY','SELL'):return None
    t=pd.Timestamp(now)
    if t.tzinfo is None:return None
    f=_validate(five,2);d=_validate(prior_daily,20)
    if f is None or d is None or not recent_frame(f,t,5,20):return None
    d=d[d.index.date<t.date()]
    today=f[f.index.date==t.date()]
    if len(d)<20 or len(today)<2:return None
    first=today.index[0].tz_convert(t.tz)
    if (first.hour,first.minute)!=(9,15):return None
    if not (today.index.to_series().diff().dropna()==pd.Timedelta(minutes=5)).all():return None
    price=float(today.close.iloc[-1]);opening=float(today.open.iloc[0])
    session_volume=float(today.volume.sum())
    prev=d.iloc[-1]
    prior19=d.iloc[-19:]
    current=pd.Series([price],index=pd.DatetimeIndex([t.normalize()]))
    daily_rsi=_rsi(pd.concat([d.close,current]))
    if daily_rsi is None:return None
    vol_sma=(float(prior19.volume.sum())+session_volume)/20
    close_sma=(float(prior19.close.sum())+price)/20
    if vol_sma<=0:return None
    if side=='BUY':
        checks={
          'Close > previous-day high':price>float(prev.high),
          'Close > current-session open':price>opening,
          'Close > previous close × 1.01':price>float(prev.close)*1.01,
          'Session volume > daily SMA20 volume × 1.5':session_volume>vol_sma*1.5,
          'Close > daily SMA20 close':price>close_sma,
          'Daily RSI14 > 60':daily_rsi>60,
          'Close > ₹100':price>100,
          'Daily SMA20 volume > 500,000':vol_sma>500000,
        }
    else:
        checks={
          'Close < previous-day low':price<float(prev.low),
          'Close < current-session open':price<opening,
          'Close < previous close × 0.99':price<float(prev.close)*.99,
          'Session volume > daily SMA20 volume × 1.5':session_volume>vol_sma*1.5,
          'Close < daily SMA20 close':price<close_sma,
          'Daily RSI14 < 40':daily_rsi<40,
          'Close > ₹100':price>100,
          'Daily SMA20 volume > 500,000':vol_sma>500000,
        }
    return dict(pass_all=all(checks.values()),checks=checks,
        close=price,daily_rsi14=round(daily_rsi,2),
        daily_volume_ratio=round(session_volume/vol_sma,2),
        daily_volume_sma20=round(vol_sma,2),
        daily_close_sma20=round(close_sma,2),
        session_volume=session_volume,
        previous_day_high=float(prev.high),previous_day_low=float(prev.low),
        previous_day_close=float(prev.close),
        asof=f.index[-1].isoformat(),
        daily_status='PROVISIONAL current session from completed 5m candles')

def fifteen_gate(frame,now,side):
    """Three exact 15m EMA20, RSI14 and 2x SMA20 volume conditions."""
    if side not in ('BUY','SELL'):return None
    t=pd.Timestamp(now);f=_validate(frame,40)
    if t.tzinfo is None or f is None:return None
    if not recent_frame(f,t,15,35):return None
    if f.index[-1]+pd.Timedelta(minutes=15)>t:return None
    price=float(f.close.iloc[-1])
    ema20=float(f.close.ewm(span=20,adjust=False).mean().iloc[-1])
    rsi=_rsi(f.close)
    volume=float(f.volume.iloc[-1]);vma=float(f.volume.tail(20).mean())
    if rsi is None or vma<=0:return None
    checks=({'15m close > EMA20':price>ema20,'15m RSI14 > 60':rsi>60,
             '15m volume > SMA20 volume × 2':volume>vma*2}
        if side=='BUY' else
        {'15m close < EMA20':price<ema20,'15m RSI14 < 40':rsi<40,
         '15m volume > SMA20 volume × 2':volume>vma*2})
    return dict(pass_all=all(checks.values()),checks=checks,
        asof=f.index[-1].isoformat(),ema20=round(ema20,2),
        rsi14=round(rsi,2),volume_ratio=round(volume/vma,2))

def candidate(five,prior_daily,fifteen,symbol,now,side,flow=None):
    """Return a research scenario only after ALL 8 daily + 3 x 15m checks."""
    daily=daily_gate(five,prior_daily,now,side)
    if not daily or not daily['pass_all']:return None
    m15=fifteen_gate(fifteen,now,side)
    if not m15 or not m15['pass_all']:return None
    f=_validate(five,20)
    if f is None:return None
    recent=f.tail(15)
    tr=pd.concat([recent.high-recent.low,
        (recent.high-recent.close.shift()).abs(),
        (recent.low-recent.close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.mean())
    if not math.isfinite(atr) or atr<=0:return None
    try:levels=risk_levels(daily['close'],atr,side)
    except ValueError:return None
    return dict(strategy='Exact Daily + 15m Momentum Query',version='1.0',
        symbol=symbol,direction=side,signal_at=daily['asof'],
        asof15=m15['asof'],backtest_status='UNVALIDATED',
        research_only=True,confidence=None,rule_matches=11,
        daily_rsi14=daily['daily_rsi14'],rsi15=m15['rsi14'],
        daily_volume_ratio=daily['daily_volume_ratio'],
        volume_ratio15=m15['volume_ratio'],
        daily_volume_sma20=daily['daily_volume_sma20'],
        daily_close_sma20=daily['daily_close_sma20'],
        session_volume=daily['session_volume'],
        previous_day_high=daily['previous_day_high'],
        previous_day_low=daily['previous_day_low'],
        previous_day_close=daily['previous_day_close'],
        fifteen_ema20=m15['ema20'],latest_daily_is_partial=True,
        daily_candle_status=daily['daily_status'],
        order_flow_proxy=flow or 'NOT VERIFIED — candle volume is not aggressor trade flow',
        mtf=dict(daily='PROVISIONAL '+side,m15=side),
        rule_evidence=dict(daily=daily['checks'],m15=m15['checks']),
        reasons=list(daily['checks'])+list(m15['checks'])+
          ['Daily session candle is PROVISIONAL; underlying 5m and 15m inputs are complete'],
        **levels)
