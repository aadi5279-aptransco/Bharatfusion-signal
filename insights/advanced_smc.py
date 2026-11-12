"""Deterministic SMC-style pattern evidence and multi-timeframe assessment.

Only completed licensed OHLCV candles; no institutional identities or true
aggressor order flow can be inferred from bars.
"""
from __future__ import annotations
import math
import pandas as pd
from insights.indicators import risk_levels,add_features


def trend(frame, min_bars=25):
    if frame is None or len(frame)<min_bars:return 'UNAVAILABLE'
    f=frame.sort_index()
    close=f.close.astype(float)
    if close.isna().any() or (close<=0).any():return 'UNAVAILABLE'
    e9=close.ewm(span=9,adjust=False).mean()
    e21=close.ewm(span=21,adjust=False).mean()
    if close.iloc[-1]>e9.iloc[-1]>e21.iloc[-1] and e21.iloc[-1]>e21.iloc[-5]:return 'UP'
    if close.iloc[-1]<e9.iloc[-1]<e21.iloc[-1] and e21.iloc[-1]<e21.iloc[-5]:return 'DOWN'
    return 'MIXED'


def _safe_float(value):
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None


def structure(frame, now=None):
    """Closed-candle BOS/CHOCH proxies, FVG, liquidity sweep and OR breakout."""
    if frame is None or len(frame)<35:return dict(available=False)
    f=frame.sort_index()
    if now is not None:
        t=pd.Timestamp(now)
        if t.tzinfo is None:return dict(available=False)
        f=f[f.index+pd.Timedelta(minutes=5)<=t]
    if len(f)<35:return dict(available=False)
    today=f[f.index.date==f.index[-1].date()]
    if len(today)<4:return dict(available=False)
    first_three=today.index[:3]
    # Never call an arbitrary first-15-minute range an opening range.
    if [(t.hour,t.minute) for t in first_three]!=[(9,15),(9,20),(9,25)]:
        return dict(available=False)
    last=f.iloc[-1]
    c=float(last.close)
    high20=float(f.high.iloc[-21:-1].max())
    low20=float(f.low.iloc[-21:-1].min())
    openhigh=float(today.high.iloc[:3].max())
    openlow=float(today.low.iloc[:3].min())
    baseline=float(f.volume.iloc[-21:-1].mean())
    rvol=float(last.volume)/baseline if baseline>0 else 0.0
    e9=float(f.close.ewm(span=9,adjust=False).mean().iloc[-1])
    e21=float(f.close.ewm(span=21,adjust=False).mean().iloc[-1])
    # BOS approximated by 20-bar closed-break; direction change is CHoCH proxy.
    prior20=float(f.close.iloc[-21:-1].mean())
    prevbias='UP' if float(f.close.iloc[-2])>prior20 else 'DOWN'
    up_break=c>max(openhigh,high20)
    down_break=c<min(openlow,low20)
    # 3-candle price imbalance (not proof that an institutional FVG will fill).
    fvg_up=bool(float(f.low.iloc[-1])>float(f.high.iloc[-3]))
    fvg_down=bool(float(f.high.iloc[-1])<float(f.low.iloc[-3]))
    # Sweep: wick through previous range then close back inside.
    sweep_high=bool(float(last.high)>high20 and c<high20)
    sweep_low=bool(float(last.low)<low20 and c>low20)
    return dict(available=True,close=c,high20=high20,low20=low20,
        opening_high=openhigh,opening_low=openlow,rvol=round(rvol,2),
        ema9=e9,ema21=e21,up_breakout=up_break,down_breakdown=down_break,
        bos_up=bool(c>high20),bos_down=bool(c<low20),
        choch_up=bool(c>high20 and prevbias=='DOWN'),
        choch_down=bool(c<low20 and prevbias=='UP'),
        fvg_up=fvg_up,fvg_down=fvg_down,
        liquidity_sweep_high=sweep_high,liquidity_sweep_low=sweep_low,
        data_asof=f.index[-1].isoformat())


def rank_early(frame, now):
    """Relative setup rankings at 09:45/10:00, NOT actionable signals."""
    m=structure(frame,now)
    if not m.get('available'):return None
    up=int(m['close']>m['opening_high'])*25+int(m['close']>m['ema21'])*15
    down=int(m['close']<m['opening_low'])*25+int(m['close']<m['ema21'])*15
    up+=min(35,max(0,(m['rvol']-1)*20))
    down+=min(35,max(0,(m['rvol']-1)*20))
    up+=int(m['bos_up'])*15+int(m['fvg_up'])*10
    down+=int(m['bos_down'])*15+int(m['fvg_down'])*10
    # Early watchlist direction uses *session return* even without a
    # confirmed breakout. Signal generation remains strict (>=2x volume,
    # structural break, 15m/60m trend and indicator agreement).
    day=frame[frame.index.date==pd.Timestamp(now).date()]
    if day.empty or float(day.open.iloc[0])<=0:return None
    session_pct=100*(m['close']/float(day.open.iloc[0])-1)
    return dict(up_score=round(up,1),down_score=round(down,1),
        rvol=m['rvol'],close=m['close'],session_change_pct=round(session_pct,3),
        up_breakout=m['up_breakout'],
        down_breakdown=m['down_breakdown'],data_asof=m['data_asof'])


def _session_return(frame):
    f=frame[frame.index.date==frame.index[-1].date()]
    return (float(f.close.iloc[-1])/float(f.open.iloc[0])-1)*100 if not f.empty and f.open.iloc[0]>0 else None


