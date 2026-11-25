"""Explicit, bounded fresh-source comparison; never overwrites a saved snapshot."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import math
from insights.config import IST
from insights.alpha.datasets import DatasetStore
from insights.alpha.readiness import assess, timestamp
from insights.data_layer.history import validate

FIELDS = ('open','high','low','close','volume')

def decode(response, interval, day, as_of):
    raw = response.get('data', response)
    clean, quality = validate(raw, interval, as_of)
    result = {}
    for i, epoch in enumerate(clean['timestamp']):
        t = datetime.fromtimestamp(epoch, IST)
        minute = t.hour*60+t.minute
        if (t.date() != day or t.second or t.microsecond or minute < 555
                or minute+interval > 930 or (minute-555)%interval
                or t+timedelta(minutes=interval) > as_of):
            continue
        result[t] = dict(time=t.isoformat(),
                         closed_at=(t+timedelta(minutes=interval)).isoformat(),
                         **{k:clean[k][i] for k in FIELDS})
    return result, {'received_rows':len(raw.get('timestamp',[])),
                    'usable_rows':len(result),
                    'last_usable':max(result).isoformat() if result else None,
                    'response_sha256':hashlib.sha256(json.dumps(raw,sort_keys=True,default=str).encode()).hexdigest()}

def aggregate(minutes):
    groups = {}
    for t, row in minutes.items():
        start=t-timedelta(minutes=(t.hour*60+t.minute-555)%5)
        groups.setdefault(start,{})[t]=row
    result={}
    for start,group in groups.items():
        times=[start+timedelta(minutes=i) for i in range(5)]
        if not all(t in group for t in times): continue
        rows=[group[t] for t in times]
        volume=sum(r['volume'] for r in rows)
        if volume<=0: continue
        result[start]=dict(time=start.isoformat(),closed_at=(start+timedelta(minutes=5)).isoformat(),
                           open=rows[0]['open'],high=max(r['high'] for r in rows),
                           low=min(r['low'] for r in rows),close=rows[-1]['close'],volume=volume)
    return result

def equal(a,b):
    return all(math.isclose(a[k],b[k],rel_tol=1e-9,abs_tol=1e-8) for k in FIELDS)

def repair(service, dataset_id, now, store=None):
    store = store or DatasetStore()
    old = store.read(dataset_id)
    manifest=old['manifest'];item=manifest['instrument']
    if item.get('segment')!='NSE_EQ' or item.get('instrument')!='EQUITY':
        raise ValueError('Repair currently supports mapped NSE cash equities only')
    as_of=timestamp(manifest['as_of'])
    if now.tzinfo is None or now<as_of: raise ValueError('Invalid repair clock')
    audit=assess(old)
    targets=[s for s in audit['sessions'] if s['missing_regular_bars']>0]
    if not targets:
        return {'status':'NO_COVERAGE_GAPS','message':'No regular-grid gaps to repair. Other provenance gates still apply.'}
    if not service._job_lock.acquire(blocking=False):
        return {'status':'BUSY','message':'Background scan in progress. No repair was performed.'}
    try:
        service.broker._sdk()
        rows={timestamp(r['time']):deepcopy(r) for r in old['rows']}
        original=set(rows);added=[];reports=[];conflicts=0
        start=as_of-timedelta(days=manifest['requested_days'])
        for session in targets[:5]:
            day=datetime.fromisoformat(session['date']).replace(tzinfo=IST)
            request={'securityId':str(item['id']),'exchangeSegment':item['segment'],
                     'instrument':item['instrument'],'oi':False,
                     'fromDate':day.strftime('%Y-%m-%d 00:00:00'),
                     'toDate':(day+timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')}
            sources={};report={'date':session['date'],'before_missing':session['missing_regular_bars'],
                               'requests':[],'added':0,'conflicts':0}
            for interval in (5,1):
                try:
                    response=service.broker.transport.request('POST','/charts/intraday',dict(request,interval=str(interval)))
                    decoded,evidence=decode(response,interval,day.date(),as_of)
                    sources[interval]=decoded
                    report['requests'].append(dict(evidence,interval=interval,status='VALID_RESPONSE'))
                except Exception:
                    report['requests'].append({'interval':interval,'status':'SOURCE_UNAVAILABLE_OR_INVALID'})
            direct={t:r for t,r in sources.get(5,{}).items() if r['volume']>0}
            derived=aggregate(sources.get(1,{}))
            for t in sorted(set(direct)|set(derived)):
                if t<start or t+timedelta(minutes=5)>as_of: continue
                a,b=direct.get(t),derived.get(t)
                if a and b and not equal(a,b):
                    report['conflicts']+=1;continue
                candidate=a or b
                if t in rows:
                    if not equal(rows[t],candidate):report['conflicts']+=1
                    continue
                rows[t]=candidate
                method='FRESH_5M' if a else 'FIVE_COMPLETE_1M_CANDLES'
                added.append({'time':t.isoformat(),'method':method})
                report['added']+=1
            conflicts+=report['conflicts'];reports.append(report)
        payload=deepcopy(old)
        payload['rows']=[rows[t] for t in sorted(rows)]
        added_times=set(rows)-original
        payload['quarantine']=[r for r in old.get('quarantine',[]) if timestamp(r['time']) not in added_times]
        m=payload['manifest']
        m.update(valid_rows=len(rows),quarantined_rows=len(payload['quarantine']),
                 first=min(rows).isoformat() if rows else None,last=max(rows).isoformat() if rows else None,
                 status='RESEARCH_ONLY',training_ready=False)
        m['repair']={'parent_dataset_id':dataset_id,'checked_at':now.astimezone(IST).isoformat(),
                     'cache_bypassed':True,'sessions_attempted':len(reports),
                     'sessions_deferred':max(0,len(targets)-5),'added_rows':len(added),
                     'conflicts':conflicts,'prior_conflicts':manifest.get('repair',{}).get('conflicts',0)+manifest.get('repair',{}).get('prior_conflicts',0),'added_evidence':added,'sessions':reports}
        after=assess(payload)
        m['repair']['remaining_regular_grid_gaps']=sum(s['missing_regular_bars'] for s in after['sessions'])
        m['repair']['outcome']='ROWS_RECOVERED' if added else 'NO_ROWS_RECOVERED'
        saved=store.save(payload)
        return dict(saved,readiness=after)
    finally:
        service._job_lock.release()
