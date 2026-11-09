"""Opt-in paper position alerts. No broker orders or guaranteed loss caps."""
import json,threading,uuid
from pathlib import Path
import pandas as pd
from engine import bars,IST

class PaperWatch:
 def __init__(self,root):self.path=Path(root)/'strategy_paper_positions.json';self.lock=threading.Lock()
 def read(self):
  try:return json.loads(self.path.read_text())
  except (OSError,ValueError):return []
 def save(self,rows):
  self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(rows,indent=2));tmp.replace(self.path)
 def add(self,row,entry,quantity,time_only=False,now=None):
  now=pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now)
  with self.lock:
   rows=self.read();rows.append(dict(id=uuid.uuid4().hex,symbol=row['symbol'],strategy=row['strategy'],entry=float(entry),quantity=int(quantity),created=now.isoformat(),last_alert='',time_only=time_only,row=row));self.save(rows)
 def monitor(self,item,cash,daily,future,api,now):
  alerts=[]
  with self.lock:rows=self.read()
  updates={}
  for p in rows:
   if p['symbol']!=item['symbol']:continue
   r=p['row'];created=pd.Timestamp(p['created']);name=p['strategy'];option=bool(r.get('option_id'));price=None;notes=[]
   if option:
    try:
     q=api.quotes([dict(id=r['option_id'],segment='NSE_FNO')]).get('NSE_FNO',{}).get(r['option_id'],{})
     qt=pd.Timestamp(q['last_trade_time']);qt=qt.tz_localize(IST) if qt.tzinfo is None else qt
     if 0<=(now-qt).total_seconds()<=120:price=float(q['depth']['buy'][0]['price'])
    except Exception:pass
   elif len(cash) and 0<=(now-(cash.index[-1]+pd.Timedelta(minutes=1))).total_seconds()<=300:price=float(cash.close.iloc[-1])
   if price and (p['entry']-price)*p['quantity']>=2000:notes.append('EXIT ALERT: paper loss >= ₹2,000 (not an executed exit)')
   base=future if 'trap' in name else cash
   if base is not None:
    interval=15 if 'trap' in name else 5
    b=bars(base,interval,now);b=b[b.index+pd.Timedelta(minutes=interval)>created]
    side=-1 if r.get('option_side')=='PE' else 1
    breach=len(b) and any(side*(c-r['underlying_sl'])<0 for c in b.close)
    if name=='125D breakout':
     closed=daily[daily.index.normalize()>=created.normalize()] if daily is not None else None
     breach=closed is not None and len(closed) and any(c<r['underlying_sl'] for c in closed.close)
     if now.hour*60+now.minute>=930 and len(b):breach=breach or b.close.iloc[-1]<r['underlying_sl']
    if breach:notes.append(('SL BREACH INFO (125D time-only mode)' if name=='125D breakout' and p['time_only'] else 'EXIT ALERT: closing-basis structural SL'))
   if daily is not None and len(cash):
    sessions=set(daily.index[daily.index.normalize()>=created.normalize()].date)
    if cash.index[-1].date()==now.date():sessions.add(now.date())
    if name=='125D breakout' and len(sessions)>=5 and now.hour*60+now.minute>=925:notes.append('EXIT ALERT: fifth observed trading session after 15:25')
    if name=='BTST consolidation' and len(sessions)>=2 and now.hour*60+now.minute>=675:notes.append('EXIT ALERT: next-session first two hours elapsed')
   if price:
    targets=(r.get('premium_t1_est'),r.get('premium_t2_est')) if option else (r.get('underlying_t1'),r.get('underlying_t2'))
    for label,target in zip(('T1','T2'),targets):
     if target and price>=target:notes.append(label+' reached (paper quote observation)')
   msg=' | '.join(notes)
   if msg and msg!=p['last_alert']:alerts.append(p['symbol']+' '+name+': '+msg);updates[p['id']]=msg
  if updates:
   with self.lock:
    current=self.read()
    for p in current:
     if p['id'] in updates:p['last_alert']=updates[p['id']]
    self.save(current)
  return alerts
