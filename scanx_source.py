"""Read the public screener snapshot. Never silently substitute another universe."""
import json,re,urllib.request
import pandas as pd
from engine import IST
URL='https://scanx.trade/stock-screener/insti-footprints-screenerha-453307'
HEADERS=['Exch','Sid','Seg','Inst','LotSize','TickSize','Multiplier','DispSym','Isin','Seosym','Ltp','Pchange','PPerchange','Volume','High1Yr','Low1Yr','Pe','Mcap','FIIHolding','FIIHLDChagPer','DIIHLDChagPer','PromoterShareholdingIncrease','DIIHolding','YoYLastQtrlyProfitGrowth','Year5ROCE','Debt2Eq','PricePerchng3mon','Sym']
EXPECTED={'Exch':('', 'NSE'),'Mcap':('gte','1000'),'FIIHLDChagPer':('gte','0'),'DIIHLDChagPer':('gte','0'),'FIIHolding':('gte','2'),'DIIHolding':('gte','2'),'YoYLastQtrlyProfitGrowth':('gte','15'),'Year5ROCE':('gte','10'),'Debt2Eq':('RANGE','0_0.5'),'PricePerchng3mon':('gte','10'),'PromoterShareholdingIncrease':('lte','10000'),'OgInst':('','ES')}

def parse_snapshot(html,now):
 m=re.search(r'<script\b[^>]*\bid="ng-state"[^>]*>(.*?)</script>',html,re.S)
 if not m:raise ValueError('ScanX public snapshot missing; no candidate substitution')
 state=json.loads(m[1]);values=[v for v in state.values() if isinstance(v,dict)]
 meta=[x for v in values if 'screener/getDetails' in v.get('u','') for x in v.get('b',{}).get('data',[]) if x.get('screener_id')==453307]
 if len(meta)!=1:raise ValueError('ScanX screener identity unavailable')
 filters=meta[0]['filters'];params={p['field']:(p['op'],str(p['val'])) for p in filters['params']}
 if params!=EXPECTED or filters.get('logic_op')!='AND':raise ValueError('ScanX filters changed; review required')
 snapshots=[v['b'] for v in values if v.get('u','').endswith('/customscan/v2/fetchdt') and v.get('b',{}).get('headers')==HEADERS]
 if len(snapshots)!=1:raise ValueError('ScanX result snapshot ambiguous')
 data=snapshots[0];rows=data['data']
 if int(data['tot_rec'])!=len(rows) or int(data.get('tot_pg',1))>1:raise ValueError('ScanX snapshot paginated; complete universe unavailable')
 stamp=pd.Timestamp(pd.to_datetime(data['last_resp_time'],format='%d-%m-%Y %H:%M:%S')).tz_localize(IST)
 age=(pd.Timestamp(now)-stamp).total_seconds()
 if not -300<=age<=900:raise ValueError('ScanX source timestamp stale or future; wait for a current snapshot')
 result={}
 for row in rows:
  if len(row)!=28 or row[0]!='NSE' or row[2]!='E' or row[3]!='EQUITY':raise ValueError('ScanX equity schema changed')
  fields=dict(zip(HEADERS,row))
  try:
   for key,(op,value) in EXPECTED.items():
    if op=='gte' and not float(fields[key])>=float(value):raise ValueError()
    if op=='lte' and not float(fields[key])<=float(value):raise ValueError()
   if not 0<=float(fields['Debt2Eq'])<=.5:raise ValueError()
  except (TypeError,ValueError,KeyError):raise ValueError('ScanX candidate does not satisfy the verified source filters') from None
  sid=str(int(row[1]));result[sid]=dict(id=sid,symbol=row[-1],name=row[7],source_at=stamp.isoformat())
 return result

def fetch(now):
 req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
 with urllib.request.urlopen(req,timeout=15) as response:html=response.read(8_000_000).decode('utf-8')
 return parse_snapshot(html,now)
