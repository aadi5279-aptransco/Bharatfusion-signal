"""Dated FII ownership comparisons, separate from attributable daily deals.

Public Screener company pages are a secondary source. A percentage change is
not proof of cash buying/selling: dilution and reclassification also affect it.
No credentials, orders, private endpoints or access-control workarounds.
"""
from __future__ import annotations
import calendar
import csv
import io
import json
import math
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from insights.config import IST

STARTER_SYMBOLS = ['RELIANCE','HDFCBANK','ICICIBANK','INFY','TCS','ITC','LT',
                   'SBIN','AXISBANK','KOTAKBANK','BHARTIARTL','HINDUNILVR',
                   'SUNPHARMA','TITAN','MARUTI','BAJFINANCE','HCLTECH','WIPRO',
                   'TATAMOTORS','NTPC','POWERGRID','ULTRACEMCO','ASIANPAINT',
                   'JSWSTEEL','TATASTEEL']
QUERIES = {'increased':'Change in FII holding > 0',
           'decreased':'Change in FII holding < 0'}
NOTE = ('Reported ownership change, not daily buy/sell transactions. '
        'Dilution, corporate actions and reclassification can change percentages. '
        'Company reporting quarters may differ. No trading signals are generated.')


def symbols_from(value):
    if not isinstance(value,str):raise ValueError('Enter comma-separated NSE symbols')
    symbols=list(dict.fromkeys(x.upper() for x in re.split(r'[,\s]+',value.strip()) if x))
    if not 1<=len(symbols)<=200:raise ValueError('Enter 1–200 NSE symbols')
    if any(not re.fullmatch(r'[A-Z0-9&._-]{1,32}',x) for x in symbols):
        raise ValueError('Use NSE symbols, not company descriptions or URLs')
    return symbols


def percentage(value):
    s=str(value).strip().replace('%','').replace(',','')
    try:n=float(s)
    except (ValueError,TypeError):raise ValueError('Missing or invalid FII percentage') from None
    if not math.isfinite(n) or not 0<=n<=100:raise ValueError('FII percentage outside 0–100')
    return n


def quarter(value):
    s=str(value).strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',s):d=date.fromisoformat(s)
        else:
            t=datetime.strptime(s,'%b %Y')
            d=date(t.year,t.month,calendar.monthrange(t.year,t.month)[1])
    except ValueError:raise ValueError('Quarter must be YYYY-MM-DD or Sep 2026') from None
    if d.month not in (3,6,9,12) or d.day!=calendar.monthrange(d.year,d.month)[1]:
        raise ValueError('Only completed calendar-quarter end dates are supported')
    return d


def comparison(symbol,company,previous,current,previous_q,current_q,now,source_url,source):
    p,c=percentage(previous),percentage(current)
    pq,cq=quarter(previous_q),quarter(current_q)
    if cq>now.date() or (cq.year*12+cq.month)-(pq.year*12+pq.month)!=3:
        raise ValueError('Need two consecutive, non-future reporting quarters')
    delta=round(c-p,4)
    return dict(symbol=symbol,company=company or symbol,previous_pct=p,current_pct=c,
        change_pp=delta,direction='INCREASED' if delta>0 else 'DECREASED' if delta<0 else 'UNCHANGED',
        previous_quarter=pq.isoformat(),current_quarter=cq.isoformat(),
        source_url=source_url,source=source,retrieved_at=now.isoformat(),
        period_verified=True)


