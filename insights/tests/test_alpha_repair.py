import unittest
import tempfile
import threading
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import Mock,patch
import pandas as pd
from insights.config import IST
from insights.alpha.datasets import DatasetStore,prepare
from insights.alpha.readiness import assess
from insights.alpha.repair import repair,aggregate,decode
from insights.alpha.calendar import published_holiday

NOW=datetime(2026,11,24,20,tzinfo=IST)
DAY=datetime(2026,11,23,9,15,tzinfo=IST)
ITEM={'id':'1','segment':'NSE_EQ','instrument':'EQUITY','symbol':'TEST'}

def raw(interval,n):
    return dict(timestamp=[int((DAY+timedelta(minutes=interval*i)).timestamp()) for i in range(n)],
                open=[100.]*n,high=[102.]*n,low=[99.]*n,close=[101.]*n,volume=[100.*interval]*n)

def payload(n=72):
    ix=pd.date_range(DAY,periods=n,freq='5min')
    return prepare(pd.DataFrame(dict(open=100.,high=102.,low=99.,close=101.,volume=500.),index=ix),ITEM,NOW,2)

def svc(five=72,one=375):
    s=Mock();s._job_lock=threading.Lock()
    s.broker.transport.request.side_effect=lambda method,path,p:raw(int(p['interval']),five if p['interval']=='5' else one)
    return s

class RepairTests(unittest.TestCase):
    def test_holiday_excluded_and_scope_limited(self):
        r=assess(payload())
        day=next(x for x in r['sessions'] if x['date']=='2026-11-24')
        self.assertEqual(day['classification'],'VERIFIED_HOLIDAY')
        self.assertEqual(day['expected_regular_bars'],0)
        self.assertEqual(r['missing_in_observed_sessions'],3)
        self.assertNotIn('2026-11-24',r['weekdays_without_rows'])
        self.assertFalse(published_holiday({'segment':'BSE_EQ'},NOW.date()))
        self.assertFalse(published_holiday(ITEM,NOW.replace(year=2027).date()))

    def test_holiday_rows_are_conflict_not_approved(self):
        p=payload()
        p['rows'].append(dict(p['rows'][0],time=NOW.replace(hour=9,minute=15).isoformat()))
        self.assertEqual(assess(p)['sessions'][-1]['classification'],'HOLIDAY_DATA_CONFLICT')
        self.assertFalse(assess(p)['training_ready'])

    def test_fresh_minute_recovery_preserves_parent_and_bypasses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=DatasetStore(Path(tmp)/'d.sqlite');old=payload();parent=st.save(old)
            service=svc();result=repair(service,parent['dataset_id'],NOW,st)
            self.assertEqual(result['repair']['added_rows'],3)
            self.assertEqual(result['repair']['remaining_regular_grid_gaps'],0)
            self.assertFalse(result['training_ready'])
            self.assertEqual(st.read(parent['dataset_id']),old)
            self.assertEqual(len(st.inventory()),2)
            self.assertEqual(service.broker.transport.request.call_count,2)
            service.broker.history.assert_not_called()
            for call in service.broker.transport.request.call_args_list:
                self.assertEqual(call.args[1],'/charts/intraday')
                self.assertEqual(call.args[2]['fromDate'],'2026-11-23 00:00:00')
                self.assertEqual(call.args[2]['toDate'],'2026-11-24 00:00:00')
            self.assertFalse(service._job_lock.locked())

    def test_incomplete_one_minute_group_never_filled(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=DatasetStore(Path(tmp)/'d.sqlite');parent=st.save(payload())
            result=repair(svc(one=374),parent['dataset_id'],NOW,st)
            self.assertEqual(result['repair']['added_rows'],2)
            self.assertEqual(result['repair']['remaining_regular_grid_gaps'],1)

    def test_direct_five_minute_recovery_when_one_minute_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=DatasetStore(Path(tmp)/'d.sqlite');parent=st.save(payload());service=svc()
            def response(method,path,p):
                if p['interval']=='1':raise RuntimeError('SECRET')
                return raw(5,75)
            service.broker.transport.request.side_effect=response
            result=repair(service,parent['dataset_id'],NOW,st)
            self.assertEqual(result['repair']['added_rows'],3)
            self.assertNotIn('SECRET',str(result))

    def test_source_disagreement_not_silently_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=DatasetStore(Path(tmp)/'d.sqlite');parent=st.save(payload());service=svc()
            def response(method,path,p):
                r=raw(int(p['interval']),75 if p['interval']=='5' else 375)
                if p['interval']=='5':r['close'][-1]=101.5
                return r
            service.broker.transport.request.side_effect=response
            r=repair(service,parent['dataset_id'],NOW,st)
            self.assertEqual(r['repair']['added_rows'],2)
            self.assertEqual(r['repair']['conflicts'],1)
            self.assertEqual(r['readiness']['status'],'COVERAGE_REVIEW')

    def test_source_failure_keeps_gaps_and_sanitizes_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=DatasetStore(Path(tmp)/'d.sqlite');parent=st.save(payload());service=svc()
            service.broker.transport.request.side_effect=RuntimeError('SECRET_TOKEN')
            r=repair(service,parent['dataset_id'],NOW,st)
            self.assertEqual(r['repair']['outcome'],'NO_ROWS_RECOVERED')
            self.assertEqual(r['repair']['remaining_regular_grid_gaps'],3)
            self.assertNotIn('SECRET_TOKEN',str(r));self.assertFalse(service._job_lock.locked())

    def test_busy_and_no_gap_make_no_network_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=DatasetStore(Path(tmp)/'d.sqlite');parent=st.save(payload());service=svc()
            service._job_lock.acquire()
            self.assertEqual(repair(service,parent['dataset_id'],NOW,st)['status'],'BUSY')
            service._job_lock.release()
            full=st.save(payload(75))
            self.assertEqual(repair(service,full['dataset_id'],NOW,st)['status'],'NO_COVERAGE_GAPS')
            service.broker.transport.request.assert_not_called()

    def test_sdk_failure_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            st=DatasetStore(Path(tmp)/'d.sqlite');parent=st.save(payload());service=svc()
            service.broker._sdk.side_effect=RuntimeError('failure')
            with self.assertRaises(RuntimeError):repair(service,parent['dataset_id'],NOW,st)
            self.assertFalse(service._job_lock.locked())

    def test_api_access_validation_and_safe_errors(self):
        from insights.api import create_app
        client=create_app(Mock()).test_client();url='/api/v1/market-insights/research/repair'
        self.assertEqual(client.post(url,json={'dataset_id':'a'*64},headers={'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(client.post(url,json={}).status_code,400)
        with patch('insights.alpha.repair.repair',side_effect=RuntimeError('SECRET')):
            r=client.post(url,json={'dataset_id':'a'*64})
            self.assertEqual(r.status_code,503);self.assertNotIn('SECRET',r.text)
        with patch('insights.alpha.repair.repair',return_value={'status':'BUSY'}):
            self.assertEqual(client.post(url,json={'dataset_id':'a'*64}).json['status'],'BUSY')
