"""Bounded/coalesced automatic training with persisted per-day attempt limits."""
from collections import OrderedDict
import json,os
from pathlib import Path
from engine import IST
import pandas as pd

class AutoTraining:
 def __init__(self,root):
  self.path=Path(root)/'auto_training_attempts.json';self.pending=OrderedDict()
  try:self.attempts=json.loads(self.path.read_text())
  except (OSError,ValueError):self.attempts={}
 def key(self,r):return r['symbol']+'|'+str(r.get('ml_minutes',3))
 def enqueue(self,rows):
  rows=list(rows);keys={self.key(r) for r in rows}
  self.pending=OrderedDict((k,v) for k,v in self.pending.items() if k in keys)
  day=str(pd.Timestamp.now(tz=IST).date())
  for r in rows:
   key=self.key(r)
   if r.get('mode')!='DHAN LIVE' or not r.get('cache_key') or self.attempts.get(key)==day:continue
   if r.get('ml',{}).get('status') in ('AGREE','WAIT / DISAGREE','PRE-VALIDATION DATA','BOOK DATA MISSING'):continue
   if key in self.pending or len(self.pending)<25:self.pending[key]=r.copy()
 def pop(self):
  if not self.pending:return None
  key,r=self.pending.popitem(last=False)
  day=str(pd.Timestamp.now(tz=IST).date());self.attempts={k:v for k,v in self.attempts.items() if v==day};self.attempts[key]=day
  self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.attempts));os.replace(tmp,self.path)
  return r
 def clear(self):self.pending.clear()
