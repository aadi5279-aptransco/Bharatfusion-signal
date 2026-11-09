"""Previous completed-session watchlists and causal 3-minute intraday plans.
Plans are conditional research levels, never a bypass of confirmation gates.
"""
import math
import pandas as pd
from engine import clean,bars,features,IST


def previous_session(frame,now):
 f=clean(frame);now=pd.Timestamp(now).tz_convert(IST)
 f=f[(f.index<now.normalize()) & (f.index+pd.Timedelta(minutes=1)<=now)]
 if f.empty:return None
 # Do not substitute an older session if the most recent available day is incomplete.
 day=f.index[-1].normalize();s=f[f.index.normalize()==day]
 expected=pd.date_range(day+pd.Timedelta(hours=9,minutes=15),periods=375,freq='min')
 if not s.index.equals(expected):return None
 return dict(date=str(day.date()),high=float(s.high.max()),low=float(s.low.min()),close=float(s.close.iloc[-1]),open=float(s.open.iloc[0]),volume=float(s.volume.sum()))


def plan(frame,now,kind='stock'):
 now=pd.Timestamp(now).tz_convert(IST);prior=previous_session(frame,now)
 empty={'plan_status':'NO COMPLETE PREVIOUS SESSION','plan_direction':'—','plan_entry':None,'plan_stop':None,'plan_t1':None,'plan_t2':None,'plan_score':0.,'plan_asof':'','prior_date':'','intraday_eligible':False}
 if prior is None:return empty
 empty.update(prior_date=prior['date'],prior_high=prior['high'],prior_low=prior['low'])
 b=bars(frame,3,now);f=features(b)
 if len(f)<21:return {**empty,'plan_status':'3m HISTORY WARMUP'}
 x=f.iloc[-1];atr=float(x.atr)
 if not math.isfinite(atr) or atr<=0:return empty
 current=f.index[-1].date()==now.date();age=(now-(f.index[-1]+pd.Timedelta(minutes=3))).total_seconds()
 live=current and 0<=age<=180
 # Break trigger is a completed 3m close beyond yesterday's high/low.
 up=live and x.close>prior['high'];down=live and x.close<prior['low']
 direction=1 if up else -1 if down else (1 if prior['close']>=prior['open'] else -1)
 level=prior['high'] if direction==1 else prior['low']
 buffer=max(.05,atr*.05);entry=float(level+direction*buffer)
 risk=max(atr,abs(entry-level)+atr*.5)
 rv=float(x.rvol) if math.isfinite(x.rvol) else 0.
 state='BREAKOUT' if up else 'BREAKDOWN' if down else 'WATCH BREAKOUT' if direction==1 else 'WATCH BREAKDOWN'
 if current and not live:state='STALE / '+state
 # Yesterday's return and liquidity rank watch candidates; live evidence promotes breaks.
 prevreturn=abs(prior['close']/prior['open']-1)*100
 distance=abs(float(x.close)-level)/atr
 score=(100 if up or down else 0)+min(rv,5)*5+prevreturn*10-max(0,distance)*2
 active=live and (up or down) and (kind!='stock' or rv>=1.5)
 # Do not turn an already extended break into a new close-price entry.
 if active and abs(float(x.close)-entry)>2*risk:state+=' / EXTENDED';active=False
 return {**empty,'plan_status':state,'plan_direction':'LONG' if direction==1 else 'SHORT',
         'plan_entry':entry,'plan_stop':entry-direction*risk,'plan_t1':entry+direction*1.5*risk,'plan_t2':entry+direction*2.5*risk,
         'plan_score':round(score,3),'plan_asof':f.index[-1].isoformat(),'plan_rvol':rv,
         'prior_turnover':prior['volume']*prior['close'],'plan_price':float(x.close),'intraday_eligible':active}


def ranked(rows,limit=20,intraday=False,now=None):
 now=pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now)
 candidates=[]
 for r in rows:
  if r.get('kind')!='stock' or r.get('plan_entry') is None or not r.get('plan_active',r.get('active',True)):continue
  if intraday:
   if not r.get('intraday_eligible'):continue
   if r.get('mode')!='DEMO':
    try:
     age=(now-pd.Timestamp(r['plan_asof'])-pd.Timedelta(minutes=3)).total_seconds()
     if not 0<=age<=180:continue
    except Exception:continue
  candidates.append(r)
 return sorted(candidates,key=lambda r:(-r.get('plan_score',0),-r.get('prior_turnover',0),r['symbol']))[:limit]


def forecast_targets(forecast):
 """Only prices actually reached along the median sampled close path; no invented R targets."""
 if not forecast or forecast.get('error') or forecast.get('bias') not in ('UP','DOWN'):return {}
 sign=1 if forecast['bias']=='UP' else -1;last=forecast['last'];path=forecast.get('median',[])
 if not path:return {}
 n=max(1,(len(path)+1)//2)
 targets=[]
 for section in (path[:n],path):
  value=max(section) if sign==1 else min(section)
  targets.append(float(value) if sign*(value-last)>0 else None)
 return dict(kronos_t1=targets[0],kronos_t2=targets[1],target_note='K1: first-half median-path extreme; K2: full-path extreme. May be equal or unavailable; not guaranteed fills.')
