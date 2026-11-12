"""Fib + SMC spot setups for option research. Read-only, completed 5m candles."""
from __future__ import annotations
import math
import pandas as pd

OPEN_TIMES=[(9,15),(9,20),(9,25),(9,30),(9,35),(9,40)]
MID_TIMES=[(12,45),(12,50),(12,55),(13,0),(13,5),(13,10)]
NAME={'0945':'09:45 Fib + SMC + OI','1245':'12:45–13:15 Fib + SMC'}


def _frame(frame,now):
    t=pd.Timestamp(now)
    if t.tzinfo is None or frame is None or not isinstance(frame,pd.DataFrame):return None
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:return None
    if not {'open','high','low','close','volume'}.issubset(frame.columns):return None
    f=frame.sort_index().copy()
    if f.index.has_duplicates:return None
    f=f[(f.index.date==t.date())&(f.index+pd.Timedelta(minutes=5)<=t)]
    if f.empty:return None
    try:f[['open','high','low','close']]=f[['open','high','low','close']].astype(float)
    except (ValueError,TypeError):return None
    if f[['open','high','low','close']].isna().any().any():return None
    if (f[['open','high','low','close']]<=0).any().any():return None
    if (f.high<f[['open','low','close']].max(axis=1)).any():return None
    if (f.low>f[['open','high','close']].min(axis=1)).any():return None
    return f


def _reference(f,times):
    w=f[(f.index.hour*60+f.index.minute).isin([h*60+m for h,m in times])]
    if len(w)!=6 or [(x.hour,x.minute) for x in w.index]!=times:return None
    return dict(high=float(w.high.max()),low=float(w.low.min()),
                first_open=float(w.open.iloc[0]),last_close=float(w.close.iloc[-1]),
                end=w.index[-1]+pd.Timedelta(minutes=5))


def _held(post,level,side):
    if len(post)<2:return False
    a,b=post.iloc[-2],post.iloc[-1]
    if side=='CE':
        return bool(a.close>level and b.close>level)  # includes a break+retest candle
    return bool(a.close<level and b.close<level)


def _smc(f,side,level,reference):
    """Objective proxies. Needs structure AND a retested FVG/OB zone."""
    if len(f)<16:return dict(confirmed=False,reason='Not enough completed 5m candles')
    prev=f.iloc[:-1];last=f.iloc[-1]
    high=float(prev.high.tail(10).max());low=float(prev.low.tail(10).min())
    if side=='CE':
        sweep=bool((last.low<low and last.close>low) or
                   ((prev.low.tail(8)<prev.low.shift().rolling(7).min().tail(8)).any()))
        bos=bool(last.close>high)
        shift=bool(prev.close.iloc[-1]<prev.close.iloc[-6])
    else:
        sweep=bool((last.high>high and last.close<high) or
                   ((prev.high.tail(8)>prev.high.shift().rolling(7).max().tail(8)).any()))
        bos=bool(last.close<low)
        shift=bool(prev.close.iloc[-1]>prev.close.iloc[-6])
    choch=bool(bos and shift)
    fvg=None
    for j in range(max(2,len(f)-18),len(f)-1):
        a=f.iloc[j-2];b=f.iloc[j]
        if side=='CE' and b.low>a.high:fvg=(float(a.high),float(b.low))
        if side=='PE' and b.high<a.low:fvg=(float(b.high),float(a.low))
    fvg_retest=bool(fvg and last.low<=fvg[1] and last.high>=fvg[0])
    opp=prev[prev.close<prev.open] if side=='CE' else prev[prev.close>prev.open]
    ob=None
    if not opp.empty:
        z=opp.tail(12).iloc[-1];ob=(float(z.low),float(z.high))
    ob_retest=bool(ob and last.low<=ob[1] and last.high>=ob[0])
    pullback=bool(last.low<=level if side=='CE' else last.high>=level)
    reaction=bool(last.close>last.open and last.close>level if side=='CE'
                  else last.close<last.open and last.close<level)
    invalid=(ob[0] if ob_retest else fvg[0] if fvg_retest else None) if side=='CE' else (
             ob[1] if ob_retest else fvg[1] if fvg_retest else None)
    return dict(confirmed=bool((sweep or bos or choch) and (fvg_retest or ob_retest)
                                and pullback and reaction),
                liquidity_sweep=sweep,bos=bos,choch_proxy=choch,
                fvg_zone=list(fvg) if fvg else None,fvg_retest=fvg_retest,
                order_block_zone=list(ob) if ob else None,order_block_retest=ob_retest,
                discount_premium_retest=pullback,directional_close=reaction,
                invalidation_price=invalid,
                reason='Requires sweep/BOS/CHoCH and FVG/order-block retest, with directional close')


