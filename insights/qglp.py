"""Additional user-imported QGLP research. No broker calls or order levels."""
import csv,io,json,math,re,threading,os
from bisect import bisect_left,bisect_right
from pathlib import Path
from datetime import datetime,date
from insights.config import IST

COLUMNS={'Name':'name','Market Capitalization':'mcap_cr','Return on capital employed':'roce','Return on equity':'roe',
'Sales growth 3Years':'sales_g3','Profit growth 3Years':'profit_g3','Debt to equity':'de','Price to Earning':'pe',
'Promoter holding':'promoter','Pledged percentage':'pledge','Operating cash flow 3years':'cfo3','Net profit 3years':'pat3',
'Symbol':'symbol','Sector':'sector'}
WEIGHTS=[('roce',.20,True),('roe',.10,True),('sales_g3',.15,True),('profit_g3',.15,True),('cash_conv',.15,True),('de',.10,False),('peg',.15,False)]
REQUIRED=list(COLUMNS.values())[:12]
RULES=[('mcap_cr','Market cap ₹500–15,000 crore',lambda v:500<=v<=15000),('roce','ROCE ≥15%',lambda v:v>=15),
('sales_g3','3-year sales growth ≥15%',lambda v:v>=15),('profit_g3','3-year profit growth ≥15%',lambda v:v>=15),
('de','Debt/equity 0–0.7',lambda v:0<=v<=.7),('pledge','Pledged shares 0–10%',lambda v:0<=v<=10),
('promoter','Promoter holding 40–100%',lambda v:40<=v<=100),('pe','Positive P/E',lambda v:v>0),
('pat3','Positive cumulative 3-year net profit',lambda v:v>0),('cash_conv','3-year cash conversion ≥0.7',lambda v:v>=.7)]

def key(s):return re.sub('[^a-z0-9]','',str(s).lower())
def numeric(value):
    s=str(value).strip().replace(',','').replace('%','').replace('₹','').strip()
    if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1]
    try:v=float(s);return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def parse(raw):
    if len(raw)>2_000_000:raise ValueError('CSV must be smaller than 2 MB')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not reader.fieldnames:raise ValueError('CSV header required')
    aliases={key(k):v for k,v in COLUMNS.items()};aliases.update({key(v):v for v in COLUMNS.values()})
    mapped=[aliases.get(key(h)) for h in reader.fieldnames]
    recognized=[x for x in mapped if x]
    if len(recognized)!=len(set(recognized)):raise ValueError('Duplicate mapped columns')
    missing=set(REQUIRED)-set(recognized)
    if missing:raise ValueError('Missing required columns: '+', '.join(sorted(missing)))
    rows=[];seen=set()
    for i,row in enumerate(reader,2):
        if len(rows)>=10000:raise ValueError('Maximum 10,000 rows')
        if None in row:raise ValueError(f'Row {i}: extra fields; quote numbers containing commas')
        out={aliases[key(h)]:v for h,v in row.items() if key(h) in aliases}
        out['name']=str(out.get('name') or '').strip()
        if not out['name']:raise ValueError(f'Row {i}: company name required')
        identity=key(out.get('symbol') or out['name'])
        if not identity or identity in seen:raise ValueError(f'Row {i}: duplicate or invalid company identifier')
        seen.add(identity)
        for col in REQUIRED[1:]:out[col]=numeric(out.get(col))
        out['symbol']=str(out.get('symbol') or '').strip();out['sector']=str(out.get('sector') or '').strip()
        rows.append(out)
    if not rows:raise ValueError('CSV contains no company rows')
    return rows

def dates(asof,period,now):
    try:a=date.fromisoformat(asof);p=date.fromisoformat(period)
    except (TypeError,ValueError):raise ValueError('Use YYYY-MM-DD dates') from None
    if p>a or a>now:raise ValueError('Period end must not exceed export date; future dates are not allowed')
    return (now-a).days<=180 and (now-p).days<=210

