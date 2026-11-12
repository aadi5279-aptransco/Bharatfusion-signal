"""Conservative directional chain OI + futures confirmation for Fib research.

Never infer OI trends from one snapshot. An option chain's previous_oi
compares to prior settlement, not necessarily prior 5m snapshot. The
result explicitly distinguishes unavailable, contradictory and corroborated
evidence. No trading sizes or fills.
"""
from __future__ import annotations
import math
import pandas as pd

def _val(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None


def chain_evidence(chain,side,spot):
    if side not in ('CE','PE') or not isinstance(chain,dict):return dict(status='UNAVAILABLE',reason='Option chain not supplied')
    oc=chain.get('oc')
    if not isinstance(oc,dict) or not oc:return dict(status='UNAVAILABLE',reason='No mapped strike OI')
    rows=[]
    for key,legs in oc.items():
        try:k=float(key)
        except (TypeError,ValueError):continue
        if not isinstance(legs,dict):continue
        ce,pe=legs.get('ce') or {},legs.get('pe') or {}
        if not isinstance(ce,dict) or not isinstance(pe,dict):continue
        # Previous OI is needed for directional 'writing/unwinding' change.
        ca=_val(ce.get('oi'));pa=_val(pe.get('oi'))
        cp=_val(ce.get('previous_oi'));pp=_val(pe.get('previous_oi'))
        if ca is None or pa is None or cp is None or pp is None:continue
        if min(ca,pa,cp,pp)<0:continue
        rows.append((k,ca,pa,ca-cp,pa-pp))
    if not rows:return dict(status='UNAVAILABLE',reason='Chain lacks verifiable current and prior OI')
    try:spot=float(spot)
    except (ValueError,TypeError):return dict(status='UNAVAILABLE',reason='Underlying spot missing')
    if spot<=0:return dict(status='UNAVAILABLE',reason='Spot invalid')
    ranked=sorted(rows,key=lambda x:abs(x[0]-spot))
    selected=ranked[:min(5,len(ranked))]
    call_delta=sum(x[3] for x in selected)
    put_delta=sum(x[4] for x in selected)
    allcall=sum(x[1] for x in rows);allput=sum(x[2] for x in rows)
    prev_call=sum(x[1]-x[3] for x in rows)
    prev_put=sum(x[2]-x[4] for x in rows)
    if allcall<=0 or prev_call<=0:
        return dict(status='UNAVAILABLE',reason='Cannot compute chain PCR')
    current_pcr=allput/allcall;prior_pcr=prev_put/prev_call
    if side=='CE':
        confirm=put_delta>0 and call_delta<0 and current_pcr>prior_pcr
        contradict=put_delta<0 and call_delta>0 and current_pcr<prior_pcr
    else:
        confirm=call_delta>0 and put_delta<0 and current_pcr<prior_pcr
        contradict=call_delta<0 and put_delta>0 and current_pcr>prior_pcr
    status='CONFIRMED' if confirm else 'CONTRADICTS' if contradict else 'MIXED'
    return dict(status=status,current_pcr=round(current_pcr,3),
        reference_pcr=round(prior_pcr,3),near_call_oi_change=call_delta,
        near_put_oi_change=put_delta,
        reason='OI change is vs chain previous_oi baseline, not verified 5-minute delta',
        note='OI positioning does not prove buyers/sellers or where institutions traded')


def futures_evidence(frame,side,now):
    if frame is None or len(frame)<2 or 'oi' not in frame:
        return dict(status='UNAVAILABLE',reason='Futures OI history missing')
    try:
        current=frame.iloc[-1];previous=frame.iloc[-2]
        current_time=pd.Timestamp(now)
        candle_time=pd.Timestamp(frame.index[-1])
        if current_time.tzinfo is None or candle_time.tzinfo is None:
            return dict(status='UNAVAILABLE',reason='Futures timestamp must be timezone-aware')
        candle_time=candle_time.tz_convert(current_time.tz)
        elapsed=(current_time-candle_time).total_seconds()/60
        if candle_time.date()!=current_time.date() or not 15<=elapsed<=40:
            return dict(status='UNAVAILABLE',reason='Futures OI candle stale or incomplete')
        oi_now=_val(current.oi);oi_before=_val(previous.oi)
        pnow=_val(current.close);pbefore=_val(previous.close)
        if not all(x is not None and x>0 for x in (oi_now,oi_before,pnow,pbefore)):
            return dict(status='UNAVAILABLE',reason='Invalid OI/price')
        up=oi_now>oi_before;pxup=pnow>pbefore;pxdown=pnow<pbefore
        confirm=up and ((side=='CE' and pxup) or (side=='PE' and pxdown))
        against=up and ((side=='CE' and pxdown) or (side=='PE' and pxup))
        return dict(status='CONFIRMED' if confirm else 'CONTRADICTS' if against else 'MIXED',
            price_change_pct=round((pnow/pbefore-1)*100,3),
            oi_change_pct=round((oi_now/oi_before-1)*100,3),
            reason='Futures 15m change; not a transaction-level order-flow delta')
    except (ValueError,TypeError,IndexError,KeyError):
        return dict(status='UNAVAILABLE',reason='Invalid futures series')


def decide(spot_setup,chain=None,futures=None):
    """Strict: no FIB+OI confirmed claim without both verified OI inputs."""
    if not isinstance(spot_setup,dict):return None
    out=dict(spot_setup)
    side=out.get('side')
    out['oi']=chain_evidence(chain,side,out.get('spot_price'))
    out['futures_oi']=futures if isinstance(futures,dict) else dict(status='UNAVAILABLE',reason='Futures OI unavailable')
    if out.get('state')!='STRUCTURE_READY':
        return dict(out,trade_status='WATCH_ONLY — SPOT SETUP INCOMPLETE')
    statuses=(out['oi']['status'],out['futures_oi']['status'])
    if 'CONTRADICTS' in statuses:
        return dict(out,trade_status='SKIP — OI CONTRADICTS PRICE')
    if statuses==('CONFIRMED','CONFIRMED'):
        return dict(out,trade_status='OI_CONFIRMED_SPOT_RESEARCH — OPTIONS UNVERIFIED')
    return dict(out,trade_status='WATCH_ONLY — OI NOT FULLY CONFIRMED')
