"""Content-addressed research snapshots. No imported dataset is training-approved."""
from __future__ import annotations
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import pandas as pd
from insights.config import IST, ROOT
from insights.alpha.research import aware

VERSION = 'research-snapshot-v1'

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

def store_path():
    return ROOT/'research'/'datasets.sqlite'

def prepare(frame, instrument, now, days):
    aware(now)
    if type(days) is not int or not 1 <= days <= 30:
        raise ValueError('Choose 1 to 30 calendar days')
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Timezone-aware Dhan candles required')
    if frame.index.hasnans:raise ValueError('Missing candle timestamps')
    if not {'open','high','low','close','volume'}.issubset(frame.columns):
        raise ValueError('Missing OHLCV columns')
    if len(frame)>20000:
        raise ValueError('Snapshot row limit exceeded')
    identity={k:str(instrument.get(k,'')) for k in ('id','segment','instrument','symbol')}
    if not all(identity[k] for k in ('id','segment','symbol')):
        raise ValueError('Incomplete instrument identity')
    rows=[];rejected=[];forming=0;previous=None;gaps=0
    duplicates=frame.index.duplicated(keep=False)
    for i,(ts,r) in enumerate(frame.iterrows()):
        t=ts.to_pydatetime().astimezone(IST)
        if t+timedelta(minutes=5)>now:
            forming+=1;continue
        if t<now-timedelta(days=days):continue
        minute=t.hour*60+t.minute
        reason=None
        try:values=[float(r[x]) for x in ('open','high','low','close','volume')]
        except (TypeError,ValueError):
            rejected.append({'time':t.isoformat(),'reason':'NON_NUMERIC'});continue
        if duplicates[i]:reason='DUPLICATE_TIMESTAMP'
        elif previous is not None and t<=previous:reason='UNORDERED_TIMESTAMP'
        elif t.weekday()>=5 or not 555<=minute<930 or (minute-555)%5 or t.second or t.microsecond:reason='NON_REGULAR_GRID'
        elif not all(math.isfinite(v) for v in values):reason='NON_FINITE'
        else:
            o,h,l,c,v=values
            if l<=0 or l>min(o,c) or h<max(o,c) or l>h or v<0:reason='INVALID_OHLCV'
            elif v==0:reason='ZERO_VOLUME'
        if previous is not None and previous.date()==t.date() and t>previous+timedelta(minutes=5):
            gaps+=int((t-previous).total_seconds()//300)-1
        previous=max(t,previous) if previous is not None else t
        if reason:
            rejected.append({'time':t.isoformat(),'reason':reason});continue
        rows.append(dict(time=t.isoformat(),closed_at=(t+timedelta(minutes=5)).isoformat(),
                         **dict(zip(('open','high','low','close','volume'),values))))
    manifest=dict(schema=VERSION,source='DHAN',instrument=identity,timeframe='5m',
                  as_of=now.astimezone(IST).isoformat(),requested_days=days,
                  valid_rows=len(rows),quarantined_rows=len(rejected),forming_removed=forming,
                  observed_intraday_gaps=gaps,
                  first=rows[0]['time'] if rows else None,last=rows[-1]['time'] if rows else None,
                  status='RESEARCH_ONLY',training_ready=False,
                  blockers=['Corporate-action adjustment unverified','Point-in-time universe unverified',
                            'Dated circuit/ban/surveillance eligibility unverified',
                            'Exchange holiday and special-session coverage unverified',
                            'Historical costs and instrument tick/lot histories unverified'])
    if rejected or gaps:manifest['blockers'].append('Quarantined candles or observed intraday gaps')
    if not rows:manifest['blockers'].append('No accepted candles')
    return {'manifest':manifest,'rows':rows,'quarantine':rejected}

class DatasetStore:
    def __init__(self,path=None):
        self.path=Path(path) if path is not None else store_path()

    def save(self,payload):
        encoded=canonical(payload);digest=hashlib.sha256(encoded.encode()).hexdigest()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path,timeout=10)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshots (digest TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute("CREATE TRIGGER IF NOT EXISTS no_snapshot_update BEFORE UPDATE ON snapshots BEGIN SELECT RAISE(ABORT,'immutable snapshot'); END")
            db.execute("CREATE TRIGGER IF NOT EXISTS no_snapshot_delete BEFORE DELETE ON snapshots BEGIN SELECT RAISE(ABORT,'immutable snapshot'); END")
            db.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?)',(digest,encoded))
        return dict(payload['manifest'],dataset_id=digest)

    def read(self,digest):
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid dataset ID')
        if not self.path.exists():raise ValueError('Dataset not found')
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            row=db.execute('SELECT payload FROM snapshots WHERE digest=?',(digest,)).fetchone()
        if row is None:raise ValueError('Dataset not found')
        if hashlib.sha256(row[0].encode()).hexdigest()!=digest:raise ValueError('Dataset integrity check failed')
        return json.loads(row[0])

    def inventory(self):
        if not self.path.exists():return []
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            ids=[r[0] for r in db.execute('SELECT digest FROM snapshots ORDER BY rowid DESC LIMIT 30')]
        from insights.alpha.readiness import assess
        result=[]
        for d in ids:
            payload=self.read(d)
            result.append(dict(payload['manifest'],dataset_id=d,readiness=assess(payload)))
        return result


def capture(service,symbol,days,now,store=None):
    if not isinstance(symbol,str) or not 0<len(symbol.strip())<=64:raise ValueError('Provide a mapped stock symbol')
    if type(days) is not int or not 1<=days<=30:raise ValueError('Choose 1 to 30 days')
    if not service._job_lock.acquire(blocking=False):return {'status':'BUSY','message':'Background scan in progress. No snapshot was created.'}
    try:
        item=service._lookup(symbol.strip())
        if not isinstance(item,dict):raise ValueError('Symbol not found in instrument mapping')
        frame=service.broker.history(item,now,minutes=5,lookback_days=days)
        return (store or DatasetStore()).save(prepare(frame,item,now,days))
    finally:service._job_lock.release()
