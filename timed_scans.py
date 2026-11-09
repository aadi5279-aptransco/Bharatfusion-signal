"""Frozen morning research setups using only candles available at release time."""
import math
import pandas as pd
from engine import clean,bars,features,IST


def daily_weekly(frame,now):
 now=pd.Timestamp(now).tz_convert(IST);f=clean(frame)
 # 15:15 cutoff means the final included one-minute candle starts at 15:14.
 f=f[(f.index<now.normalize())&(f.index.hour*60+f.index.minute<915)]
 rows=[]
 for day,g in f.groupby(f.index.normalize()):
  # Require 95% coverage and both session boundaries; never fill missing prices.
  if len(g)<342 or g.index[0]!=day+pd.Timedelta(hours=9,minutes=15) or g.index[-1]!=day+pd.Timedelta(hours=15,minutes=14):continue
  rows.append(dict(timestamp=day,open=g.open.iloc[0],high=g.high.max(),low=g.low.min(),close=g.close.iloc[-1],volume=g.volume.sum()))
 if not rows:return None,None,'No prior session with 95% coverage through 15:15'
 d=pd.DataFrame(rows).set_index('timestamp')
 rawdays=f.index.normalize().unique()
 if d.index[-1]!=rawdays[-1]:return None,None,'Latest prior session incomplete through 15:15'
 week_start=now.normalize()-pd.Timedelta(days=now.weekday())
 finished=d[d.index<week_start]
 w=finished.resample('W-FRI').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
 counts=finished.close.resample('W-FRI').count();w=w.loc[counts>=3]
 if len(d)<21 or len(w)<6:return d,w,'Need 21 daily and 6 completed weekly candles'
 return d,w,''


