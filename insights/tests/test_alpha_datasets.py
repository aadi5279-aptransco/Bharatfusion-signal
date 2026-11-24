import unittest
import tempfile
import threading
import hashlib
import sqlite3
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
import pandas as pd
from insights.alpha.datasets import DatasetStore,prepare,capture
from insights.alpha.baselines import Event,evaluate

T=datetime(2026,11,24,12,tzinfo=timezone.utc)
ITEM={'id':'1','segment':'NSE_EQ','instrument':'EQUITY','symbol':'TEST'}
def frame():
    ix=pd.date_range('2026-11-24 09:15',periods=5,freq='5min',tz='Asia/Kolkata')
    return pd.DataFrame(dict(open=100.,high=102.,low=99.,close=101.,volume=10000.),index=ix)

class DatasetTests(unittest.TestCase):
    def test_connections_close_after_save_read_and_inventory(self):
        real_connect=sqlite3.connect;opened=[]
        def tracked(*args,**kwargs):
            db=real_connect(*args,**kwargs);opened.append(db);return db
        with tempfile.TemporaryDirectory() as tmp:
            s=DatasetStore(Path(tmp)/'closed.sqlite')
            with patch('insights.alpha.datasets.sqlite3.connect',side_effect=tracked):
                result=s.save(prepare(frame(),ITEM,T,7))
                s.read(result['dataset_id']);s.inventory()
            self.assertEqual(len(opened),4)
            for db in opened:
                with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
            # Keep references alive: cleanup must not depend on garbage collection.
            s.path.unlink()

    def test_connections_close_on_query_error(self):
        real_connect=sqlite3.connect;opened=[]
        def tracked(*args,**kwargs):
            db=real_connect(*args,**kwargs);opened.append(db);return db
        with tempfile.TemporaryDirectory() as tmp:
            s=DatasetStore(Path(tmp)/'empty.sqlite');s.path.touch()
            with patch('insights.alpha.datasets.sqlite3.connect',side_effect=tracked):
                with self.assertRaises(sqlite3.OperationalError):s.read('a'*64)
                with self.assertRaises(sqlite3.OperationalError):s.inventory()
            for db in opened:
                with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
            s.path.unlink()

    def test_failed_save_rolls_back_and_closes(self):
        real_connect=sqlite3.connect;opened=[]
        class BrokenConnection(sqlite3.Connection):
            def execute(self,sql,*args,**kwargs):
                result=super().execute(sql,*args,**kwargs)
                if sql.startswith('INSERT OR IGNORE'):raise RuntimeError('injected write failure')
                return result
        def tracked(*args,**kwargs):
            db=real_connect(*args,factory=BrokenConnection,**kwargs);opened.append(db);return db
        with tempfile.TemporaryDirectory() as tmp:
            s=DatasetStore(Path(tmp)/'rollback.sqlite')
            with patch('insights.alpha.datasets.sqlite3.connect',side_effect=tracked):
                with self.assertRaises(RuntimeError):s.save(prepare(frame(),ITEM,T,7))
            with self.assertRaises(sqlite3.ProgrammingError):opened[0].execute('SELECT 1')
            self.assertEqual(s.inventory(),[])
            s.path.unlink()

    def test_snapshot_provenance_and_quarantine(self):
        f=frame();f.iloc[1,0]=float('nan');f.iloc[2,4]=0
        p=prepare(f,dict(ITEM,token='never-save'),T,7)
        self.assertEqual(len(p['rows']),3);self.assertEqual(len(p['quarantine']),2)
        self.assertNotIn('token',p['manifest']['instrument'])
        self.assertFalse(p['manifest']['training_ready'])
    def test_forming_bars_not_saved(self):
        p=prepare(frame(),ITEM,frame().index[1].to_pydatetime(),7)
        self.assertEqual(len(p['rows']),1);self.assertEqual(p['manifest']['forming_removed'],4)
    def test_duplicates_and_off_grid(self):
        f=frame();f=pd.concat([f,f.iloc[:1]])
        p=prepare(f,ITEM,T,7)
        self.assertEqual(sum(r['reason']=='DUPLICATE_TIMESTAMP' for r in p['quarantine']),2)
        f=frame();f.index=f.index+pd.Timedelta(minutes=1)
        self.assertEqual(prepare(f,ITEM,T,7)['manifest']['valid_rows'],0)
    def test_store_idempotency_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=DatasetStore(Path(tmp)/'snap.sqlite');p=prepare(frame(),ITEM,T,7)
            a=s.save(p);self.assertEqual(s.save(p),a)
            self.assertEqual(len(s.inventory()),1);self.assertEqual(s.read(a['dataset_id']),p)
            self.assertEqual(len(a['dataset_id']),64)
            with self.assertRaises(ValueError):s.read('../unsafe')
    def test_naive_source_rejected_and_lock_released(self):
        f=frame();f.index=f.index.tz_localize(None)
        with self.assertRaises(ValueError):prepare(f,ITEM,T,7)
        svc=Mock();svc._job_lock=threading.Lock();svc._lookup.return_value=ITEM
        svc.broker.history.side_effect=RuntimeError('secret')
        with self.assertRaises(RuntimeError):capture(svc,'TEST',7,T)
        self.assertFalse(svc._job_lock.locked())
        svc._job_lock.acquire()
        self.assertEqual(capture(svc,'TEST',7,T)['status'],'BUSY');svc._job_lock.release()
    def test_capture_only_explicit_request_and_api_guards(self):
        from insights.api import create_app
        svc=Mock();client=create_app(svc).test_client()
        with patch('insights.alpha.datasets.DatasetStore.inventory',return_value=[]):
            self.assertEqual(client.get('/api/v1/market-insights/model-health').status_code,200)
        svc.broker.history.assert_not_called()
        url='/api/v1/market-insights/research/capture'
        self.assertEqual(client.post(url,json={'symbol':'TEST','days':7},headers={'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(client.post(url,json={'symbol':'TEST'}).status_code,400)
        self.assertEqual(client.post(url,json={'symbol':'TEST','days':True}).status_code,400)
        with patch('insights.alpha.datasets.capture',side_effect=RuntimeError('SECRET_TOKEN')):
            r=client.post(url,json={'symbol':'TEST','days':7})
            self.assertEqual(r.status_code,503);self.assertNotIn('SECRET_TOKEN',r.text)
    def test_capture_saves_mapped_source(self):
        svc=Mock();svc._job_lock=threading.Lock();svc._lookup.return_value=ITEM;svc.broker.history.return_value=frame()
        with tempfile.TemporaryDirectory() as tmp:
            r=capture(svc,'TEST',7,T,DatasetStore(Path(tmp)/'s.sqlite'))
            self.assertEqual(r['valid_rows'],5);self.assertEqual(r['instrument']['id'],'1')

class BaselineTests(unittest.TestCase):
    def events(self):
        return [Event(str(i),T+timedelta(days=i),T+timedelta(days=i),T+timedelta(days=i,hours=1),
                      (float(i%2),float(i%3)),1. if i%2 else -1.) for i in range(100)]
    def test_purged_fold_and_determinism(self):
        events=self.events();cut=T+timedelta(days=85)
        a=evaluate(events,holdout_start=cut,min_train=10,test_size=10)
        self.assertEqual(a,evaluate(events,holdout_start=cut,min_train=10,test_size=10))
        self.assertTrue(a['folds']);self.assertFalse(a['promotion_allowed']);self.assertFalse(a['holdout_evaluated'])
        for f in a['folds']:
            self.assertLess(datetime.fromisoformat(f['train_last_end']),datetime.fromisoformat(f['test_start'])-timedelta(days=1))
    def test_holdout_values_cannot_change_report(self):
        from dataclasses import replace
        events=self.events();cut=T+timedelta(days=85)
        changed=[replace(e,net_r=999,features=(999.,999.)) if e.known_at>=cut else e for e in events]
        self.assertEqual(evaluate(events,holdout_start=cut,min_train=10),evaluate(changed,holdout_start=cut,min_train=10))
    def test_future_features_and_bad_order_rejected(self):
        with self.assertRaises(ValueError):Event('x',T,T+timedelta(seconds=1),T+timedelta(hours=1),(1.,),1.)
        with self.assertRaises(ValueError):evaluate(list(reversed(self.events())),holdout_start=T+timedelta(days=85))
    def test_insufficient_is_not_positive_evidence(self):
        r=evaluate(self.events()[:5],holdout_start=T+timedelta(days=85))
        self.assertEqual(r['status'],'INSUFFICIENT_FOLDS');self.assertIsNone(r['metrics']['logistic']['mean_net_r'])
