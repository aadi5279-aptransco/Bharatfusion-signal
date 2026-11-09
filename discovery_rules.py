"""Explicit cash-equity setups; no claim of institutional orders or trading accuracy."""
import numpy as np
import pandas as pd
from engine import IST,bars,features,clean
from strategy_rules import empty

def rsi14(close):
 """Wilder RSI14 with arithmetic-mean seed, no pre-warmup values."""
 delta=close.astype(float).diff();gain=delta.clip(lower=0);loss=-delta.clip(upper=0)
 out=pd.Series(np.nan,index=close.index,dtype=float)
 if len(close)<15:return out
 up=float(gain.iloc[1:15].mean());down=float(loss.iloc[1:15].mean())
 for i in range(14,len(close)):
  if i>14:up=(up*13+float(gain.iloc[i]))/14;down=(down*13+float(loss.iloc[i]))/14
  out.iloc[i]=50. if up+down==0 else 100. if down==0 else 100-100/(1+up/down)
 return out

def completed_periods(d,now):
 d=d[d.index.normalize()<now.normalize()].sort_index()
 agg={'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
 # Exclude the first potentially incomplete source month/week and current periods.
 m=d.resample('MS').agg(agg).dropna();w=d.resample('W-MON',label='left',closed='left').agg(agg).dropna()
 m=m[(m.index> d.index[0].replace(day=1))&(m.index<now.normalize().replace(day=1))]
 monday=now.normalize()-pd.Timedelta(days=now.weekday());w=w[(w.index>d.index[0])&(w.index<monday)]
 return m,w

def levels(name,entry,low,atr,now,reason,history):
 out=empty(name,reason)
 sl=float(low)-max(.05,.1*float(atr));risk=entry-sl
 if not np.isfinite([entry,sl,risk]).all() or sl<=0 or not 0<risk/entry<=.04:
  out.update(matched=True,reason='Structural stop exceeds 4% or is invalid; no artificially tighter SL');return out
 resistance=sorted(set(float(x) for x in history.high if float(x)>=entry+1.5*risk))
 t1=resistance[0] if resistance else entry+1.5*risk
 t2=next((x for x in resistance if x>=max(entry+2.5*risk,t1+.5*risk)),max(entry+2.5*risk,t1+.5*risk))
 out.update(matched=True,eligible=True,strategy_status='READY / RESEARCH',underlying_entry=float(entry),underlying_sl=sl,underlying_t1=t1,underlying_t2=t2,underlying_now=float(entry),trigger_at=now.isoformat(),valid_until=(now+pd.Timedelta(minutes=5)).isoformat(),stop_basis='Closing basis below setup low plus 0.1 ATR buffer',reason=reason)
 return out

def institutional(d,f,now,member=False,source_status='ScanX unavailable'):
 name='Institutional RSI pullback';now=pd.Timestamp(now).tz_convert(IST);out=empty(name,source_status)
 if not member:out['reason']=source_status+'; not in the current verified ScanX list';return out
 if d is None or len(d)<400:return empty(name,'Monthly RSI warmup: need sufficient multi-year daily history')
 d=d[d.index<now.normalize()];m,w=completed_periods(d,now)
 if len(m)<30 or len(w)<30:return empty(name,'Need at least 30 completed monthly and weekly candles')
 mr=float(rsi14(m.close).iloc[-1]);wr=float(rsi14(w.close).iloc[-1]);out.update(monthly_rsi=mr,weekly_rsi=wr)
 if not mr>60 or not wr>60:out['reason']=f'Completed monthly RSI {mr:.1f}, weekly RSI {wr:.1f}; both must exceed 60';return out
 f=clean(f);today=f[(f.index.normalize()==now.normalize())&(f.index+pd.Timedelta(minutes=1)<=now)]
 if today.empty:return empty(name,'Waiting for current-session data')
 end=min(now.floor('min'),today.index[-1]+pd.Timedelta(minutes=1),now.normalize()+pd.Timedelta(hours=15,minutes=30));expected=int((end-(now.normalize()+pd.Timedelta(hours=9,minutes=15))).total_seconds()/60)
 if expected<1 or len(today)!=expected:return empty(name,'Waiting for complete current-session minute data')
 if (now-(today.index[-1]+pd.Timedelta(minutes=1))).total_seconds()>300:return empty(name,'Underlying data stale')
 if now.weekday()>4 or not 555<=now.hour*60+now.minute<930:return empty(name,'Entry window closed; next market session required')
 x=pd.DataFrame([dict(open=today.open.iloc[0],high=today.high.max(),low=today.low.min(),close=today.close.iloc[-1],volume=today.volume.sum())],index=[now.normalize()]);full=pd.concat([d,x]);rs=rsi14(full.close);prev=float(rs.iloc[-2]);current=float(rs.iloc[-1]);ratio=float(x.volume.iloc[0]/d.volume.tail(20).mean())
 out.update(daily_rsi=current,previous_daily_rsi=prev,volume_ratio=ratio,matched=39<=current<=44)
 checks=[]
 if not 39<=current<=44:checks.append(f'Daily RSI {current:.1f} outside 39–44')
 if not prev<=40<current:checks.append('Wait for prior completed daily RSI <=40 and current RSI >40')
 if not x.close.iloc[0]>x.open.iloc[0]:checks.append('Daily candle not green')
 if not ratio>=1.5:checks.append(f'Daily volume {ratio:.2f}x; need >=1.5x prior 20-day mean')
 if checks:out['reason']='; '.join(checks);return out
 atr=float(features(full).atr.iloc[-1]);r=levels(name,float(x.close.iloc[0]),float(x.low.iloc[0]),atr,now,'PROVISIONAL daily RSI cross; daily candle still forming',d.tail(60))
 r.update(monthly_rsi=mr,weekly_rsi=wr,daily_rsi=current,previous_daily_rsi=prev,volume_ratio=ratio,stop_basis='Daily closing basis below current-session low plus 0.1 daily ATR',valid_until=min(now+pd.Timedelta(minutes=5),now.normalize()+pd.Timedelta(hours=15,minutes=30)).isoformat());return r

def smc_setup(b,higher,d,now):
 """15m liquidity-sweep/CHoCH or BOS/FVG-retest, with causal prior ranges."""
 name='SMC cash setup';out=empty(name,'Need 80 closed 15m bars, 30 closed 60m bars and 60 daily bars')
 if len(b)<80 or len(higher)<30 or d is None or len(d)<60:return out
 b=b[b.index+pd.Timedelta(minutes=15)<=now];higher=higher[higher.index+pd.Timedelta(minutes=60)<=now];d=d[d.index<now.normalize()]
 if len(b)<80 or len(higher)<30 or len(d)<60:return out
 x=features(b).iloc[-1];last=b.iloc[-1];prior=b.iloc[:-1];h=features(higher).iloc[-1]
 if b.index[-1].date()!=now.date() or (now-(b.index[-1]+pd.Timedelta(minutes=15))).total_seconds()>600:return empty(name,'Waiting for fresh completed 15m candle')
 if now.weekday()>4 or not 570<=now.hour*60+now.minute<915:return empty(name,'Intraday entry window closed')
 daily_ema=d.close.ewm(span=50,adjust=False).mean().iloc[-1]
 if not (d.close.iloc[-1]>daily_ema and h.close>h.ema9>h.ema21):return empty(name,'Daily/60m bullish trend not aligned')
 if not (last.close>last.open and x.rvol>=1.5 and x.adx>=20 and last.close>x.vwap):return empty(name,'Need green 15m candle, RVOL >=1.5, ADX >=20 and close above VWAP')
 # Sweep below a pre-existing 20-bar range, then a close back above it.
 sweep=None
 for j in range(len(b)-6,len(b)-1):
  p=b.iloc[j-20:j];c=b.iloc[j];level=p.low.min()
  if c.low<level<c.close and c.low<=(p.high.max()+p.low.min())/2:sweep=j
 reversal=False;stop=None;evidence=[]
 if sweep is not None:
  choch=float(b.iloc[sweep-5:sweep].high.max())
  # Prior five-bar structure was descending; this is a defined CHoCH proxy.
  descending=b.close.iloc[sweep-1]<b.close.iloc[sweep-5]
  if descending and last.close>choch and last.close-last.open>=.6*x.atr:
   reversal=True;stop=float(b.iloc[sweep:].low.min());evidence=['Sell-side liquidity sweep','Descending structure -> bullish CHoCH','Bullish displacement','Daily/60m alignment','Volume + VWAP']
 continuation=False
 if not reversal:
  for j in range(len(b)-7,len(b)-1):
   c=b.iloc[j];pre=b.iloc[j-20:j];res=float(pre.high.max())
   fvg_low=float(b.high.iloc[j-2]);fvg_high=float(c.low)
   # Gap formed by a three-candle move, BOS close, then first mitigated retest.
   if c.close>res and fvg_high>fvg_low and c.close>c.open:
    middle=b.iloc[j+1:-1]
    if len(middle) and (middle.low<=fvg_high).any():continue
    origin=b.iloc[max(0,j-5):j];red=origin[origin.close<origin.open]
    if red.empty:continue
    if last.low<=fvg_high and last.low>=fvg_low and last.close>fvg_high and last.close>prior.high.iloc[-1]:
     continuation=True;stop=float(min(last.low,red.low.iloc[-1],fvg_low));evidence=['20-bar bullish BOS','Three-candle bullish FVG','First FVG retest and rejection','Last bearish origin candle (order-block proxy)','Daily/60m alignment','Volume + VWAP'];break
 if not reversal and not continuation:return empty(name,'Wait for sweep + CHoCH or BOS + first FVG retest')
 name='SMC sweep + CHoCH' if reversal else 'SMC BOS + FVG retest'
 r=levels(name,float(last.close),stop,float(x.atr),now,'; '.join(evidence),prior.tail(60));r.update(evidence=evidence,volume_ratio=float(x.rvol),trigger_at=(b.index[-1]+pd.Timedelta(minutes=15)).isoformat(),stop_basis='15m closing basis below structural low plus 0.1 ATR',valid_until=min(now+pd.Timedelta(minutes=5),now.normalize()+pd.Timedelta(hours=15,minutes=15)).isoformat());return r

def ai_selected(d,f,now,ml):
 r=smc_setup(bars(f,15,now),bars(f,60,now),d,now)
 r['ml_status']=ml.get('status','NOT TRAINED');r['ml_probability']=ml.get('probability')
 if r.get('eligible') and not ml.get('pass_gate',False):r.update(eligible=False,strategy_status='WAIT ML',reason=r['reason']+'; validated 3m ML context unavailable: '+r['ml_status'])
 elif r.get('eligible'):r['reason']+='; 3m ML context passed (not validation of this SMC strategy)'
 return r