def evaluate(frame,now,intraday=False):
 now=pd.Timestamp(now).tz_convert(IST);release=now.normalize()+pd.Timedelta(hours=10 if intraday else 9,minutes=15 if intraday else 45)
 out=dict(plan_status='WAIT',plan_direction='LONG',plan_entry=None,plan_stop=None,plan_t1=None,plan_t2=None,plan_score=0.,plan_asof='',prior_date='',intraday_eligible=False,timed_eligible=False,scan_release=release.isoformat(),daily_bias='WARMUP',weekly_bias='WARMUP',scan_reason='')
 d,w,error=daily_weekly(frame,now)
 if d is not None:
  prior=d.iloc[-1];out.update(prior_date=str(d.index[-1].date()),prior_high=float(prior.high),prior_low=float(prior.low),prior_turnover=float(prior.close*prior.volume))
 if not intraday and error:out['scan_reason']=error;return out
 if d is not None and len(d)>=21:
  ema9=d.close.ewm(span=9,adjust=False).mean();ema21=d.close.ewm(span=21,adjust=False).mean()
  out['daily_bias']='BULL' if d.close.iloc[-1]>ema9.iloc[-1]>ema21.iloc[-1] else 'NOT BULL'
 if w is not None and len(w)>=6:
  e3=w.close.ewm(span=3,adjust=False).mean();e6=w.close.ewm(span=6,adjust=False).mean()
  out['weekly_bias']='BULL' if w.close.iloc[-1]>e3.iloc[-1]>e6.iloc[-1] else 'NOT BULL'
 if now<release:out['scan_reason']='Waiting until '+release.strftime('%H:%M')+' IST for closed 15m candles';return out
 b=bars(frame,15,release);f=features(b);n=4 if intraday else 2
 expected=pd.date_range(now.normalize()+pd.Timedelta(hours=9,minutes=15),periods=n,freq='15min')
 today=f[f.index.normalize()==now.normalize()]
 if len(f)<30 or not today.index.equals(expected):out['scan_reason']=f'Need first {n} complete 15m candles and indicator history';return out
 x=today.iloc[-1];atr=float(x.atr);rv=float(x.rvol) if math.isfinite(x.rvol) else 0
 if not math.isfinite(atr) or atr<=0:out['scan_reason']='ATR unavailable';return out
 reasons=[]
 if intraday:
  if not x.close>today.high.iloc[:3].max():reasons.append('Fourth close has not broken first-three-candle high')
  if not x.close>x.ema9>x.ema21:reasons.append('EMA9/21 not bullish')
  if not 52<=x.rsi<=75:reasons.append('RSI9 outside 52-75')
  if x.adx<20:reasons.append('ADX14 below 20')
  if not x.close>x.vwap:reasons.append('Close below VWAP')
  if rv<1.2:reasons.append('Fourth-candle RVOL below 1.2')
 else:
  if out['daily_bias']!='BULL' or out['weekly_bias']!='BULL':reasons.append('Daily and completed-week trends not both bullish')
  if not (today.close>out['prior_high']).all():reasons.append('Both first 15m closes must exceed prior-session high')
  if not today.close.iloc[-1]>today.close.iloc[0]:reasons.append('Second confirmation close is not stronger')
  if not x.close>x.vwap:reasons.append('Close below morning VWAP')
  if rv<1.2:reasons.append('Confirmation RVOL below 1.2')
 out.update(plan_asof=today.index[-1].isoformat(),plan_rvol=rv,plan_price=float(x.close))
 if reasons:out['scan_reason']='; '.join(reasons);return out
 entry=float(x.close);stop=min(float(today.low.min()),entry-atr);risk=entry-stop
 out.update(plan_entry=entry,plan_stop=stop,plan_t1=entry+1.5*risk,plan_t2=entry+2.5*risk,
            timed_eligible=True,intraday_eligible=intraday,plan_status='FOUR-CANDLE SETUP' if intraday else 'DOUBLE CONFIRMED',
            plan_score=round(min(rv,5)*10+float(x.adx)+float((x.close/today.open.iloc[0]-1)*100)*10,3),scan_reason='Morning research setup; ML/fundamental/Kronos confirmation remains separate')
 # Freeze morning levels; subsequent candles update outcome only, never reselect the morning setup.
 later=clean(frame);later=later[(later.index>=release)&(later.index+pd.Timedelta(minutes=1)<=now)]
 for r in later.itertuples():
  if r.low<=stop:out['plan_status']='STOP TOUCHED / HISTORICAL';break
  if r.high>=out['plan_t2']:out['plan_status']='T2 TOUCHED / HISTORICAL';break
  if r.high>=out['plan_t1']:out['plan_status']='T1 TOUCHED / REVIEW'
 if now.weekday()>=5:out['plan_status']='WEEKEND / HISTORICAL'
 return out


def plans(frame,now):
 return {**evaluate(frame,now), 'intraday_plan':evaluate(frame,now,True)}


def ranked(rows,limit=20,intraday=False,now=None):
 selected=[]
 for r in rows:
  if r.get('kind')!='stock' or not r.get('plan_active',r.get('active',True)):continue
  view={**r,**r.get('intraday_plan',{})} if intraday else r
  if view.get('timed_eligible'):selected.append(view)
 return sorted(selected,key=lambda r:(-r.get('plan_score',0),-r.get('prior_turnover',0),r['symbol']))[:limit]


def status(rows,intraday=False):
 from collections import Counter
 rows=[r for r in rows if r.get('kind')=='stock']
 if rows and not any(r.get('plan_active',r.get('active',True)) for r in rows):return 'Scanner stopped or data unavailable. Restart and inspect Activity / Coverage.'
 views=[r.get('intraday_plan',{}) if intraday else r for r in rows]
 qualified=sum(bool(v.get('timed_eligible')) for v in views)
 reasons=Counter(v.get('scan_reason','Awaiting data') for v in views if not v.get('timed_eligible'))
 return f'{qualified} qualify / {len(rows)} received. '+(' | '.join(f'{n}: {reason}' for reason,n in reasons.most_common(3)) or 'No qualifying data yet' if not qualified else 'Frozen morning levels; check timestamps and current price before use.')
