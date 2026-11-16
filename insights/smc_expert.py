"""Built-in SMC expert system. Deterministic rules, NOT a trained statistical model."""
import math
import pandas as pd
from insights.config import IST,is_market_session
from insights.indicators import clean_bars
from insights.advanced_smc import trend
from insights.scanner_quality import recent_frame
from insights.atm_recommendation import evaluate as atm_evaluate, _strike_rows

VERSION='smc-expert-v1'

def completed(frame,now,period,minimum=35):
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:raise ValueError(f'{period}m dated history missing')
    f=frame.copy();f.index=f.index.tz_convert(IST)
    f=clean_bars(f[f.index+pd.Timedelta(minutes=period)<=now])
    if len(f)<minimum or not all(math.isfinite(v) for v in f.to_numpy().flat):raise ValueError(f'{period}m history insufficient or invalid')
    if not recent_frame(f,now,period,{5:15,15:35,60:125}[period]):raise ValueError(f'{period}m candles stale')
    return f

def atr(f):
    tr=pd.concat([f.high-f.low,(f.high-f.close.shift()).abs(),(f.low-f.close.shift()).abs()],axis=1).max(axis=1)
    return float(tr.ewm(alpha=1/14,adjust=False).mean().iloc[-1])

def patterns(f):
    # Two right-hand bars must finish before a pivot exists. Exclude the
    # trigger bar when finding the latest confirmed structural reference.
    highs=[];lows=[]
    for i in range(2,len(f)-3):
        w=f.iloc[i-2:i+3]
        if f.high.iloc[i]>w.high.drop(w.index[2]).max():highs.append(i)
        if f.low.iloc[i]<w.low.drop(w.index[2]).min():lows.append(i)
    x=f.iloc[-1];previous=f.iloc[-2];a=atr(f)
    high=float(f.high.iloc[highs[-1]]) if highs else None
    low=float(f.low.iloc[lows[-1]]) if lows else None
    prior='UP' if len(highs)>1 and len(lows)>1 and f.high.iloc[highs[-1]]>f.high.iloc[highs[-2]] and f.low.iloc[lows[-1]]>f.low.iloc[lows[-2]] else 'DOWN' if len(highs)>1 and len(lows)>1 and f.high.iloc[highs[-1]]<f.high.iloc[highs[-2]] and f.low.iloc[lows[-1]]<f.low.iloc[lows[-2]] else 'MIXED'
    result={}
    for side in ('CE','PE'):
        up=side=='CE';level=high if up else low
        bos=level is not None and (previous.close<=level<x.close if up else previous.close>=level>x.close)
        sweep=low is not None and x.low<low<x.close if up else high is not None and x.high>high>x.close
        displacement=bool(a>0 and abs(x.close-x.open)>=.8*a and (x.close>x.open if up else x.close<x.open))
        gaps=[]
        for j in range(max(2,len(f)-20),len(f)-1):
            bottom,top=(float(f.high.iloc[j-2]),float(f.low.iloc[j])) if up else (float(f.high.iloc[j]),float(f.low.iloc[j-2]))
            if bottom>=top:continue
            after=f.iloc[j+1:]
            invalid=(after.close<bottom).any() if up else (after.close>top).any()
            retest=x.low<=top and x.high>=bottom and (x.close>top if up else x.close<bottom)
            if not invalid:gaps.append(dict(low=bottom,high=top,retested=bool(retest)))
        fvg=any(z['retested'] for z in gaps)
        ob=None
        if bos and displacement:
            for j in range(len(f)-2,max(-1,len(f)-8),-1):
                bar=f.iloc[j]
                if (bar.close<bar.open if up else bar.close>bar.open):
                    ob=dict(low=float(bar.low),high=float(bar.high),status='Opposite-candle proxy before displacement; retest not assumed');break
        midpoint=(high+low)/2 if high is not None and low is not None and high>low else None
        result[side]=dict(bos=bool(bos),choch=bool(bos and prior==('DOWN' if up else 'UP')),liquidity_sweep=bool(sweep),displacement=displacement,fvg_retest=bool(fvg),active_fvgs=gaps[-3:],order_block=ob,range_location=('DISCOUNT' if x.close<midpoint else 'PREMIUM') if midpoint is not None else 'UNAVAILABLE',swing_high=high,swing_low=low)
    return result

