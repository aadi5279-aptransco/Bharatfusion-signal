"""User-defined traps and evening strategies. Causal closed-candle research only."""
import math
import numpy as np
import pandas as pd
from engine import bars,clean,features,IST


def rsi14(close):
 d=close.diff();up=d.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean();down=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
 return (100-100/(1+up/down.replace(0,np.nan))).where(down>0,100).where((up+down)>0,50)


def empty(name,reason,side=''):
 return dict(strategy=name,matched=False,eligible=False,strategy_status='WAIT',reason=reason,option_side=side,underlying_entry=None,underlying_sl=None,underlying_t1=None,underlying_t2=None)


def pivots(day):
 p=float((day.high+day.low+day.close)/3);return dict(P=p,R1=2*p-day.low,R2=p+day.high-day.low,S1=2*p-day.high,S2=p-day.high+day.low)


def trap(frame,now,strict=False,tick=.05):
 """Actual single futures contract bars. Written rules default; strict scanner optional.
 All breaks require a 15m CLOSE; delayed VWAP qualification allowed in written mode.
 """
 now=pd.Timestamp(now).tz_convert(IST);name='Trap scan'
 if frame is None:return empty(name,'Futures contract/history unavailable; no equity-candle substitution')
 f=clean(frame);f=f[f.index+pd.Timedelta(minutes=1)<=now];b=bars(f,15,now)
 t=b[b.index.normalize()==now.normalize()]
 if len(t)<2:return empty(name,'Need first two complete 15m futures candles')
 expected=pd.date_range(now.normalize()+pd.Timedelta(hours=9,minutes=15),periods=len(t),freq='15min')
 if not t.index.equals(expected):return empty(name,'Missing opening/session 15m candles')
 first=t.iloc[0];sign=1 if first.close<first.open else -1 if first.close>first.open else 0
 if not sign:return empty(name,'First candle is doji')
 name='Bear trap CE' if sign==1 else 'Bull trap PE';side='CE' if sign==1 else 'PE'
 if sign*(t.iloc[1].close-t.iloc[1].open)<=0:return empty(name,'Second candle must be green for CE / red for PE',side)
 prior=f[f.index.normalize()<now.normalize()]
 if prior.empty:return empty(name,'Previous futures session unavailable',side)
 prior=prior[prior.index.normalize()==prior.index[-1].normalize()]
 if len(prior)<356 or prior.index[0].strftime('%H:%M')!='09:15' or prior.index[-1].strftime('%H:%M')!='15:29':return empty(name,'Previous futures session incomplete for pivots',side)
 prev=pd.Series({'high':prior.high.max(),'low':prior.low.min(),'close':prior.close.iloc[-1]});pv=pivots(prev)
 strict_open=abs(first.open-(first.high if sign==1 else first.low))<=tick*.5
 strict_gap=first.open<prev.low if sign==1 else first.open>prev.high
 if strict and not (strict_open and strict_gap):return empty(name,'Strict scanner opening wick/gap condition failed',side)
 vwap=((t.high+t.low+t.close)/3*t.volume).cumsum()/t.volume.cumsum().replace(0,np.nan)
 anchor=None;trigger=None
 for i in range(1,len(t)):
  x=t.iloc[i]
  if (sign==1 and x.close<first.low) or (sign==-1 and x.close>first.high):return empty(name,'Invalidated: candle closed beyond first-candle extreme',side)
  if anchor is not None:
   a=t.iloc[anchor];level=float(a.high if sign==1 else a.low)
   if sign*(x.close-level)>0:
    if strict and (anchor!=1 or i!=2):return empty(name,'Strict scanner requires third-candle confirmation',side)
    trigger=i;break
  if anchor is None and sign*(x.close-x.open)>0 and math.isfinite(vwap.iloc[i]) and sign*(x.close-vwap.iloc[i])>0:
   anchor=i
  if strict and i==1 and anchor is None:return empty(name,'Strict scanner second candle failed colour/VWAP conditions',side)
 if trigger is None:return empty(name,'Waiting for qualifying VWAP candle and later close beyond its extreme',side)
 x=t.iloc[trigger];previous=t.iloc[trigger-1];entry=float(x.close);sl=float(previous.low if sign==1 else previous.high);risk=sign*(entry-sl)
 if risk<=tick:return empty(name,'Invalid/too-small structural risk',side)
 # Valid nearby structure at >=1R, otherwise explicit R-multiple fallback.
 levels=[float(first.high if sign==1 else first.low)]+list(pv.values())
 favourable=sorted({v for v in levels if sign*(v-entry)>=risk},reverse=sign<0)
 t1=favourable[0] if favourable else entry+sign*risk
 t2=next((v for v in favourable if sign*(v-t1)>tick),entry+sign*max(2*risk,sign*(t1-entry)+risk))
 stamp=t.index[trigger]+pd.Timedelta(minutes=15);later=t.iloc[trigger+1:]
 status='PATTERN MATCH';reason='Closing-basis 15m trigger; futures levels; option premium estimates separate'
 stopped=any(sign*(c-sl)<0 for c in later.close) or any((c<first.low if sign==1 else c>first.high) for c in later.close)
 targets=any(sign*(c-t1)>=0 for c in later.close)
 age=(now-stamp).total_seconds()
 eligible=0<=age<=600 and not stopped and not targets and now.weekday()<5 and now.hour*60+now.minute<915
 if stopped:status='SL CLOSE / HISTORICAL'
 elif targets:status='TARGET CLOSE / HISTORICAL'
 elif not eligible:status='HISTORICAL / NOT A FRESH ENTRY'
 return dict(strategy=name,matched=True,eligible=eligible,strategy_status=status,reason=reason,option_side=side,
             underlying_entry=entry,underlying_sl=sl,underlying_t1=float(t1),underlying_t2=float(t2),trigger_at=stamp.isoformat(),
             underlying_now=float(t.close.iloc[-1]),stop_basis='15m futures close; ₹2,000 premium loss alert separately',
             strict_scanner_pass=bool(strict_open and strict_gap and anchor==1 and trigger==2),pivot_levels=pv,
             valid_until=min(stamp+pd.Timedelta(minutes=10),now.normalize()+pd.Timedelta(hours=15,minutes=15)).isoformat(),futures_asof=(t.index[-1]+pd.Timedelta(minutes=15)).isoformat())


