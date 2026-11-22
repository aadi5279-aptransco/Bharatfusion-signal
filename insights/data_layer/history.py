"""Resumable SQLite history chunks with quarantined invalid responses.

SQLite is already shipped by Python; transactions make chunk completion atomic on
Windows. Cached market data contains no credentials. Prices remain AS_REPORTED:
corporate-action adjustments and exchange calendars require independent evidence.
"""
import hashlib,json,math,time,threading
from datetime import datetime,timedelta
import pandas as pd
from insights.config import IST
from .transport import DataError

COLS=('open','high','low','close','volume')
def validate(raw,period,now):
    if not isinstance(raw,dict):raise DataError('History data object missing')
    keys=list(COLS)+['timestamp']
    if not all(isinstance(raw.get(k),list) for k in keys):raise DataError('History arrays missing')
    n=len(raw['timestamp'])
    if not n or any(len(raw[k])!=n for k in keys):raise DataError('Empty or unequal history arrays')
    if 'open_interest' in raw and (not isinstance(raw['open_interest'],list) or len(raw['open_interest'])!=n):raise DataError('Missing or unequal OI array')
    rows={};duplicate=0;forming=0;zero=0;gaps=0
    for i in range(n):
        try:
            t=float(raw['timestamp'][i]);v=[float(raw[k][i]) for k in COLS]
            if not all(math.isfinite(x) for x in [t]+v) or t<=0:raise ValueError()
            stamp=pd.Timestamp(t,unit='s',tz='UTC').tz_convert(IST)
            o,h,l,c,vol=v
            if min(o,h,l,c)<=0 or vol<0 or h<max(o,l,c) or l>min(o,h,c):raise ValueError()
            oi=float(raw['open_interest'][i]) if 'open_interest' in raw else None
            if oi is not None and (not math.isfinite(oi) or oi<0):raise ValueError()
        except (ValueError,TypeError,OverflowError):raise DataError('Invalid timestamp/OHLCV/OI; response quarantined') from None
        complete=(stamp.date()<now.date() or (stamp.date()==now.date() and (now.hour,now.minute)>=(15,40))) if period==1440 else stamp+pd.Timedelta(minutes=period)<=now
        if not complete:forming+=1;continue
        row=v+([oi] if oi is not None else [])
        if t in rows:
            if rows[t]!=row:raise DataError('Conflicting duplicate candles; response quarantined')
            duplicate+=1
        rows[t]=row;zero+=int(vol==0)
    times=sorted(rows)
    for a,b in zip(times,times[1:]):
        aa=pd.Timestamp(a,unit='s',tz='UTC').tz_convert(IST);bb=pd.Timestamp(b,unit='s',tz='UTC').tz_convert(IST)
        if period<1440 and aa.date()==bb.date() and b-a>period*60:gaps+=1
    result={k:[] for k in COLS};result['timestamp']=times
    if 'open_interest' in raw:result['open_interest']=[]
    for t in times:
        for k,v in zip(list(COLS)+(['open_interest'] if 'open_interest' in raw else []),rows[t]):result[k].append(v)
    return result,dict(valid=len(times),identical_duplicates=duplicate,forming_removed=forming,zero_volume=zero,within_day_gaps=gaps,
                       adjustment_status='UNVERIFIED — AS REPORTED BY DHAN',calendar_status='Regular-session checks only; special sessions unverified')