def evaluate(frames,chain,metrics,item,expiry,now,calendar,requested_side=None):
    now=pd.Timestamp(now).tz_convert(IST)
    out=dict(version=VERSION,model_type='EXPLAINABLE RULE-BASED EXPERT SYSTEM',training_status='NOT TRAINED / NOT CALIBRATED',probability_of_win=None,status='WATCH',direction=None,score=None,reasons=[],blockers=[],patterns={},mtf={},research_only=True)
    try:fs={p:completed(frames.get(p),now,p) for p in (5,15,60)}
    except (ValueError,TypeError) as exc:
        out['blockers']=[str(exc)];return out
    ps=patterns(fs[5]);out['patterns']=ps
    mtf={str(p):trend(f) for p,f in fs.items()};out['mtf']=mtf
    side='CE' if all(t=='UP' for t in mtf.values()) else 'PE' if all(t=='DOWN' for t in mtf.values()) else None
    if not side:out['blockers'].append('5m/15m/60m trends do not agree');return out
    out['direction']=side;p=ps[side]
    checks={'Aligned 5m/15m/60m trend':30,'Confirmed swing break':25 if p['bos'] else 0,'Liquidity sweep rejection':15 if p['liquidity_sweep'] else 0,'Displacement candle':15 if p['displacement'] else 0,'Active FVG retest':15 if p['fvg_retest'] else 0}
    out['score']=sum(checks.values());out['reasons']=[f'{k}: {v} points' for k,v in checks.items()]
    if not (p['bos'] or p['liquidity_sweep']):out['blockers'].append('No fresh swing break or liquidity sweep')
    if out['score']<65:out['blockers'].append('SMC confluence below 65/100')
    if requested_side and requested_side!=side:out['blockers'].append('Requested option side conflicts with model')
    if not is_market_session(now,calendar):out['blockers'].append('Outside verified market session')
    try:
        pcr=float(metrics['pcr'])
        if not math.isfinite(pcr) or pcr<=0 or (pcr<.85 if side=='CE' else pcr>1.15):raise ValueError()
    except (TypeError,KeyError,ValueError):out['blockers'].append('Option-chain PCR missing or contradicts direction')
    if item.get('kind')=='stock':
        base=float(fs[5].volume.iloc[-21:-1].mean());rv=float(fs[5].volume.iloc[-1])/base if base>0 else 0
        if rv<1.5:out['blockers'].append('Stock relative volume below 1.5')
    try:
        spot=float(chain['last_price']);cash=float(fs[5].close.iloc[-1])
        if not math.isfinite(spot) or abs(spot-cash)>max(2*atr(fs[5]),.005*cash):raise ValueError()
    except (TypeError,KeyError,ValueError):out['blockers'].append('Chain underlying price missing or too far from completed spot candles')
    if out['blockers']:return out
    scenario=atm_evaluate(chain,expiry,item['symbol'],now,calendar,bias='BULLISH' if side=='CE' else 'BEARISH')
    # Remove the old fixed-percentage levels: no fallback to invented premium history.
    scenario.update(entry=None,sl=None,t1=None,t2=None,rr=None)
    out['recommendation']=scenario
    if not scenario.get('contract') or scenario.get('ask') is None or scenario.get('spread_pct') is None or scenario['spread_pct']>2:
        out['blockers'].append('Mapped liquid ATM quote with spread <=2% required');return out
    if scenario['contract'].get('security_id') is None or scenario.get('status','').startswith('WATCH'):
        out['blockers'].append(scenario.get('reason','Contract quote unavailable'));return out
    leg=next((legs.get(side.lower(),{}) for strike,legs in _strike_rows(chain) if strike==scenario['atm_strike']),{})
    try:
        oi=float(leg.get('oi',0))
        if not math.isfinite(oi) or oi<=0:raise ValueError()
    except (TypeError,ValueError):out['blockers'].append('Positive ATM contract OI required');return out
    out['status']='AWAITING OPTION CANDLES'
    return out

def premium_levels(model,frame,now):
    result=dict(model);recommendation=dict(model['recommendation']);result['recommendation']=recommendation
    f=completed(frame,pd.Timestamp(now).tz_convert(IST),5,minimum=20)
    entry=float(recommendation['ask']);a=atr(f);close=float(f.close.iloc[-1])
    if a<=0 or abs(entry-close)>2*a:raise ValueError('Option ask too far from last completed premium candle')
    stop=min(float(f.low.tail(3).min()),entry-a);risk=entry-stop
    if not 0<stop<entry or not .03<=risk/entry<=.35:raise ValueError('Premium structural stop outside 3–35% research risk limits')
    recommendation.update(entry=round(entry,2),sl=round(stop,2),t1=round(entry+1.5*risk,2),t2=round(entry+2.5*risk,2),rr=1.5,status='HYPOTHETICAL SMC ATM SCENARIO — QUOTE AGE UNVERIFIED',reason='SMC + multi-timeframe + chain checks passed; stop uses option ATR14 and recent 3-bar low',premium_candle_asof=f.index[-1].isoformat())
    if not 0<recommendation['sl']<recommendation['entry']<recommendation['t1']<recommendation['t2']:raise ValueError('Rounded option prices collapse risk levels')
    result['status']='RESEARCH SCENARIO';result['reasons']=model['reasons']+['Premium stop derived from selected ATM option candles; targets 1.5R / 2.5R']
    return result