class ShareholdingHTML(HTMLParser):
    """Read only quarterly-shp; yearly and financial tables cannot leak in."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0;self.rows=[];self.row=None;self.cell=None;self.nse_symbols=set()
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a':
            u=urlparse(attrs.get('href',''))
            if u.hostname in ('www.nseindia.com','nseindia.com'):
                self.nse_symbols.update(parse_qs(u.query).get('symbol',[]))
        if tag=='div':
            if self.depth:self.depth+=1
            elif attrs.get('id')=='quarterly-shp':self.depth=1
        if not self.depth:return
        if tag=='tr':self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        elif tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None
        elif tag=='div' and self.depth:self.depth-=1


def parse_company(raw,symbol,now,url):
    if not isinstance(raw,bytes) or len(raw)>2_000_000:raise ValueError('Company page too large')
    parser=ShareholdingHTML();parser.feed(raw.decode('utf-8-sig'))
    if symbol not in parser.nse_symbols:
        raise ValueError('Company page did not confirm the requested NSE symbol')
    heads=[r for r in parser.rows if len(r)>2 and r[0]=='']
    fiis=[r for r in parser.rows if r and re.sub(r'[^a-z]','',r[0].lower()) in ('fiis','fii','fpis','fpi')]
    if len(heads)!=1 or len(fiis)!=1 or len(heads[0])!=len(fiis[0]):
        raise ValueError('Quarterly FII table missing or changed; use CSV import')
    # Keep missing latest values as missing; do not skip back to an older pair.
    return comparison(symbol,symbol,fiis[0][-2],fiis[0][-1],heads[0][-2],heads[0][-1],
                      now,url,'SCREENER PUBLIC QUARTERLY SHAREHOLDING')


def fetch_company(symbol):
    url='https://www.screener.in/company/'+quote(symbol,safe='')+'/consolidated/'
    try:
        with urlopen(Request(url,headers={'User-Agent':'BharatSignalResearch/1.0',
                         'Accept':'text/html'}),timeout=12) as r:
            final=urlparse(r.geturl())
            if final.hostname!='www.screener.in' or not final.path.startswith('/company/'):
                raise PermissionError('Source requires sign-in. Use your downloaded CSV; no login bypass attempted.')
            raw=r.read(2_000_001)
        return raw,url
    except HTTPError as exc:
        if exc.code in (401,403,429):raise PermissionError('Source denied/rate-limited access. Scan stopped; use CSV import.') from exc
        raise ValueError('Company page unavailable (HTTP '+str(exc.code)+')') from exc
    except PermissionError:
        raise
    except (URLError,TimeoutError,OSError) as exc:
        raise ValueError('Company source unavailable or timed out') from exc


def parse_csv(raw,now):
    """Dated wide CSV, or Screener export with explicit period-unverified labels."""
    if not isinstance(raw,bytes) or not 1<=len(raw)<=2_000_000:raise ValueError('CSV must be under 2 MB')
    text=raw.decode('utf-8-sig')
    if text.lstrip().startswith('<'):raise ValueError('Upload CSV, not an HTML login page')
    reader=csv.DictReader(io.StringIO(text),delimiter='\t' if '\t' in text.splitlines()[0] else ',')
    norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
    fields={norm(x):x for x in (reader.fieldnames or [])}
    def field(*names):return next((fields[n] for n in names if n in fields),None)
    name=field('company','name');sym=field('symbol','nsesymbol','nsecode')
    current=field('currentpct','fiiholding','fiihold','fiiholdingpercentage')
    previous=field('previouspct','previousfiiholding')
    delta=field('changepp','changeinfiiholding','chginfiihold','changeinfiiholdingpercentage')
    pq,cq=field('previousquarter'),field('currentquarter')
    if not (name or sym) or not current or not (previous or delta):
        raise ValueError('Required columns: Name/Symbol, FII holding, Change in FII holding; or Symbol, Previous pct, Current pct, Previous quarter, Current quarter')
    rows=[];seen=set()
    for lineno,r in enumerate(reader,2):
        if not any(str(v or '').strip() for v in r.values()):continue
        if len(rows)>=10000:raise ValueError('Maximum 10,000 rows per import')
        if None in r:raise ValueError('Malformed CSV row '+str(lineno))
        label=str(r.get(name) or r.get(sym) or '').strip()
        symbol=str(r.get(sym) or '').strip().upper() or None
        if not label or len(label)>240:raise ValueError('Invalid company name on row '+str(lineno))
        if symbol and (len(symbols_from(symbol))!=1 or symbols_from(symbol)[0]!=symbol):
            raise ValueError('Invalid symbol on row '+str(lineno))
        key=(symbol or label).casefold()
        if key in seen:raise ValueError('Duplicate company on row '+str(lineno))
        seen.add(key)
        c=percentage(r.get(current,''))
        try:
            change=float(str(r.get(delta,'')).replace('%','').replace(',','')) if delta else None
            if change is not None and not math.isfinite(change):raise ValueError()
            p=percentage(r.get(previous,'')) if previous else percentage(c-change)
        except (ValueError,TypeError):raise ValueError('Invalid holding/change on row '+str(lineno)) from None
        if change is not None and abs((c-p)-change)>0.021:raise ValueError('Inconsistent holding change on row '+str(lineno))
        if pq or cq:
            if not pq or not cq:raise ValueError('Both quarter columns are required')
            obj=comparison(symbol,label,p,c,r.get(pq,''),r.get(cq,''),now,
                           'https://www.screener.in/','USER IMPORT — NOT INDEPENDENTLY VERIFIED')
        else:
            change=round(c-p,4)
            obj=dict(symbol=symbol,company=label,previous_pct=round(p,4),current_pct=c,
                change_pp=change,direction='INCREASED' if change>0 else 'DECREASED' if change<0 else 'UNCHANGED',
                previous_quarter=None,current_quarter=None,period_verified=False,
                source='USER IMPORT — REPORTING PERIOD NOT SUPPLIED',source_url='https://www.screener.in/',
                retrieved_at=now.isoformat())
        rows.append(obj)
    if not rows:raise ValueError('No usable company rows in CSV')
    return rows


class FIIHoldings:
    def __init__(self,root,fetcher=None,delay=1.0):
        self.path=Path(root)/'fii_holdings.sqlite';self.path.parent.mkdir(parents=True,exist_ok=True)
        self.fetcher=fetcher or fetch_company;self.delay=delay;self._lock=threading.Lock();self._thread=None
        self._last_start=0.;self._state={'status':'NOT SCANNED','completed':0,'requested':0}
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS holdings_snapshot (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS holdings_cache (symbol TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=8)
        try:
            with db:yield db
        finally:db.close()
    def _save(self,rows,coverage):
        payload=json.dumps(dict(rows=rows,coverage=coverage))
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO holdings_snapshot VALUES(1,?)',(payload,))
    def snapshot(self,now=None):
        now=now or datetime.now(IST)
        with self.connect() as db:
            record=db.execute('SELECT payload FROM holdings_snapshot WHERE id=1').fetchone()
        saved=json.loads(record[0]) if record else dict(rows=[],coverage={})
        rows=saved['rows']
        for row in rows:
            row['stale_quarter']=bool(row['current_quarter'] and (now.date()-date.fromisoformat(row['current_quarter'])).days>180)
            row['cache_age_hours']=round(max(0,(now-datetime.fromisoformat(row['retrieved_at'])).total_seconds()/3600),1)
        with self._lock:state=dict(self._state)
        return dict(rows=rows,increased=sorted([r for r in rows if r['change_pp']>0],key=lambda x:-x['change_pp']),
            decreased=sorted([r for r in rows if r['change_pp']<0],key=lambda x:x['change_pp']),
            unchanged_count=sum(r['change_pp']==0 for r in rows),coverage=saved['coverage'],refresh=state,
            starter_symbols=STARTER_SYMBOLS,queries=QUERIES,
            query_urls={k:'https://www.screener.in/screen/raw/?'+urlencode({'query':v}) for k,v in QUERIES.items()},
            note=NOTE)
    def _scan(self,symbols,now):
        rows=[];failures=[];stopped=False;completed=0;cached=0
        try:
            for symbol in symbols:
                try:
                    with self.connect() as db:
                        item=db.execute('SELECT payload FROM holdings_cache WHERE symbol=?',(symbol,)).fetchone()
                    row=json.loads(item[0]) if item else None
                    age=(now-datetime.fromisoformat(row['retrieved_at'])).total_seconds() if row else None
                    if row and 0<=age<86400:
                        cached+=1
                    else:
                        raw,url=self.fetcher(symbol)
                        row=parse_company(raw,symbol,now,url)
                        with self.connect() as db:
                            db.execute('INSERT OR REPLACE INTO holdings_cache VALUES(?,?)',(symbol,json.dumps(row)))
                        if self.delay:time.sleep(self.delay)
                    rows.append(row)
                except PermissionError as exc:
                    failures.append(dict(symbol=symbol,error=str(exc)));stopped=True
                except (ValueError,OSError,UnicodeError) as exc:
                    failures.append(dict(symbol=symbol,error=str(exc)[:180]))
                completed+=1
                with self._lock:self._state.update(completed=completed,current_symbol=symbol,available=len(rows))
                if stopped:break
            coverage=dict(mode='SELECTED NSE SYMBOLS — NOT WHOLE MARKET',requested=len(symbols),
                completed=completed,available=len(rows),cached=cached,failures=failures,
                not_attempted=symbols[completed:],finished_at=now.isoformat())
            # An unsuccessful refresh cannot erase a previously successful list.
            if rows:self._save(rows,coverage)
            with self._lock:self._state.update(status='ACCESS BLOCKED' if stopped else 'COMPLETE' if rows else 'NO DATA',
                coverage=coverage,error='Previous saved list retained' if not rows else None)
        except Exception:
            with self._lock:self._state.update(status='FAILED',error='Refresh failed; previous saved list retained')
    def start(self,value,now=None):
        symbols=symbols_from(value);now=now or datetime.now(IST)
        with self._lock:
            if self._thread and self._thread.is_alive():return dict(status='BUSY')
            if self._last_start and time.monotonic()-self._last_start<30:return dict(status='RATE_LIMITED')
            self._last_start=time.monotonic()
            self._state=dict(status='RUNNING',requested=len(symbols),completed=0,available=0)
            self._thread=threading.Thread(target=self._scan,args=(symbols,now),daemon=True,name='FIIQuarterlyHoldings')
            self._thread.start()
        return dict(status='STARTED',requested=len(symbols))
    def import_csv(self,raw,now=None):
        now=now or datetime.now(IST);rows=parse_csv(raw,now)
        with self._lock:
            if self._thread and self._thread.is_alive():raise ValueError('Wait for the active holdings scan to finish')
            self._save(rows,dict(mode='IMPORTED FILE ONLY — NOT WHOLE MARKET',available=len(rows),finished_at=now.isoformat()))
            self._state=dict(status='IMPORTED',completed=len(rows),requested=len(rows))
        return dict(status='IMPORTED',rows=len(rows))
