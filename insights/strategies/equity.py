"""Independent, deterministic candidate rules. No LLM price levels."""
from __future__ import annotations
import math
import pandas as pd
from insights.indicators import add_features,risk_levels

INTRADAY_NAME='Opening range VWAP'
INTRADAY_VERSION='1.0'
BTST_NAME='Close-high breakout'
BTST_VERSION='1.0'


def intraday(frame,symbol,now,index_return=None,sector_return=None):
    """Run only after 10:00 on *completed* five-minute Dhan candles."""
    now=pd.Timestamp(now)
    if now.tzinfo is None:raise ValueError('Timezone-aware asof required')
    if (now.hour,now.minute)<(10,0):return None
    f=add_features(frame)
    today=f[f.index.date==now.date()]
    if len(today)<9:return None
    first=today.iloc[:3];last=today.iloc[-1]
    o=float(first.open.iloc[0]);close=float(last.close)
    if index_return is None or sector_return is None:return None
    own=(close/o-1)*100
    conditions=[
        ('Closed candle broke first-15-minute range',close>first.high.max()),
        ('Price above session VWAP',math.isfinite(last.vwap) and close>last.vwap),
        ('Five-minute relative volume at least 1.5',math.isfinite(last.rvol) and last.rvol>=1.5),
        ('Price above EMA20 and EMA50',close>last.ema20>last.ema50),
        ('Outperforming NIFTY since session open',own>index_return),
        ('Outperforming own sector since session open',own>sector_return),
        ('ADX at least 20',math.isfinite(last.adx) and last.adx>=20),
    ]
    if not all(ok for _,ok in conditions):return None
    sl=min(float(today.low.tail(3).min()),close-float(last.atr))
    try:levels=risk_levels(close,last.atr,'BUY',stop=sl)
    except ValueError:return None
    return dict(strategy=INTRADAY_NAME,version=INTRADAY_VERSION,symbol=symbol,direction='BUY',
      signal_at=str(f.index[-1]),confidence=min(95,round(75+min(9,max(0,float(last.rvol)-1.5)*4)+min(7,max(0,float(last.adx)-20)*.4)+min(4,max(0,own-index_return)))),
      reasons=[label for label,ok in conditions if ok],**levels)


def btst(daily,intraday_frame,symbol,now,delivery_pct=None,sector_return=None):
    """Requires a dated licensed delivery metric; never invent delivery percentages."""
    now=pd.Timestamp(now)
    if now.tzinfo is None:raise ValueError('Timezone-aware asof required')
    if (now.hour,now.minute)<(15,0) or delivery_pct is None or sector_return is None:return None
    d=daily.sort_index()
    if len(d)<30:return None
    today=intraday_frame[intraday_frame.index.date==now.date()]
    if today.empty:return None
    current_close=float(today.close.iloc[-1]);current_high=float(today.high.max());v=float(today.volume.sum())
    yesterday=d.iloc[-1]; prev_high=float(d.high.tail(20).max())
    # 15:00 running volume is compared with 15:00 historical volume only if supplied;
    # full-day historical volumes are NOT a valid comparison at 15:00.
    if 'volume_1500' not in d.columns:return None
    baseline=float(d.volume_1500.tail(20).mean())
    if baseline<=0:return None
    current_open=float(today.open.iloc[0]);ret=(current_close/current_open-1)*100
    ok=[
        ('Within 0.5% of session high',current_close>=.995*current_high),
        ('Breakout above prior 20-session high',current_close>prev_high),
        ('Volume at 15:00 at least 1.5x matched-time average',v>=1.5*baseline),
        ('Licensed delivery percentage at least 40%',float(delivery_pct)>=40),
        ('Outperforming own sector',ret>sector_return),
    ]
    if not all(v for _,v in ok):return None
    # Levels use underlying cash price and true range from previous completed daily bars.
    tr=pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.tail(14).mean());stop=min(float(today.low.tail(3).min()),current_close-atr)
    try:levels=risk_levels(current_close,atr,'BUY',stop=stop)
    except ValueError:return None
    return dict(strategy=BTST_NAME,version=BTST_VERSION,symbol=symbol,direction='BUY',
      signal_at=str(today.index[-1]),confidence=100,reasons=[label for label,val in ok if val],**levels)