class HistoryStore:
    def __init__(self,transport):
        self.transport=transport;self.lock=threading.RLock();self.last_quality={}
        with transport.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS history_chunks(key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS quarantine(id INTEGER PRIMARY KEY, at TEXT, reason TEXT, request_key TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS data_quality(key TEXT PRIMARY KEY, at TEXT, report TEXT);''');db.commit()
    def fetch(self,path,payload,now=None):
        now=now or datetime.now(IST)
        period=int(payload.get('interval',1440))
        if period not in (1,5,15,25,60,1440):raise DataError('Unsupported Dhan interval')
        start=pd.Timestamp(payload['fromDate']);end=pd.Timestamp(payload['toDate'])
        start=start.tz_localize(IST) if start.tzinfo is None else start.tz_convert(IST)
        end=end.tz_localize(IST) if end.tzinfo is None else end.tz_convert(IST)
        if start>=end or end-start>pd.Timedelta(days=365*30):raise DataError('Invalid history date range')
        # Stable calendar-month partitions: <=31 days, safely below the documented
        # intraday 90-day ceiling. A restart reuses already committed partitions.
        cursor=start.normalize().replace(day=1);all_rows={};has_oi=bool(payload.get('oi'));reports=[]
        anchor=pd.Timestamp(now).normalize()+pd.Timedelta(hours=9,minutes=15)
        cutoff=(anchor+pd.Timedelta(minutes=((pd.Timestamp(now)-anchor).total_seconds()//(period*60))*period)).timestamp() if period<1440 else (pd.Timestamp(now).normalize()-pd.Timedelta(days=int((now.hour,now.minute)<(15,40)))).timestamp()
        with self.lock:
            while cursor<end:
                stop=cursor+pd.offsets.MonthBegin(1)
                stop=min(stop,end)
                request=dict(payload,fromDate=cursor.strftime('%Y-%m-%d' if period==1440 else '%Y-%m-%d %H:%M:%S'),toDate=stop.strftime('%Y-%m-%d' if period==1440 else '%Y-%m-%d %H:%M:%S'))
                identity=dict(payload);identity.pop('fromDate');identity.pop('toDate');identity.update(path=path,month=cursor.strftime('%Y-%m'))
                key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
                with self.transport.db() as db:cached=db.execute('SELECT payload,fetched FROM history_chunks WHERE key=?',(key,)).fetchone()
                cache=json.loads(cached[0]) if cached else None
                # Historical months refresh every day to detect provider corrections.
                covered=cache is not None and pd.Timestamp(cache['until'])>=stop and (stop<now-timedelta(days=2) or cache.get('closed_cutoff',0)>=cutoff)
                if covered and time.time()-cached[1]<(86400 if stop<now-timedelta(days=2) else 45):raw=cache['data'];quality=cache['quality']
                else:
                    if cache and cache['data']['timestamp'] and stop>=now-timedelta(days=2):
                        overlap=pd.Timestamp(cache['data']['timestamp'][-1],unit='s',tz='UTC').tz_convert(IST).normalize()-pd.Timedelta(days=1)
                        request['fromDate']=max(cursor,overlap).strftime('%Y-%m-%d' if period==1440 else '%Y-%m-%d %H:%M:%S')
                    response=self.transport.request('POST',path,request)
                    raw=response.get('data',response)
                    try:
                        raw,quality=validate(raw,period,now)
                        if has_oi and 'open_interest' not in raw:raise DataError('Requested OI unavailable')
                    except DataError as exc:
                        with self.transport.db() as db:
                            db.execute('INSERT INTO quarantine(at,reason,request_key,payload) VALUES(?,?,?,?)',(now.isoformat(),str(exc),key,json.dumps({'response_sha256':hashlib.sha256(json.dumps(raw,default=str).encode()).hexdigest(),'array_lengths':{k:len(v) for k,v in raw.items() if isinstance(v,list)}}) if isinstance(raw,dict) else '{}' ));db.commit()
                        self.last_quality=dict(status='QUARANTINED',reason=str(exc));raise
                    if cache and request['fromDate']!=cursor.strftime('%Y-%m-%d' if period==1440 else '%Y-%m-%d %H:%M:%S'):
                        old=cache['data'];merged={t:[old[k][i] for k in list(COLS)+(['open_interest'] if has_oi else [])] for i,t in enumerate(old['timestamp']) if t<pd.Timestamp(request['fromDate'],tz=IST).timestamp()}
                        merged.update({t:[raw[k][i] for k in list(COLS)+(['open_interest'] if has_oi else [])] for i,t in enumerate(raw['timestamp'])})
                        raw={k:[merged[t][j] for t in sorted(merged)] for j,k in enumerate(list(COLS)+(['open_interest'] if has_oi else []))};raw['timestamp']=sorted(merged)
                    saved=dict(data=raw,until=stop.isoformat(),quality=quality,closed_cutoff=cutoff)
                    with self.transport.db() as db:
                        db.execute('INSERT OR REPLACE INTO history_chunks VALUES(?,?,?)',(key,json.dumps(saved),time.time()))
                        db.execute('INSERT OR REPLACE INTO data_quality VALUES(?,?,?)',(key,now.isoformat(),json.dumps(quality)));db.commit()
                for i,t in enumerate(raw['timestamp']):
                    if start.timestamp()<=t<end.timestamp():all_rows[t]=[raw[k][i] for k in list(COLS)+(['open_interest'] if has_oi else [])]
                reports.append(quality);cursor=cursor+pd.offsets.MonthBegin(1)
        self.last_quality=dict(status='VALIDATED',chunks=len(reports),reports=reports[-3:],adjustment_status='UNVERIFIED',last_bar=pd.Timestamp(max(all_rows),unit='s',tz='UTC').tz_convert(IST).isoformat() if all_rows else None)
        result={k:[all_rows[t][j] for t in sorted(all_rows)] for j,k in enumerate(list(COLS)+(['open_interest'] if has_oi else []))};result['timestamp']=sorted(all_rows)
        return dict(status='success',data=result)