def signal(frame5,frame15,frame60,side,symbol,now,index_return,sector_return,
           depth=None):
    """Strict directional research candidate; both sides require huge volume."""
    if side not in ('BUY','SELL'):return None
    m=structure(frame5,now)
    if not m.get('available') or m['rvol']<2.0:return None
    t15=trend(frame15)
    t60=trend(frame60)
    expected='UP' if side=='BUY' else 'DOWN'
    if t15!=expected or t60!=expected:return None
    breakout=m['up_breakout'] if side=='BUY' else m['down_breakdown']
    if not breakout:return None
    close=m['close']
    if side=='BUY' and not(close>m['ema9']>m['ema21']):return None
    if side=='SELL' and not(close<m['ema9']<m['ema21']):return None
    own=_session_return(frame5)
    if own is None or index_return is None or sector_return is None:return None
    if side=='BUY' and not(own>index_return and own>sector_return):return None
    if side=='SELL' and not(own<index_return and own<sector_return):return None
    try:
        features=add_features(frame5)
    except ValueError:
        return None
    last=features.iloc[-1]
    close_series=features.close
    delta=close_series.diff()
    gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rs=float(gain.iloc[-1])/float(loss.iloc[-1]) if float(loss.iloc[-1])>0 else float('inf')
    rsi=100-100/(1+rs)
    fast=close_series.ewm(span=12,adjust=False).mean()
    slow=close_series.ewm(span=26,adjust=False).mean()
    macd_line=fast-slow
    macd_hist=macd_line-macd_line.ewm(span=9,adjust=False).mean()
    macd=float(macd_hist.iloc[-1])
    adx=float(last.adx)
    vwap=float(last.vwap)
    alignment=float(last.ema20)-float(last.ema50)
    confirmations={
        'ADX >=20':math.isfinite(adx) and adx>=20,
        'VWAP aligned':math.isfinite(vwap) and ((close>vwap) if side=='BUY' else (close<vwap)),
        'RSI aligned':math.isfinite(rsi) and ((rsi>=52) if side=='BUY' else (rsi<=48)),
        'MACD histogram aligned':math.isfinite(macd) and ((macd>0) if side=='BUY' else (macd<0)),
        'EMA20/EMA50 aligned':((alignment>0) if side=='BUY' else (alignment<0))
    }
    if sum(confirmations.values())<3:return None
    # Order-book quantity is a resting-depth proxy, NOT trade direction/delta.
    flow='UNAVAILABLE — NOT VERIFIED'
    ratio=None
    if depth and depth.get('verified'):
        ratio=_safe_float(depth.get('bid_ask_ratio'))
        if ratio is not None:
            flow='RESTING DEPTH BUY LEAN' if ratio>=1.2 else 'RESTING DEPTH SELL LEAN' if ratio<=.83 else 'NEUTRAL RESTING DEPTH'
            # A contradictory depth snapshot blocks a high-conviction call.
            if side=='BUY' and ratio<.83:return None
            if side=='SELL' and ratio>1.2:return None
    recent=frame5.tail(14)
    tr=pd.concat([(recent.high-recent.low),
        (recent.high-recent.close.shift()).abs(),
        (recent.low-recent.close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.mean())
    if not math.isfinite(atr) or atr<=0:return None
    stop=(min(float(frame5.low.tail(3).min()),close-atr) if side=='BUY'
          else max(float(frame5.high.tail(3).max()),close+atr))
    try:levels=risk_levels(close,atr,side,stop=stop)
    except ValueError:return None
    confirmations_list=[f'5m {side} 20-bar/opening-range structure break',
       f'5m volume {m["rvol"]:.2f}x trailing baseline (minimum 2.0x)',
       '15m EMA9/21 trend aligned',
       '60m EMA9/21 trend aligned',
       'Price relative to NIFTY and mapped sector confirmed',
       f'5m confirmations {sum(confirmations.values())}/5: '+', '.join(k for k,v in confirmations.items() if v),
       'Order flow proxy: '+flow]
    if m['choch_up' if side=='BUY' else 'choch_down']:confirmations_list.append('Possible CHoCH proxy (range-based)')
    if m['fvg_up' if side=='BUY' else 'fvg_down']:confirmations_list.append('Three-candle FVG proxy')
    if m['liquidity_sweep_low' if side=='BUY' else 'liquidity_sweep_high']:confirmations_list.append('Liquidity sweep proxy')
    confidence=min(90,60+min(10,round((m['rvol']-2)*4))+5*sum(confirmations.values())+
                   (5 if ratio is not None and ((side=='BUY' and ratio>=1.2) or (side=='SELL' and ratio<=.83)) else 0))
    return dict(strategy='MTF SMC Volume Breakout/Breakdown',version='2.0',
        symbol=symbol,direction=side,signal_at=m['data_asof'],confidence=confidence,
        rvol=m['rvol'],structure=m,mtf=dict(m5=side,m15=t15,m60=t60),
        order_flow_proxy=flow,order_flow_ratio=ratio,
        backtest_status='UNVALIDATED',research_only=True,
        confirmations=confirmations,adx=round(adx,2),rsi14=round(rsi,2),macd_histogram=round(macd,3),reasons=confirmations_list,**levels)


def btst_confirm(frame15,frame60,daily,now):
    """Prior completed daily trend + current 15/60 trend, weekly if complete.
    Reject if weekly directional confirmation cannot be measured.
    """
    if trend(frame15)!='UP' or trend(frame60)!='UP':return False
    if daily is None or len(daily)<80:return False
    d=daily.sort_index()
    if trend(d,min_bars=40)!='UP':return False
    weekly=d.resample('W-FRI').agg({'open':'first','high':'max',
        'low':'min','close':'last','volume':'sum'}).dropna()
    # Do not use the current incomplete trading week as a weekly candle.
    weekly=weekly[weekly.index.date<pd.Timestamp(now).date()]
    return trend(weekly,min_bars=12)=='UP'
