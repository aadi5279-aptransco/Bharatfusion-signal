"""Read-only strategy orchestration; API failures are isolated from the legacy scanner."""
import pandas as pd
from engine import IST,bars
from strategy_rules import trap,evening,empty
from option_research import choose_atm,premium_plan
from market_safety import SafetyReports

class StrategyService:
 def __init__(self,api,cache,root,stop,strict=False,proxy=False,capital=100000,risk_pct=.5):
  self.api=api;self.cache=cache;self.safety=SafetyReports(root,stop);self.stop=stop;self.strict=strict;self.proxy=proxy
  self.capital=capital;self.budget=min(2000,max(0,capital*risk_pct/100));self.daily_checked={}
 def daily(self,item,now,long_history=False):
  key=item['segment']+':'+item['id'];d=self.cache.load_daily(key);day=str(now.date());check_key=key+(':long' if long_history else ':normal')
  if self.daily_checked.get(check_key)!=day:
   start=now.normalize()-pd.Timedelta(days=2200 if long_history else 450) if d is None or len(d)<125 or (long_history and (now-d.index[0]).days<1800) else d.index[-1]-pd.Timedelta(days=5)
   try:
    new=self.api.daily(item,start,now.normalize());self.cache.save_daily(key,new);d=self.cache.load_daily(key);self.daily_checked[check_key]=day
   except Exception:
    if d is None:raise
  if d is None:raise ValueError('Daily history unavailable')
  return d
 def futures(self,item,now):
  contract=item.get('future')
  if not contract:return None
  key='FUT:'+contract['id'];old=self.cache.load(key)
  start=now.normalize()-pd.Timedelta(days=7) if old is None else old.index[-1]-pd.Timedelta(minutes=5)
  new=self.api.history(contract,start,now);f=new if old is None else pd.concat([old,new]);f=f[~f.index.duplicated(keep='last')].sort_index();self.cache.save(key,new);return f
 def option(self,item,row,now):
  expiries=self.api.expiry_list(item)
  expiry=next((e for e in sorted(expiries) if e>str(now.date()) and any(c['expiry']==e for c in item.get('options',[]))),None)
  if expiry is None:raise ValueError('No mapped future stock-option expiry')
  chain=self.api.option_chain(item,expiry);contract,leg,spot=choose_atm(chain,item.get('options',[]),expiry,row['option_side'],now)
  quotes=self.api.quotes([contract]);quote=quotes.get('NSE_FNO',{}).get(contract['id'],{})
  return premium_plan(row,contract,leg,quote,pd.Timestamp.now(tz=IST),self.capital,self.budget)
 def review(self,item,row,now,frame,daily=None):
  r={**row,'symbol':item['symbol'],'data_at':now.isoformat()};blocks=[]
  if not r.get('matched'):return r
  if not r.get('eligible'):blocks.append(r.get('strategy_status','Outside entry window'))
  latest=frame.index[-1]+pd.Timedelta(minutes=1)
  if not 0<=(now-latest).total_seconds()<=300:blocks.append('Stale underlying feed')
  current=float(frame.close.iloc[-1]);r['underlying_now']=current
  sign=1 if r.get('option_side')!='PE' else -1
  if r['strategy']=='BTST consolidation' and current<=r.get('breakout_level',0):blocks.append('Price no longer sustaining previous-day high')
  if sign*(current-r['underlying_sl'])<=0:blocks.append('Underlying stop already breached')
  if sign*(current-r['underlying_t1'])>=0:blocks.append('Underlying T1 already reached')
  risk=abs(r['underlying_entry']-r['underlying_sl'])
  if abs(current-r['underlying_entry'])>.25*risk:blocks.append('Price moved >0.25R from reference entry; do not chase')
  istrap='trap' in r['strategy']
  gates=self.safety.gates(item.get('ticker') or item['symbol'],now,delivery=r['strategy']=='BTST consolidation',previous_day=r.get('previous_day'),allow_proxy=self.proxy,days=10 if r['strategy']=='125D breakout' else 4)
  if not item.get('ticker'):gates['ban_check']='UNKNOWN / exchange ticker unavailable'
  r.update(gates)
  if gates['ban_check']!='PASS':blocks.append('F&O ban check: '+gates['ban_check'])
  if not istrap and not gates['event_check'].startswith('PASS'):blocks.append(gates['event_check'])
  if r['strategy']=='BTST consolidation' and not gates['delivery_check'].startswith('PASS'):blocks.append('Delivery: '+gates['delivery_check'])
  if r.get('option_side'):
   # Quotes may be shown for matched patterns even when a safety gate blocks entry.
   if r.get('eligible') and not any('Stale' in x for x in blocks):
    try:
     r.update(self.option(item,r,now))
     if r['quantity']==0:blocks.append('One option lot exceeds structural risk/capital budget')
    except Exception as exc:blocks.append('Option unavailable: '+str(exc)[:150])
   else:blocks.append('No current option-entry quote for historical setup')
  else:
   r['quantity']=max(0,min(10,int(self.budget/risk),int(self.capital/current))) if risk>0 and current>0 else 0
   if r['quantity']==0:blocks.append('Cash quantity exceeds risk/capital budget')
  r['eligible']=not blocks;r['strategy_status']='READY / RESEARCH' if not blocks else 'BLOCKED'
  r['reason']='; '.join(blocks) if blocks else r['reason'];return r
 def run(self,item,cash,now):
  d=None;future=None
  try:future=self.futures(item,now);t=trap(future,now,self.strict)
  except Exception as exc:t=empty('Trap scan','Futures unavailable: '+str(exc)[:120])
  try:
   d=self.daily(item,now)
   prior=cash[cash.index.normalize()<now.normalize()]
   if len(prior) and d.index[-1].normalize()<prior.index[-1].normalize():raise ValueError('Daily history missing latest cash session')
   even=evening(d,cash,now)
  except Exception as exc:even=[empty(n,'Daily data unavailable: '+str(exc)[:120]) for n in ('125D breakout','BTST consolidation')]
  t=self.review(item,t,now,future if future is not None else cash,d);t['contract']=str((item.get('future') or {}).get('symbol','UNAVAILABLE'))
  return t,[self.review(item,r,now,cash,d) for r in even],d,future