def evaluate(bundle,now):
    fresh=dates(bundle['asof'],bundle['period_end'],now);rows=[]
    for raw in bundle['rows']:
        r=dict(raw);missing=[c for c in REQUIRED[1:] if r.get(c) is None]
        r['cash_conv']=r['cfo3']/r['pat3'] if r.get('cfo3') is not None and r.get('pat3') is not None and r['pat3']>0 else None
        r['peg']=r['pe']/r['profit_g3'] if r.get('pe') is not None and r['pe']>0 and r.get('profit_g3') is not None and r['profit_g3']>0 else None
        for derived in ('cash_conv','peg'):
            if r[derived] is not None and not math.isfinite(r[derived]):r[derived]=None
        if r['peg'] is None:missing.append('peg')
        if r['cash_conv'] is None:missing.append('cash_conv')
        checks=[dict(label=label,value=r.get(col),status='UNVERIFIED' if r.get(col) is None else 'PASS' if predicate(r[col]) else 'FAIL') for col,label,predicate in RULES]
        financial=any(word in r.get('sector','').lower() for word in ('bank','finance','financial','insurance','nbfc'))
        r.update(checks=checks,score=None,rank=None,missing=missing,
                 warnings=['Growth consistency, accounting quality, valuation and longevity require manual review.']+([] if r['sector'] else ['Sector missing: confirm suitability; this model is not for financial companies.']))
        r['status']='STALE' if not fresh else 'UNSUPPORTED SECTOR' if financial else 'UNVERIFIED' if missing else 'REJECTED' if any(c['status']=='FAIL' for c in checks) else 'QUALIFIED'
        rows.append(r)
    qualified=[r for r in rows if r['status']=='QUALIFIED'];n=len(qualified)
    distributions={col:sorted(r[col] for r in qualified) for col,_,_ in WEIGHTS}
    for r in qualified:
        parts=[]
        for col,weight,higher in WEIGHTS:
            v=r[col];values=distributions[col]
            # Average tied positions, normalized 0–100. A singleton has no relative evidence.
            below=bisect_left(values,v);ties=bisect_right(values,v)-below
            pct=(below+(ties-1)/2)/(n-1) if n>1 else .5
            if not higher:pct=1-pct
            parts.append(dict(metric=col,value=v,weight=weight,points=round(100*weight*pct,3)))
        r['score']=round(sum(x['points'] for x in parts),2);r['score_parts']=parts
    qualified.sort(key=lambda r:(-r['score'],r['name'].casefold()))
    previous=None;rank=0
    for position,r in enumerate(qualified,1):
        if r['score']!=previous:rank=position
        r['rank']=rank;previous=r['score']
    others=sorted((r for r in rows if r['status']!='QUALIFIED'),key=lambda r:(r['status'],r['name'].casefold()))
    return dict(status='READY' if fresh else 'STALE IMPORT — REPLACE DATA',asof=bundle['asof'],period_end=bundle['period_end'],source=bundle['source'],
                count=len(rows),qualified=n,rows=qualified+others,note='Relative QGLP research score, not return probability or a trade signal. Imported values are user supplied, not independently verified.')

class QGLPResearch:
    def __init__(self,root):
        self.path=Path(root)/'qglp_import.json';self.lock=threading.RLock();self.bundle=None;self.error=''
        try:
            if self.path.exists():
                b=json.loads(self.path.read_text(encoding='utf-8'));evaluate(b,datetime.now(IST).date());self.bundle=b
        except (OSError,ValueError,KeyError,TypeError):self.error='Saved QGLP import could not be read; import again.'
    def snapshot(self):
        with self.lock:
            if self.bundle is None:return dict(status='IMPORT REQUIRED',rows=[],qualified=0,count=0,error=self.error)
            return evaluate(self.bundle,datetime.now(IST).date())
    def import_csv(self,raw,asof,period,source):
        today=datetime.now(IST).date();source=str(source).strip()
        if not 3<=len(source)<=200:raise ValueError('Provide a source description (3–200 characters)')
        if not dates(asof,period,today):raise ValueError('Export must be within 180 days and financial period within 210 days')
        b=dict(rows=parse(raw),asof=asof,period_end=period,source=source)
        result=evaluate(b,today)
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(b,allow_nan=False),encoding='utf-8');os.replace(temp,self.path)
            self.bundle=b;self.error=''
        return result
