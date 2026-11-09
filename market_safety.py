"""Dated public NSE reports and explicit reviewed-event coverage. Unknown never passes."""
import io,json,time,urllib.request
from pathlib import Path
import pandas as pd
from engine import IST


def parse_ban(text,day):
 f=pd.read_csv(io.StringIO(text));f.columns=[str(c).strip().upper() for c in f.columns]
 col=next((c for c in f if c in ('SYMBOL','SECURITY','SECURITY SYMBOL')),None)
 if col is None:raise ValueError('Ban CSV must contain SYMBOL')
 vals={str(v).strip().upper() for v in f[col].dropna()};vals-={'NIL','NONE','NO SECURITIES','-'}
 if any('<' in v or len(v)>40 for v in vals):raise ValueError('Invalid ban content')
 return {'date':str(day),'symbols':sorted(vals),'source':'NSE dated F&O ban CSV'}


def parse_delivery(text,day):
 f=pd.read_csv(io.StringIO(text));f.columns=[str(c).strip().upper() for c in f.columns]
 if not {'SYMBOL','SERIES','DATE1','DELIV_PER'}.issubset(f.columns):raise ValueError('Use NSE full bhavcopy/deliverable CSV with DATE1 and DELIV_PER')
 dates=pd.to_datetime(f.DATE1.str.strip(),dayfirst=True,errors='coerce').dt.date
 if dates.isna().any() or any(str(d)!=str(day) for d in dates):raise ValueError('Delivery report date mismatch')
 out={}
 for r in f[f.SERIES.str.strip()=='EQ'].itertuples():
  try:v=float(str(r.DELIV_PER).strip())
  except ValueError:continue
  if 0<=v<=100:out[str(r.SYMBOL).strip()]=v
 return {'date':str(day),'values':out,'source':'NSE full bhavcopy DELIV_PER'}


def event_gate(calendar,symbol,now,days=4):
 try:
  if not calendar.get('sources') or not calendar.get('reviewed_by'):return 'EVENT CALENDAR UNKNOWN / INVALID'
  now=pd.Timestamp(now);checked=pd.Timestamp(calendar['reviewed_at']);start=pd.Timestamp(calendar['coverage_start']);end=pd.Timestamp(calendar['coverage_end'])
  if any(x.tzinfo is None for x in (checked,start,end)):raise ValueError('Timezone missing')
  if not 0<=(now-checked).total_seconds()<=86400 or start>now or end<now+pd.Timedelta(days=days):return 'EVENT CALENDAR UNKNOWN / STALE'
  for e in calendar['events']:
   t=pd.Timestamp(e['at'])
   if t.tzinfo is None or not e.get('source'):raise ValueError('Event source/time missing')
   if now<=t<=now+pd.Timedelta(days=days) and (e.get('symbol','ALL') in ('ALL',symbol)) and e.get('impact','HIGH')=='HIGH':return 'EVENT BLOCK: '+e['title']
  return 'PASS (reviewed calendar)'
 except (KeyError,ValueError,TypeError):return 'EVENT CALENDAR UNKNOWN / INVALID'


class SafetyReports:
 def __init__(self,root,stop):self.root=Path(root)/'safety';self.root.mkdir(parents=True,exist_ok=True);self.stop=stop;self.last={};self.memory={}
 def _read(self,kind,day):
  key=f'{kind}_{day}';path=self.root/(key+'.json')
  if path.exists():
   try:
    obj=json.loads(path.read_text())
    if obj.get('date')==str(day):return obj
   except (OSError,ValueError):pass
  if time.monotonic()-self.last.get(key,-1e9)<300:return self.memory.get(key)
  self.last[key]=time.monotonic();stamp=pd.Timestamp(day).strftime('%d%m%Y')
  suffix=f'content/fo/fo_secban_{stamp}.csv' if kind=='ban' else f'products/content/sec_bhavdata_full_{stamp}.csv'
  for host in ('https://nsearchives.nseindia.com/','https://archives.nseindia.com/'):
   if self.stop.is_set():return None
   try:
    req=urllib.request.Request(host+suffix,headers={'User-Agent':'Mozilla/5.0','Accept':'text/csv'})
    with urllib.request.urlopen(req,timeout=8) as response:txt=response.read(4_000_000).decode('utf-8-sig')
    obj=(parse_ban if kind=='ban' else parse_delivery)(txt,day);obj['source_url']=host+suffix
    self.memory[key]=obj;path.write_text(json.dumps(obj));return obj
   except Exception:continue
  return None
 def gates(self,symbol,now,delivery=False,previous_day=None,allow_proxy=False,days=4):
  day=str(pd.Timestamp(now).date());ban=self._read('ban',day);out={}
  out['ban_check']='UNKNOWN' if ban is None else 'BANNED' if symbol in ban['symbols'] else 'PASS'
  try:calendar=json.loads((self.root/'risk_calendar.json').read_text())
  except (OSError,ValueError):calendar={}
  out['event_check']=event_gate(calendar,symbol,now,days)
  out['delivery_check']='N/A';out['delivery_pct']=None;out['delivery_date']=''
  if delivery:
   report=self._read('delivery',day);proxy=False
   if report is None and allow_proxy and previous_day:report=self._read('delivery',previous_day);proxy=report is not None
   v=report.get('values',{}).get(symbol) if report else None
   out.update(delivery_pct=v,delivery_date=report['date'] if report else '',delivery_check='UNKNOWN' if v is None else ('PASS PRIOR-SESSION PROXY' if proxy else 'PASS') if v>40 else 'FAIL <=40%')
  return out