def daily_context(daily,frame,cutoff):
 if daily is None or len(daily)<15:raise ValueError('Daily history unavailable')
 cutoff=pd.Timestamp(cutoff).tz_convert(IST);d=daily.copy().sort_index();d=d[d.index.normalize()<cutoff.normalize()]
 f=clean(frame);today=f[(f.index.normalize()==cutoff.normalize())&(f.index+pd.Timedelta(minutes=1)<=cutoff)]
 expected=int((cutoff-(cutoff.normalize()+pd.Timedelta(hours=9,minutes=15))).total_seconds()/60)
 if expected<1 or len(today)!=expected:raise ValueError('Missing one-minute candles for intraday daily snapshot')
 if today.index[0].strftime('%H:%M')!='09:15':raise ValueError('Opening candle missing')
 x=pd.DataFrame([dict(open=today.open.iloc[0],high=today.high.max(),low=today.low.min(),close=today.close.iloc[-1],volume=today.volume.sum())],index=pd.DatetimeIndex([cutoff.normalize()]))
 return d,pd.concat([d,x]),today


def evening(daily,frame,now):
 now=pd.Timestamp(now).tz_convert(IST);minute=now.hour*60+now.minute
 results=[]
 for name,release in (('125D breakout',915),('BTST consolidation',905)):
  out=empty(name,'Wait until '+('15:15' if release==915 else '15:05')+' IST', '' if release==915 else 'CE')
  if minute<release:results.append(out);continue
  cutoff=now.normalize()+pd.Timedelta(minutes=release)
  try:d,full,today=daily_context(daily,frame,cutoff)
  except ValueError as e:out['reason']=str(e);results.append(out);continue
  x=full.iloc[-1];rsi=float(rsi14(full.close).iloc[-1]);checks=[]
  if name=='125D breakout':
   if len(d)<125:out['reason']='Need 125 completed daily candles (daily endpoint backfill)';results.append(out);continue
   level=float(d.high.tail(125).max());baseline=float(d.volume.tail(125).mean())
   if not x.close>level:checks.append('Close not above prior 125-day high')
   if not x.volume>2*baseline:checks.append('Volume not greater than 2x prior 125-day average')
   if not rsi<70:checks.append('RSI14 not below 70')
   entry=float(x.close);sl=float(min(d.low.iloc[-1],level));t1=entry+(entry-sl);t2=entry+2*(entry-sl)
   exit_rule='Entry session counts as day 1; exit alert after 15:25 on trading session 5. T1/T2 informational.'
   eligible_window=915<=minute<925
  else:
   if len(d)<15:checks.append('Insufficient daily data')
   level=float(d.high.iloc[-1]);zone=d.tail(2)
   # Explicit configurable operational definition: two-day range <=3% and overlapping ranges.
   two=zone.high.max()/zone.low.min()-1<=.03 and zone.low.max()<=zone.high.min()
   one=d.high.iloc[-1]/d.low.iloc[-1]-1<=.02
   if not two and one:zone=d.tail(1)
   elif not two:checks.append('No 1-day <=2% or overlapping 2-day <=3% consolidation')
   if not x.close>max(level,float(zone.high.max())):checks.append('15:05 snapshot not above previous-day/consolidation high')
   sma10=float(full.volume.tail(10).mean())
   if not x.volume>=2*sma10:checks.append('Volume below 2x daily SMA10 (includes current snapshot)')
   if not 55<rsi<65:checks.append('RSI14 not between 55 and 65')
   cutoff5=min(now,now.normalize()+pd.Timedelta(hours=15,minutes=20));b=bars(frame,5,cutoff5)
   candidates=b[(b.index>=now.normalize()+pd.Timedelta(hours=15,minutes=5))&(b.index.normalize()==now.normalize())]
   # 15:05-15:10, 15:10-15:15, 15:15-15:20 closes must sustain PDH.
   hits=candidates[(candidates.close>level)&(candidates.close>zone.high.max())]
   if hits.empty:checks.append('Waiting for a completed 5m close above PDH between 15:10 and 15:20');entry=float(x.close);trigger=cutoff
   else:
    entry=float(hits.close.iloc[0]);trigger=hits.index[0]+pd.Timedelta(minutes=5)
    fx=features(b.loc[:hits.index[0]]).iloc[-1]
    if not (fx.close>fx.ema9>fx.ema21 and fx.adx>=20):checks.append('5m breakout trend weak/sideways (EMA9/21 + ADX20)')
   sl=float(zone.low.min());t1=entry*1.015;t2=entry*1.03
   exit_rule='Next trading session: T1 +1.5%, T2 +3% underlying; time-exit alert by 11:15 IST'
   eligible_window=910<=minute<=920
  if checks:out['reason']='; '.join(checks);out['rsi14']=rsi;results.append(out);continue
  if entry<=sl or sl<=0:out['reason']='Invalid structural stop';results.append(out);continue
  stamp=cutoff if name=='125D breakout' else trigger
  # Only the partial daily candle known at the stated scan time is used for selection.
  out.update(matched=True,eligible=bool(eligible_window and now.weekday()<5),strategy_status='PATTERN MATCH' if eligible_window else 'OUTSIDE ENTRY WINDOW / HISTORICAL',reason='Partial daily snapshot; delivery/ban/events checked separately',
    underlying_entry=entry,underlying_sl=sl,underlying_t1=t1,underlying_t2=t2,trigger_at=stamp.isoformat(),rsi14=rsi,exit_rule=exit_rule,
    stop_basis='5m close below consolidation low' if name!='125D breakout' else 'Daily close below prior-day low; default risk stop takes priority',
    valid_until=(now.normalize()+pd.Timedelta(minutes=925 if name=='125D breakout' else 921)).isoformat(),breakout_level=level,volume_snapshot=float(x.volume),previous_day=str(d.index[-1].date()),underlying_now=float(today.close.iloc[-1]))
  results.append(out)
 return results
