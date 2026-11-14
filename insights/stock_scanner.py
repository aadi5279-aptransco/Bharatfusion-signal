"""Indian cash-equity screener. Completed daily candles; never places orders."""
from __future__ import annotations
import csv
import io
import json
import math
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
from insights.config import IST,is_market_session
from insights.brokers.dhan import BrokerUnavailable

NUMERIC=('price','change_pct','volume','avg_volume','rvol','rsi','atr_pct','perf_week','perf_month',
         'perf_quarter','sma20','sma50','sma200','market_cap_cr','pe','roe','debt_equity','dividend_yield')
RANGES=('price','change_pct','avg_volume','rvol','rsi','perf_week','perf_month','market_cap_cr','pe','roe','debt_equity','dividend_yield')
SORT_FIELDS=set(NUMERIC)|{'symbol','company','exchange','sector','asof'}
SIGNALS=('','uptrend','downtrend','breakout20','breakdown20','high_volume','cross20_up','cross20_down')


def session_date(now,holidays):
    if holidays is None:return None
    d=now.date() if (now.hour,now.minute)>=(15,40) else now.date()-timedelta(days=1)
    for _ in range(30):
        if is_market_session(datetime(d.year,d.month,d.day,10,tzinfo=IST),holidays):return d
        d-=timedelta(days=1)
    return None


def finite(value):
    try:x=float(value)
    except (TypeError,ValueError):return None
    return round(x,6) if math.isfinite(x) else None


