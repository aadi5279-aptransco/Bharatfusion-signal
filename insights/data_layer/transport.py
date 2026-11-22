"""Exact endpoint allow-list, conservative token buckets and durable quota accounting."""
import json,random,sqlite3,threading,time
from pathlib import Path
from datetime import datetime
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError
from insights.config import IST

ALLOWED={('GET','/profile'):'profile',('GET','/RenewToken'):'profile',
 ('POST','/charts/historical'):'data',('POST','/charts/intraday'):'data',
 ('POST','/optionchain'):'chain',('POST','/optionchain/expirylist'):'chain',
 ('POST','/marketfeed/quote'):'quote'}
LIMITS={'data':4.0,'quote':.9,'chain':1/3.1,'profile':2.0}
class DataError(RuntimeError):pass
class ReadOnlyViolation(DataError):pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise DataError('Redirect blocked; credentials were not forwarded')

class Bucket:
    def __init__(self,rate,clock=time.monotonic,sleep=time.sleep):
        self.rate=rate;self.clock=clock;self.sleep=sleep;self.tokens=1.;self.last=clock();self.lock=threading.Lock()
    def acquire(self):
        with self.lock:
            while True:
                now=self.clock();self.tokens=min(1.,self.tokens+(now-self.last)*self.rate);self.last=now
                if self.tokens>=1:self.tokens-=1;return
                self.sleep((1-self.tokens)/self.rate)

_BUCKETS={k:Bucket(v) for k,v in LIMITS.items()}
class Transport:
    def __init__(self,root,credentials,sender=None,buckets=None,sleep=time.sleep):
        self.path=Path(root)/'dhan_data.sqlite';self.path.parent.mkdir(parents=True,exist_ok=True)
        self.credentials=credentials;self.sender=sender or self._send;self.buckets=buckets or _BUCKETS;self.sleep=sleep
        self.last_error='';self.last_success=None
        with self.db() as db:db.execute('CREATE TABLE IF NOT EXISTS quota(day TEXT, category TEXT, requests INTEGER, PRIMARY KEY(day,category))')
    def db(self):
        from contextlib import closing
        # Callers explicitly commit; closing also releases Windows handles.
        return closing(sqlite3.connect(self.path,timeout=20))
    def reserve(self,category):
        day=datetime.now(IST).date().isoformat()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT requests FROM quota WHERE day=? AND category=?',(day,category)).fetchone();n=row[0] if row else 0
            used=db.execute("SELECT COALESCE(SUM(requests),0) FROM quota WHERE day=? AND category IN ('data','chain')",(day,)).fetchone()[0]
            if category in ('data','chain') and used>=100000:raise DataError('Daily data quota reached; retry next IST day')
            db.execute('INSERT INTO quota VALUES(?,?,?) ON CONFLICT(day,category) DO UPDATE SET requests=excluded.requests',(day,category,n+1));db.commit()
    def status(self):
        day=datetime.now(IST).date().isoformat()
        with self.db() as db:counts=dict(db.execute('SELECT category,requests FROM quota WHERE day=?',(day,)))
        return dict(day=day,requests=counts,data_limit=100000,data_requests=counts.get('data',0)+counts.get('chain',0),quota_warning=counts.get('data',0)+counts.get('chain',0)>=80000,
                    quota_scope='This installation only; other applications using this account are not counted',last_error=self.last_error,last_success=self.last_success)
    @staticmethod
    def _send(method,path,payload,headers):
        req=Request('https://api.dhan.co/v2'+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers,method=method)
        with build_opener(NoRedirect()).open(req,timeout=20) as response:
            raw=response.read(20_000_001)
        if len(raw)>20_000_000:raise DataError('Oversized Dhan response')
        try:return json.loads(raw)
        except (ValueError,UnicodeError):raise DataError('Dhan response is not valid JSON') from None
    def request(self,method,path,payload=None):
        # Before credentials, quota, sleep, network or payload interpretation.
        if (method,path) not in ALLOWED:raise ReadOnlyViolation('Blocked non-allow-listed Dhan operation')
        category=ALLOWED[(method,path)]
        client,token=self.credentials()
        if not client or not token:raise DataError('Dhan credentials missing; configure locally')
        headers={'Content-Type':'application/json','Accept':'application/json','access-token':token,'client-id':str(client)}
        for attempt in range(4):
            self.buckets[category].acquire();self.reserve(category)
            try:
                obj=self.sender(method,path,payload,headers)
                if not isinstance(obj,dict):raise DataError('Unexpected Dhan response structure')
                if obj.get('status')=='failure':
                    remarks=obj.get('remarks');code=str(obj.get('errorCode') or (remarks.get('error_code','') if isinstance(remarks,dict) else ''))
                    if code in ('805','DH-805','429'):raise HTTPError('',429,'rate limit',{},None)
                    raise DataError('Dhan rejected request; check token, subscription and instrument mapping')
                self.last_error='';self.last_success=datetime.now(IST).isoformat();return obj
            except HTTPError as exc:
                if exc.code in (401,403):
                    self.last_error='Authentication/entitlement rejected; check token and Data API plan';raise DataError(self.last_error) from None
                retry=exc.code==429 or 500<=exc.code<600
                message=f'Dhan HTTP {exc.code}; no response body or credentials logged'
                header=exc.headers.get('Retry-After','') if exc.headers else ''
                try:delay=min(30,max(0,float(header)))
                except (TypeError,ValueError):delay=0
            except (URLError,TimeoutError,OSError):retry=True;message='Dhan connection timeout/unavailable';delay=0
            except DataError as exc:self.last_error=str(exc);raise
            if not retry or attempt==3:self.last_error=message;raise DataError(message) from None
            self.sleep(max(delay,min(8,2**attempt)+random.uniform(0,.25)))