def evaluate(frame,now,key):
    """WAITING, NO_TRADE, WATCH, or STRUCTURE_READY; never a trade fill."""
    if key not in NAME:raise ValueError('Unknown fib strategy')
    t=pd.Timestamp(now)
    result=dict(strategy=NAME[key],key='fib_'+key,state='WAITING',research_only=True,
                asof=t.isoformat(),source='COMPLETED 5m SPOT/CASH CANDLES')
    f=_frame(frame,t)
    if f is None:return dict(result,reason='No valid completed underlying candles')
    times=OPEN_TIMES if key=='0945' else MID_TIMES
    end=(9,45) if key=='0945' else (13,15)
    if (t.hour,t.minute)<end:return dict(result,reason='Reference range still forming')
    ref=_reference(f,times)
    if ref is None:return dict(result,reason='Missing exact 5m bars for reference period')
    h,l=ref['high'],ref['low']
    if not h>l:return dict(result,state='NO_TRADE',reason='Invalid reference range')
    fib={str(r):round(l+(h-l)*r,4) for r in (0,.44,.5,1)}
    result.update(fib=fib,reference=dict(high=h,low=l,
        color='GREEN' if ref['last_close']>=ref['first_open'] else 'RED',
        interval='09:15–09:45' if key=='0945' else '12:45–13:15'))
    post=f[f.index>=ref['end']]
    if len(post)<2:return dict(result,reason='Waiting for two completed 5m closes after reference')
    if (t-post.index[-1]).total_seconds()>1200:
        return dict(result,reason='Confirmation candles stale')
    color=result['reference']['color']
    if key=='0945':
        bull,bear=fib['0.5'],fib['0.44'];zone='0.44–0.50'
    elif color=='GREEN':
        bull,bear=fib['0.5'],fib['0'];zone='0–0.50'
    else:
        bull,bear=fib['1'],fib['0.44'];zone='0.44–1'
    buy=_held(post,bull,'CE');sell=_held(post,bear,'PE')
    result['no_trade_zone']=zone
    if buy==sell:
        return dict(result,state='NO_TRADE',reason='No unambiguous two-close sustain outside no-trade zone')
    side='CE' if buy else 'PE';level=bull if buy else bear
    smc=_smc(f,side,level,ref)
    result.update(side=side,trigger_level=level,spot_price=round(float(post.close.iloc[-1]),2),
                  smc=smc,signal_at=post.index[-1].isoformat())
    if not smc['confirmed']:
        return dict(result,state='WATCH',reason='Fib directional hold; wait for confirmed SMC retest/structure')
    entry=float(post.close.iloc[-1]);stop=smc['invalidation_price']
    if stop is None:return dict(result,state='WATCH',reason='No structural invalidation')
    sign=1 if side=='CE' else -1
    risk=sign*(entry-stop)
    if risk<=0 or risk/entry>.03:return dict(result,state='WATCH',reason='Invalid or >3% spot stop distance')
    first=h if buy else l
    if key=='1245':first=max(h,float(f.high.max())) if buy else min(l,float(f.low.min()))
    if sign*(first-entry)<=0:first=entry+sign*1.5*risk
    return dict(result,state='STRUCTURE_READY',
       spot_entry=round(entry,2),spot_sl=round(stop,2),spot_t1=round(first,2),
       spot_t2=round(entry+sign*2*risk,2),spot_risk_pct=round(100*risk/entry,2),
       reason='Confirmed Fib hold, SMC structure, retest and directional 5m close; OI still required')
