"""Local read-only evidence collection. Default never contacts Dhan."""
import argparse,json,os,re
from pathlib import Path
from datetime import datetime,timedelta
from insights.config import IST,ROOT
from insights.brokers.dhan import DhanReadOnly
from insights.data_layer.evidence import candle_evidence,result_status

def run(live=False):
    report=dict(phase=0,checked_at=datetime.now(IST).isoformat(),mode='LIVE READ-ONLY' if live else 'OFFLINE PREFLIGHT',
                real_dhan_verified=False,checks=[],unverified=['Sandbox market-data capability and endpoint not confirmed',
                'Split/bonus/dividend adjustment status; do not train models until independently verified',
                'Special sessions, suspended/delisted coverage and expired derivative behaviour',
                'Empirical maximum request window; implementation uses <=31-day partitions',
                'Full live-market forming-candle observation and zero-volume interpretation'])
    b=DhanReadOnly();report['credentials_present']=b.configured()
    if not live:
        report['status']='NOT RUN — pass --live on your locally configured PC';return report
    if not b.configured():report['status']='BLOCKED — configure local Dhan environment; never paste tokens in chat';return report
    profile=b.check_profile();report['profile']=profile
    if profile.get('status')!='VERIFIED RESPONSE' or str(profile.get('data_plan','')).lower()!='active':
        report['status']='BLOCKED — profile/active data entitlement not verified';return report
    now=datetime.now(IST)
    def check(label,fn):
        try:
            result=fn()
            entry=dict(check=label,status=result_status(result),result=result)
            if result is None:entry['reason']='NO_RESULT_OR_MAPPING'
            report['checks'].append(entry)
            return result
        except Exception as exc:
            # Fixed categories only: arbitrary exception messages can contain secrets.
            category='DATA_REQUEST_FAILED' if isinstance(exc,RuntimeError) else 'SCHEMA_OR_EMPTY_RESULT' if isinstance(exc,(ValueError,KeyError,TypeError,IndexError,StopIteration)) else 'UNEXPECTED_CHECK_ERROR'
            report['checks'].append(dict(check=label,status='UNAVAILABLE',reason=category,error_code=getattr(exc,'code','DATA_ERROR') if re.fullmatch(r'(?:DH-)?[0-9]{3}|HTTP_[0-9]{3}|DATA_ERROR|AUTH_REJECTED|CONNECTION_UNAVAILABLE',str(getattr(exc,'code',''))) else 'DATA_ERROR'))
            return None
    mapped=[]
    try:mapped=b.instruments()
    except Exception:report['status']='BLOCKED — official master unavailable';return report
    report['master']=dict(b.master.status)
    indices=[x for x in mapped if x.get('kind')=='index'][:1]
    stocks=[x for x in mapped if x.get('kind')=='stock'][:2]
    samples=indices+stocks
    if not indices or len(stocks)<2:report['checks'].append(dict(check='Representative sample coverage',status='UNAVAILABLE',reason='MISSING_INDEX_OR_STOCK_SAMPLES'))
    for x in samples.copy():
        future=check(x['symbol']+' futures mapping',lambda i=x:i.get('future') if i.get('kind')=='stock' else b.index_future(i,now))
        if future:samples.append(dict(future,kind='future'))
    if indices:
        x=indices[0]
        try:
            expiry=next(e for e in sorted(b.expiry_list(x)) if e>=now.date().isoformat())
            chain=b.option_chain(x,expiry);spot=float(chain['last_price'])
            strike,legs=min(((float(k),v) for k,v in chain['oc'].items()),key=lambda z:abs(z[0]-spot))
            for side in ('ce','pe'):
                sid=legs.get(side,{}).get('security_id')
                if not sid:raise ValueError('Missing ATM leg')
                if sid:samples.append(dict(id=str(sid),symbol=f"{x['symbol']} ATM {side.upper()}",segment='BSE_FNO' if x['symbol'].upper()=='SENSEX' else 'NSE_FNO',instrument='OPTIDX',kind='option',expiry=expiry,strike=strike,side=side.upper()))
            report['checks'].append(dict(check='Live expiry list and option chain',status='PASS',expiry=expiry,strike_count=len(chain['oc'])))
        except Exception:report['checks'].append(dict(check='Live expiry list and option chain',status='UNAVAILABLE'))
    def candles(item,period):
        f=b.daily(item,now,days=60,oi=item.get('kind') in ('future','option')) if period==1440 else b.history(item,now,minutes=period,lookback_days=7,oi=item.get('kind') in ('future','option'))
        if f.empty:raise ValueError()
        return candle_evidence(f,period,now,item,b.data_status()['quality'],requested_start=now-timedelta(days=7) if period<1440 else None)
    for item in samples:
        for period in (1440,1,5,15,25,60):check(item['symbol']+' '+str(period)+'m',lambda i=item,p=period:candles(i,p))
    report['data_layer']=b.data_status();report['real_dhan_calls_run']=True;report['smoke_checks_passed']=bool(report['checks']) and all(x['status']=='PASS' for x in report['checks'])
    report['status']='SMOKE CHECKS PASSED — PHASE 0 EMPIRICAL ITEMS STILL OPEN' if report['smoke_checks_passed'] else 'PARTIAL — REVIEW WARNINGS AND UNAVAILABLE CHECKS'
    return report

def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=False)
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');args=p.parse_args()
    result=run(args.live);folder=ROOT/'phase0_reports';folder.mkdir(parents=True,exist_ok=True)
    path=folder/('phase0-'+datetime.now(IST).strftime('%Y%m%d-%H%M%S')+'.json')
    path.write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps(result,indent=2,default=str));print('Report:',path)
if __name__=='__main__':main()
