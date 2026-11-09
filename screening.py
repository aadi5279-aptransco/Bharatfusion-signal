"""Transparent momentum ranking and three evidence checks; not calibrated confidence."""
import math
import pandas as pd
from engine import IST


def fresh(r,now=None):
    if not r.get('active',True) or not r.get('candle'): return False
    if r.get('mode')=='DEMO':return True
    now=pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now)
    age=(now-pd.Timestamp(r['candle'])).total_seconds()-r.get('minutes',3)*60
    return 0<=age<=max(180,r.get('minutes',3)*60)


def momentum_metrics(b):
    if len(b)<21:return {}
    x=b.iloc[-1]; session=b[b.index.date==b.index[-1].date()]
    roc=float((x.close/session.close.iloc[-6]-1)*100) if len(session)>=6 else None
    day=float((x.close/session.open.iloc[0]-1)*100)
    baseline=b.volume.iloc[-21:-1].mean()
    rv=float(x.volume/baseline) if baseline>0 else None
    # Rank magnitude is a documented heuristic; not a probability.
    score=round(max(0,roc or 0)*40+max(0,day)*10+min(rv or 0,5)*5,2)
    return dict(roc5=round(roc,3) if roc is not None else None,session_change=round(day,3),rvol=round(rv,3) if rv is not None else None,
                volume=float(x.volume),turnover=float(x.volume*x.close),momentum=score)


def top_momentum(rows,limit=20,min_rvol=1.5,now=None):
    candidates=[r for r in rows if r['kind']=='stock' and fresh(r,now)
                and (r.get('rvol') or 0)>=min_rvol and (r.get('roc5') or 0)>0
                and (r.get('session_change') or 0)>0 and r.get('bias')=='BULL']
    return sorted(candidates,key=lambda r:(-r.get('momentum',0),-r.get('turnover',0),r['symbol']))[:limit]


def number(v):
    try:
        n=float(str(v).replace(',','').replace('%',''))
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None


def assess_fundamentals(payload,kind='stock',now=None):
    if kind!='stock':return dict(status='N/A',reasons=['Company fundamentals do not apply to an index'],metrics={})
    if not payload or payload.get('error'):return dict(status='UNAVAILABLE',reasons=[(payload or {}).get('error','No company snapshot received')],metrics={})
    now=pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now)
    try:
        age=(now-pd.Timestamp(payload['fetched_at'])).total_seconds()
        if age<0 or age>86400:return dict(status='STALE',reasons=['Company snapshot retrieval older than 24 hours'],metrics={})
    except (KeyError,ValueError,TypeError):return dict(status='UNAVAILABLE',reasons=['Missing valid retrieval timestamp'],metrics={})
    data=payload.get('data',{})
    if isinstance(data,list) and len(data)==1:data=data[0]
    if not isinstance(data,dict):return dict(status='UNAVAILABLE',reasons=['Unknown company-data schema'],metrics={})
    co,ratios=data.get('CO',{}),data.get('RATIOS',{})
    if not isinstance(co,dict) or not isinstance(ratios,dict):return dict(status='UNAVAILABLE',reasons=['Unknown ratio sections'],metrics={})
    metrics={k:number((co if k in ('EPS','MARKET_CAP') else ratios).get(k)) for k in ('EPS','MARKET_CAP','ROE','ROCE','PE_RATIO','PE_TO_SECTOR_PE','DEBT_TO_EQUITY')}
    financial=any(word in (str(co.get('SECTOR',''))+' '+str(co.get('INDUSTRY',''))).lower() for word in ('bank','financ','insurance','lending'))
    if not co.get('SECTOR') and not co.get('INDUSTRY'):
        return dict(status='UNAVAILABLE',reasons=['Sector classification missing; cannot choose appropriate ratio rules'],metrics=metrics)
    required=['EPS','ROE','PE_RATIO','PE_TO_SECTOR_PE']+([] if financial else ['ROCE','DEBT_TO_EQUITY'])
    missing=[k for k in required if metrics[k] is None]
    if missing:return dict(status='UNAVAILABLE',reasons=['Missing ratios: '+', '.join(missing)],metrics=metrics)
    checks=[('Positive trailing EPS',metrics['EPS']>0),('ROE >= 12%',metrics['ROE']>=12),
            ('Positive PE',metrics['PE_RATIO']>0),('PE / sector PE > 0 and <= 1.5',0<metrics['PE_TO_SECTOR_PE']<=1.5)]
    if not financial:checks += [('ROCE >= 12%',metrics['ROCE']>=12),('Debt/equity between 0 and 1.5',0<=metrics['DEBT_TO_EQUITY']<=1.5)]
    reasons=[('PASS: ' if ok else 'FAIL: ')+name for name,ok in checks]
    if financial:reasons.append('Financial sector: generic debt/equity and ROCE tests excluded; capital adequacy/NPA not provided')
    reasons.append('Retrieved '+payload['fetched_at']+'; underlying ratio publication dates are not supplied')
    return dict(status='PASS' if all(ok for _,ok in checks) else 'FAIL',reasons=reasons,metrics=metrics,source='Dhan /data/companyinfo',sector=co.get('SECTOR'),shareholding=data.get('SHP',{}))


def confirm(r,forecast=None,now=None):
    """Mutates display fields only. Preserve original rules for transparent explanations."""
    if 'technical_action' not in r:
        r['technical_action']=r['action'];r['technical_levels']={k:r.get(k) for k in ('entry','stop','t1','t2')}
    technical=r['technical_action']!='WAIT' and fresh(r,now)
    technical=technical and all(r.get('htf',{}).get(str(m))==r.get('bias') for m in (15,30,60))
    if r['kind']=='stock':technical=technical and r['technical_action']=='BUY SETUP' and (r.get('rvol') or 0)>=1.5 and (r.get('roc5') or 0)>0 and (r.get('session_change') or 0)>0
    fund=r.get('fundamentals',{}).get('status','UNAVAILABLE') if r['kind']=='stock' else 'N/A'
    ai='PENDING'
    if forecast:
        if forecast.get('error'):ai='UNAVAILABLE'
        elif forecast.get('asof')!=r['candle'] or forecast.get('mode')!=r.get('mode') or not fresh(r,now):ai='STALE'
        else:
            expected='UP' if r.get('bias')=='BULL' else 'DOWN'
            ai='PASS' if forecast.get('bias')==expected else 'DISAGREE'
    passed=int(technical)+int(fund=='PASS')+int(ai=='PASS');total=2 if r['kind']!='stock' else 3
    r.update(technical_check='PASS' if technical else 'WAIT',fundamental_check=fund,kronos_check=ai,
             confirmation=f'{passed}/{total}'+(' (index)' if total==2 else ''))
    r['forecast_change']=forecast.get('change_pct') if forecast and ai not in ('STALE','UNAVAILABLE','PENDING') else None
    r['action']=r['technical_action'] if passed==total else 'WAIT'
    if r.get('ml_required') and (not r.get('ml',{}).get('pass_gate') or not fresh(r,now)):r['action']='WAIT'
    if r.get('risk_overlay',{}).get('factor',1)==0:r['action']='WAIT'
    for k in ('entry','stop','t1','t2'):r[k]=r['technical_levels'].get(k) if r['action']!='WAIT' else None
    return r