def daily_row(frame,item,now,expected):
    if not isinstance(frame,pd.DataFrame) or not set(('open','high','low','close','volume')).issubset(frame):
        raise ValueError('Missing OHLCV')
    f=frame[['open','high','low','close','volume']].copy()
    if not isinstance(f.index,pd.DatetimeIndex) or f.index.tz is None:
        raise ValueError('Daily candles require timezone-aware dates')
    f.index=f.index.tz_convert(IST).normalize()
    complete=(now.hour,now.minute)>=(15,40)
    f=f[(f.index.date<now.date())|((f.index.date==now.date())&complete)].sort_index()
    if f.index.has_duplicates or len(f)<21:raise ValueError('Need 21 unique completed daily candles')
    f=f.astype(float)
    if not f.map(lambda x:math.isfinite(x)).all().all():raise ValueError('Nonfinite daily values')
    if (f[['open','high','low','close']]<=0).any().any() or (f.volume<0).any():raise ValueError('Invalid daily prices/volume')
    if (f.high<f[['open','low','close']].max(axis=1)).any() or (f.low>f[['open','high','close']].min(axis=1)).any():
        raise ValueError('Inconsistent OHLC')
    c=f.close;last=f.iloc[-1];prior=f.iloc[-2];p=float(last.close)
    avg=float(f.volume.iloc[-21:-1].mean());d=c.diff()
    gain=d.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean().iloc[-1]
    loss=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean().iloc[-1]
    rsi=50. if gain==loss==0 else 100. if loss==0 else 100.-100./(1+gain/loss)
    tr=pd.concat([f.high-f.low,(f.high-c.shift()).abs(),(f.low-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean().iloc[-1]
    row=dict(key=item['segment']+':'+str(item['id']),security_id=str(item['id']),
        symbol=str(item.get('ticker') or item['symbol']),company=str(item['symbol']),
        exchange='NSE' if item['segment']=='NSE_EQ' else 'BSE',fno=bool(item.get('scanner_fno')),
        price=p,change_pct=(p/float(prior.close)-1)*100,volume=float(last.volume),avg_volume=avg,
        rvol=float(last.volume)/avg if avg>0 else None,rsi=rsi,atr_pct=float(atr)/p*100,
        asof=f.index[-1].date().isoformat(),fetched_at=now.isoformat(),
        freshness='UNKNOWN CALENDAR' if expected is None else 'FRESH' if f.index[-1].date()==expected else 'STALE',
        expected_session=expected.isoformat() if expected else None,source='DHAN COMPLETED DAILY CANDLES')
    for n,label in ((5,'week'),(21,'month'),(63,'quarter')):
        row['perf_'+label]=(p/float(c.iloc[-n-1])-1)*100 if len(c)>n else None
    for n in (20,50,200):
        s=c.rolling(n).mean();value=finite(s.iloc[-1]);previous=finite(s.iloc[-2])
        row['sma'+str(n)]=value
        row['cross'+str(n)+'_up']=bool(value is not None and previous is not None and p>value and float(prior.close)<=previous)
        row['cross'+str(n)+'_down']=bool(value is not None and previous is not None and p<value and float(prior.close)>=previous)
    row['high52']=finite(f.high.iloc[-252:].max()) if len(f)>=252 else None
    row['low52']=finite(f.low.iloc[-252:].min()) if len(f)>=252 else None
    row['breakout20']=p>float(f.high.iloc[-21:-1].max())
    row['breakdown20']=p<float(f.low.iloc[-21:-1].min())
    row['doji']=bool((last.high-last.low)>0 and abs(last.close-last.open)<=.1*(last.high-last.low))
    row['bullish_engulfing']=bool(last.close>last.open and prior.close<prior.open and last.open<=prior.close and last.close>=prior.open)
    for key in set(NUMERIC)|{'high52','low52'}:
        if key in row:row[key]=finite(row[key])
    return row


def validate_filters(filters):
    if not isinstance(filters,dict):raise ValueError('Filters must be an object')
    allowed={'exchange','fno','sector','industry','index','search','signal','freshness','pattern','sma20','sma50','sma200','high52'}
    allowed|={k+'_'+b for k in RANGES for b in ('min','max')}
    if set(filters)-allowed:raise ValueError('Unknown scanner filter')
    out={}
    for key,v in filters.items():
        if v is None or v=='':continue
        if key.endswith(('_min','_max')):
            n=finite(v)
            if n is None:raise ValueError('Invalid numeric filter: '+key)
            out[key]=n
        else:
            if not isinstance(v,str) or len(v)>150:raise ValueError('Invalid text filter')
            out[key]=v
    choices={'exchange':('NSE','BSE'),'fno':('yes','no'),'signal':SIGNALS,'freshness':('fresh','stale'),
             'pattern':('doji','bullish_engulfing'),'high52':('near_high','near_low'),
             **{k:('above','below','cross_up','cross_down') for k in ('sma20','sma50','sma200')}}
    for key,values in choices.items():
        if key in out and out[key] not in values:raise ValueError('Unsupported '+key+' filter')
    for k in RANGES:
        if k+'_min' in out and k+'_max' in out and out[k+'_min']>out[k+'_max']:
            raise ValueError('Minimum exceeds maximum for '+k)
    return out


def matches(row,f):
    if f.get('exchange') and row['exchange']!=f['exchange']:return False
    if f.get('fno') and row['fno']!=(f['fno']=='yes'):return False
    for key in ('sector','industry'):
        if f.get(key) and row.get(key)!=f[key]:return False
    if f.get('index') and f['index'] not in row.get('indices',[]):return False
    if f.get('search') and f['search'].casefold() not in (' '.join(str(row.get(k,'')) for k in ('symbol','company','security_id'))).casefold():return False
    if f.get('freshness') and row['freshness']!=f['freshness'].upper():return False
    for key in RANGES:
        for suffix,cmp in (('_min',lambda a,b:a>=b),('_max',lambda a,b:a<=b)):
            if key+suffix in f:
                if row.get(key) is None or not cmp(row[key],f[key+suffix]):return False
    for n in (20,50,200):
        value=f.get('sma'+str(n));sma=row.get('sma'+str(n))
        if value:
            if sma is None:return False
            if value=='above' and row['price']<=sma:return False
            if value=='below' and row['price']>=sma:return False
            if value.startswith('cross_') and not row.get('cross'+str(n)+'_'+value[6:]):return False
    signal=f.get('signal')
    if signal in ('uptrend','downtrend'):
        values=[row.get(k) for k in ('price','sma20','sma50','sma200')]
        if any(x is None for x in values):return False
        if signal=='uptrend' and not values[0]>values[1]>values[2]>values[3]:return False
        if signal=='downtrend' and not values[0]<values[1]<values[2]<values[3]:return False
    elif signal=='high_volume':
        if row.get('rvol') is None or row['rvol']<2:return False
    elif signal and not row.get(signal):return False
    if f.get('pattern') and not row.get(f['pattern']):return False
    if f.get('high52')=='near_high' and (row.get('high52') is None or row['price']<.95*row['high52']):return False
    if f.get('high52')=='near_low' and (row.get('low52') is None or row['price']>1.05*row['low52']):return False
    return True


def read_metadata(raw,now):
    if not isinstance(raw,bytes) or not 0<len(raw)<=2_000_000:raise ValueError('Metadata CSV must be 1 byte–2 MB')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required={'Exchange','Security ID','As of','Source'}
    if not required.issubset(reader.fieldnames or []):raise ValueError('Required headers: Exchange,Security ID,As of,Source')
    numeric={'Market cap cr':'market_cap_cr','PE':'pe','ROE':'roe','Debt equity':'debt_equity','Dividend yield':'dividend_yield'}
    rows={}
    for line,r in enumerate(reader,2):
        if None in r:raise ValueError('Malformed CSV row '+str(line))
        exchange=(r.get('Exchange') or '').strip().upper();ident=(r.get('Security ID') or '').strip()
        if exchange not in ('NSE','BSE') or not re.fullmatch(r'\d{1,12}',ident):raise ValueError('Invalid exchange/security ID')
        stamp=date.fromisoformat(r.get('As of',''))
        if stamp>now.date() or (now.date()-stamp).days>180:raise ValueError('Metadata date must be within past 180 days')
        source=(r.get('Source') or '').strip()
        if urlparse(source).scheme!='https' or not urlparse(source).hostname:raise ValueError('Provide an HTTPS source URL')
        key=exchange+'_EQ:'+ident
        if key in rows:raise ValueError('Duplicate exchange/security ID')
        obj=dict(metadata_asof=stamp.isoformat(),metadata_source=source)
        for title,keyname in numeric.items():
            value=(r.get(title) or '').strip()
            if not value:obj[keyname]=None;continue
            n=finite(value.replace(',','').removesuffix('%'))
            if n is None or (keyname!='roe' and n<0):raise ValueError('Invalid '+title)
            obj[keyname]=n if keyname!='pe' or n>0 else None
        for title in ('Sector','Industry'):
            val=(r.get(title) or '').strip()
            if len(val)>100:raise ValueError('Metadata label too long')
            obj[title.lower()]=val or None
        obj['indices']=[v.strip() for v in (r.get('Indices') or '').split('|') if v.strip()]
        if len(obj['indices'])>20 or any(len(x)>100 for x in obj['indices']):raise ValueError('Too many/long index labels')
        rows[key]=obj
        if len(rows)>10000:raise ValueError('At most 10,000 metadata rows')
    if not rows:raise ValueError('No metadata rows')
    return rows


class StockScanner:
    def __init__(self,broker,root,holidays,job_lock,delay=.4):
        self.broker=broker;self.holidays=holidays;self.job_lock=job_lock;self.delay=delay
        self.path=Path(root)/'stock_scanner.sqlite';self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock();self._thread=None;self._cancel=threading.Event();self._last_start=0
        self._state=dict(status='IDLE',completed=0,requested=0)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS scanner_state (name TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS scanner_cache (key TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=8)
        try:
            with db:yield db
        finally:db.close()
    def _read(self,name,default):
        with self.connect() as db:r=db.execute('SELECT payload FROM scanner_state WHERE name=?',(name,)).fetchone()
        return json.loads(r[0]) if r else default
    def _write(self,name,payload):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO scanner_state VALUES(?,?)',(name,json.dumps(payload,allow_nan=False)))
    def import_metadata(self,raw,now=None):
        rows=read_metadata(raw,now or datetime.now(IST));self._write('metadata',rows)
        return dict(status='IMPORTED',rows=len(rows))
    def snapshot(self,filters=None,sort='symbol',order='asc',page=1,page_size=50,now=None):
        now=now or datetime.now(IST);f=validate_filters({} if filters is None else filters)
        if sort not in SORT_FIELDS or order not in ('asc','desc'):raise ValueError('Unsupported sort')
        if not 1<=page<=10000 or not 1<=page_size<=10000:raise ValueError('Invalid pagination')
        saved=self._read('snapshot',dict(rows=[],coverage={}))
        metadata=self._read('metadata',{});rows=saved['rows'];expected=session_date(now,self.holidays())
        facets={k:set() for k in ('sector','industry','index')};meta_count=0
        for r in rows:
            r['freshness']='UNKNOWN CALENDAR' if expected is None else 'FRESH' if r['asof']==expected.isoformat() else 'STALE'
            r['expected_session']=expected.isoformat() if expected else None
            m=metadata.get(r['key'])
            if m and 0<=(now.date()-date.fromisoformat(m['metadata_asof'])).days<=180:
                r.update(m);meta_count+=1
            for key in ('sector','industry'):
                if r.get(key):facets[key].add(r[key])
            facets['index'].update(r.get('indices',[]))
        matches_rows=[r for r in rows if matches(r,f)]
        present=[r for r in matches_rows if r.get(sort) is not None]
        missing=[r for r in matches_rows if r.get(sort) is None]
        present.sort(key=lambda r:r[sort].casefold() if isinstance(r[sort],str) else r[sort],reverse=order=='desc')
        ordered=present+missing
        pages=max(1,math.ceil(len(ordered)/page_size));page=min(page,pages)
        with self._lock:state=dict(self._state)
        return dict(rows=ordered[(page-1)*page_size:page*page_size],total=len(ordered),loaded=len(rows),
            page=page,pages=pages,page_size=page_size,refresh=state,coverage=saved['coverage'],
            facets={k:sorted(v) for k,v in facets.items()},metadata_covered=meta_count,
            note='Completed daily sessions only; filters apply to loaded batches, not the entire exchange. Fundamentals are dated user imports. No orders.')
    def start(self,settings,now=None):
        if not isinstance(settings,dict) or set(settings)-{'universe','exchange','offset','limit','symbols'}:raise ValueError('Invalid scan settings')
        universe=settings.get('universe','fno');exchange=settings.get('exchange','NSE')
        if universe not in ('fno','all') or exchange not in ('NSE','BSE','ALL'):raise ValueError('Invalid universe/exchange')
        try:offset=int(settings.get('offset',0));limit=int(settings.get('limit',100))
        except (ValueError,TypeError):raise ValueError('Offset/batch size must be integers') from None
        if not 0<=offset<=10000 or not 1<=limit<=500:raise ValueError('Batch size 1–500; offset 0–10000')
        symbols=settings.get('symbols','')
        if not isinstance(symbols,str) or len(symbols)>5000:raise ValueError('Invalid symbol list')
        if not self.broker.configured():return dict(status='UNAVAILABLE',error='Configure Dhan credentials first')
        with self._lock:
            if self._thread and self._thread.is_alive():return dict(status='BUSY',error='A scanner batch is running')
            if self._last_start and time.monotonic()-self._last_start<5:return dict(status='RATE_LIMITED',error='Wait five seconds between batches')
            self._last_start=time.monotonic();self._cancel.clear()
            opts=dict(universe=universe,exchange=exchange,offset=offset,limit=limit,symbols=symbols)
            self._state=dict(status='RUNNING',completed=0,requested=0,settings=opts)
            self._thread=threading.Thread(target=self._run,args=(opts,now or datetime.now(IST)),daemon=True,name='StockScanner')
            self._thread.start()
        return dict(status='STARTED')
    def cancel(self):
        self._cancel.set();return dict(status='CANCEL_REQUESTED')
    def _call(self,fn):
        # Serialize each broker request with existing service jobs, not the
        # whole batch; scheduled scans get opportunities between requests.
        while not self._cancel.is_set():
            if self.job_lock.acquire(timeout=.2):
                try:return fn()
                finally:self.job_lock.release()
        raise InterruptedError('Cancelled')
    def _run(self,opts,now):
        try:
            mapped=self._call(self.broker.instruments)
            fno={x['segment']+':'+str(x['id']) for x in mapped if x.get('kind')=='stock' and (x.get('future') or x.get('options'))}
            items=(self._call(self.broker.longterm_instruments) if opts['universe']=='all' else mapped)
            selected={x.strip().upper() for x in opts['symbols'].split(',') if x.strip()}
            clean={}
            for x in items:
                if x.get('kind')!='stock' or x.get('segment') not in ('NSE_EQ','BSE_EQ'):continue
                key=x['segment']+':'+str(x['id']);is_fno=key in fno
                if opts['universe']=='fno' and not is_fno:continue
                if opts['exchange']!='ALL' and x['segment']!=opts['exchange']+'_EQ':continue
                aliases={str(x.get(k,'')).upper() for k in ('symbol','ticker','id')}
                if x.get('future'):aliases.add(str(x['future'].get('symbol','')).split('-')[0].upper())
                if selected and not selected.intersection(aliases):continue
                clean[key]=dict(x,scanner_fno=is_fno)
            universe=sorted(clean.values(),key=lambda x:(str(x.get('ticker') or x['symbol']),x['segment'],str(x['id'])))
            batch=universe[opts['offset']:opts['offset']+opts['limit']]
            expected=session_date(now,self.holidays());signature={k:v for k,v in opts.items() if k not in ('offset','limit')}
            saved=self._read('snapshot',dict(rows=[],coverage={}))
            same=(saved['coverage'].get('selection')==signature and saved['coverage'].get('analysis_date')==now.date().isoformat())
            if opts['offset'] and (not same or saved['coverage'].get('next_offset')!=opts['offset']):
                raise ValueError('Universe changed or batch is out of sequence; start a fresh scan')
            rows={r['key']:r for r in saved['rows']} if opts['offset'] else {}
            failures=list(saved['coverage'].get('failures',[])) if opts['offset'] else [];cached=0;completed=0;consecutive_errors=0
            with self._lock:self._state.update(requested=len(batch),universe=len(universe))
            for item in batch:
                if self._cancel.is_set():break
                key=item['segment']+':'+str(item['id'])
                try:
                    with self.connect() as db:record=db.execute('SELECT payload FROM scanner_cache WHERE key=?',(key,)).fetchone()
                    row=json.loads(record[0]) if record else None
                    if row and expected and row['asof']==expected.isoformat():
                        cached+=1;row['fno']=item['scanner_fno']
                    else:
                        frame=self._call(lambda:self.broker.daily(item,now,days=550))
                        row=daily_row(frame,item,now,expected)
                        with self.connect() as db:db.execute('INSERT OR REPLACE INTO scanner_cache VALUES(?,?)',(key,json.dumps(row,allow_nan=False)))
                        if self.delay:self._cancel.wait(self.delay)
                    rows[key]=row;consecutive_errors=0
                except InterruptedError:break
                except (BrokerUnavailable,ValueError,TypeError,KeyError,OSError) as exc:
                    failures.append(dict(symbol=item['symbol'],error=str(exc)[:180]));consecutive_errors+=1
                completed+=1
                with self._lock:self._state.update(completed=completed,current_symbol=item['symbol'],available=len(rows))
                if consecutive_errors>=3:break
            coverage=dict(selection=signature,analysis_date=now.date().isoformat(),available_master=len(universe),
                batch_offset=opts['offset'],batch_requested=len(batch),batch_completed=completed,loaded=len(rows),cached=cached,
                next_offset=min(len(universe),opts['offset']+completed),has_more=opts['offset']+completed<len(universe),
                failures=failures,saved_at=now.isoformat(),source='DHAN DAILY')
            # Preserve a previous result on total source failure; a successful
            # empty universe explicitly replaces it to avoid stale confusion.
            if rows or not batch:self._write('snapshot',dict(rows=list(rows.values()),coverage=coverage))
            status='CANCELLED' if self._cancel.is_set() else 'SOURCE ERRORS — STOPPED' if consecutive_errors>=3 else 'COMPLETE'
            with self._lock:self._state.update(status=status,coverage=coverage,previous_retained=bool(batch and not rows))
        except InterruptedError:
            with self._lock:self._state.update(status='CANCELLED')
        except Exception as exc:
            with self._lock:self._state.update(status='FAILED',error=str(exc)[:180])
