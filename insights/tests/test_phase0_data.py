"""Offline fault-injection tests. These are NOT real-Dhan evidence."""
import tempfile,unittest,json
from unittest.mock import Mock
from urllib.error import HTTPError,URLError
from datetime import datetime
import pandas as pd
from insights.config import IST
from insights.data_layer.transport import Transport,Bucket,DataError,ReadOnlyViolation,ALLOWED
from insights.data_layer.history import HistoryStore,validate
from insights.data_layer.client import Client

NOW=datetime(2026,11,16,10,30,tzinfo=IST)
def raw(stamp='2026-11-16 10:20'):
    return dict(open=[100],high=[101],low=[99],close=[100],volume=[0],timestamp=[int(pd.Timestamp(stamp,tz=IST).timestamp())])
def transport(root,sender):return Transport(root,lambda:('fixture-client','fixture-token'),sender=sender,buckets={k:Mock() for k in ('data','quote','chain','profile')},sleep=Mock())
class Tests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.sender=Mock(return_value={'status':'success','data':raw()});self.t=transport(self.tmp.name,self.sender)
    def tearDown(self):self.tmp.cleanup()
    def test_non_allowlisted_endpoints_block_before_network(self):
        for path in ('/orders','/orders/1','/super/orders','/forever/orders','/killswitch','/positions/convert','https://other.test/profile','/profile?x=y','/charts/../orders'):
            for method in ('GET','POST','PUT','DELETE'):
                with self.assertRaises(ReadOnlyViolation):self.t.request(method,path,{})
        self.sender.assert_not_called();self.assertEqual(self.t.status()['requests'],{})
    def test_sdk_facade_cannot_submit_modify_cancel(self):
        c=Client(self.t)
        for name in ('place_order','modify_order','cancel_order','kill_switch','super_order'):
            with self.assertRaises(ReadOnlyViolation):getattr(c,name)
    def test_retries_count_every_attempt(self):
        self.sender.side_effect=[HTTPError('',429,'',{},None),HTTPError('',503,'',{},None),{'data':raw()}]
        self.t.request('POST','/charts/intraday',{})
        self.assertEqual(self.t.status()['requests']['data'],3);self.assertEqual(self.t.sleep.call_count,2)
    def test_auth_error_not_retried_or_leaked(self):
        self.sender.side_effect=HTTPError('https://secret',401,'fixture-token',{},None)
        with self.assertRaises(DataError) as e:self.t.request('GET','/profile')
        self.assertNotIn('fixture-token',str(e.exception));self.assertEqual(self.sender.call_count,1)
    def test_timeout_bounded(self):
        self.sender.side_effect=URLError('fixture-token')
        with self.assertRaises(DataError) as e:self.t.request('GET','/profile')
        self.assertNotIn('fixture-token',str(e.exception));self.assertEqual(self.sender.call_count,4)
    def test_quota_survives_restart_and_blocks_at_limit(self):
        day=datetime.now(IST).date().isoformat()
        with self.t.db() as db:db.execute('INSERT INTO quota VALUES(?,?,?)',(day,'data',100000));db.commit()
        t=transport(self.tmp.name,self.sender);self.assertTrue(t.status()['quota_warning'])
        with self.assertRaises(DataError):t.request('POST','/charts/intraday',{})
        self.sender.assert_not_called()
    def test_missing_credentials_no_network(self):
        self.t.credentials=lambda:('','')
        with self.assertRaises(DataError):self.t.request('GET','/profile')
        self.sender.assert_not_called()
    def test_bucket_no_burst(self):
        times=[0.];sleeps=[]
        def sleep(s):sleeps.append(s);times[0]+=s
        b=Bucket(4,clock=lambda:times[0],sleep=sleep)
        for _ in range(6):b.acquire()
        self.assertAlmostEqual(times[0],1.25);self.assertEqual(len(sleeps),5)
    def test_timestamp_zero_volume_and_completed_candle(self):
        r,q=validate(raw(),5,NOW);self.assertEqual(q['zero_volume'],1);self.assertEqual(q['valid'],1)
        self.assertEqual(pd.Timestamp(r['timestamp'][0],unit='s',tz='UTC').tz_convert(IST).hour,10)
        r,q=validate(raw('2026-11-16 10:30'),5,NOW);self.assertFalse(r['timestamp']);self.assertEqual(q['forming_removed'],1)
    def test_bad_arrays_ohlc_and_nonfinite(self):
        for r in [dict(raw(),high=[98]),dict(raw(),volume=[-1]),dict(raw(),close=[float('inf')]),dict(raw(),timestamp=[]),dict(raw(),open_interest=[-1]),dict(raw(),open_interest=None),dict(raw(),open_interest=42)]:
            with self.assertRaises(DataError):validate(r,5,NOW)
    def test_duplicates_identical_and_conflicting(self):
        r={k:v*2 for k,v in raw().items()};got,q=validate(r,5,NOW);self.assertEqual(q['identical_duplicates'],1)
        r['close'][1]=100.5
        with self.assertRaises(DataError):validate(r,5,NOW)
    def test_forming_daily(self):
        self.assertEqual(validate(raw('2026-11-16 00:00'),1440,NOW)[1]['forming_removed'],1)
    def test_quarantine_not_cached_or_secret_logged(self):
        self.sender.return_value={'data':dict(raw(),close=['fixture-token'])};h=HistoryStore(self.t)
        with self.assertRaises(DataError):h.fetch('/charts/intraday',self.payload(),NOW)
        with self.t.db() as db:
            rows=db.execute('SELECT payload FROM quarantine').fetchall();self.assertEqual(len(rows),1)
            self.assertNotIn('fixture-token',str(rows));self.assertEqual(db.execute('SELECT count(*) FROM history_chunks').fetchone()[0],0)
    def payload(self):return dict(securityId='fixture-id',exchangeSegment='NSE_EQ',instrument='EQUITY',fromDate='2026-11-16 09:15:00',toDate='2026-11-16 10:30:00',interval='5',oi=False)
    def test_restart_reuses_validated_chunk(self):
        h=HistoryStore(self.t);a=h.fetch('/charts/intraday',self.payload(),NOW)
        b=HistoryStore(self.t).fetch('/charts/intraday',self.payload(),NOW)
        self.assertEqual(a,b);self.assertEqual(self.sender.call_count,1)
    def test_month_chunks_bounded_and_resume_failed_batch(self):
        p=dict(self.payload(),fromDate='2026-07-01 00:00:00')
        self.sender.side_effect=[{'data':raw('2026-07-02 10:20')},DataError('interrupted')]
        h=HistoryStore(self.t)
        with self.assertRaises(DataError):h.fetch('/charts/intraday',p,NOW)
        def response(method,path,payload,headers):
            start=pd.Timestamp(payload['fromDate']);end=pd.Timestamp(payload['toDate'])
            self.assertLessEqual((end-start).days,31)
            return {'data':raw((start+pd.Timedelta(days=1,hours=10,minutes=20)).strftime('%Y-%m-%d %H:%M'))}
        self.sender.side_effect=response;self.sender.reset_mock();h.fetch('/charts/intraday',p,NOW)
        self.assertEqual(self.sender.call_count,4) # July survived, August-November fetched.
    def test_unsupported_interval_rejected(self):
        with self.assertRaises(DataError):HistoryStore(self.t).fetch('/charts/intraday',dict(self.payload(),interval='3'),NOW)
        self.sender.assert_not_called()
    def test_read_facade_payload_schema(self):
        c=Client(self.t);c.expiry_list(123,'IDX_I');self.assertEqual(self.sender.call_args.args[2],dict(UnderlyingScrip=123,UnderlyingSeg='IDX_I'))

class BoundaryAndMasterTests(unittest.TestCase):
    def test_history_does_not_reuse_previous_closed_bucket(self):
        with tempfile.TemporaryDirectory() as root:
            send=Mock(side_effect=[{'data':raw('2026-11-16 10:20')},{'data':raw('2026-11-16 10:25')}]);t=transport(root,send);h=HistoryStore(t)
            payload=dict(securityId='fixture-id',exchangeSegment='IDX_I',instrument='INDEX',interval='5',oi=False,fromDate='2026-11-16 09:15:00',toDate='2026-11-16 10:29:00')
            h.fetch('/charts/intraday',payload,NOW.replace(minute=29))
            out=h.fetch('/charts/intraday',dict(payload,toDate='2026-11-16 10:30:00'),NOW)
            self.assertEqual(send.call_count,2);self.assertEqual(out['data']['timestamp'][-1],raw('2026-11-16 10:25')['timestamp'][0])
    def test_profile_status_never_returns_account_or_token(self):
        from insights.brokers.dhan import DhanReadOnly
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root,patch('insights.brokers.dhan.ROOT',root):
            b=DhanReadOnly('fixture-client','fixture-token');b.transport.request=Mock(return_value=dict(dataPlan='Active',dhanClientId='fixture-client',accessToken='fixture-token',tokenValidity='expiry'))
            result=b.check_profile();self.assertNotIn('fixture-client',json.dumps(result));self.assertNotIn('fixture-token',json.dumps(result))
    def test_master_reuses_valid_official_payload(self):
        from insights.data_layer.master import Master
        from unittest.mock import patch
        payload=b'EXCH_ID,SEGMENT,INSTRUMENT,SECURITY_ID,UNDERLYING_SECURITY_ID,SYMBOL_NAME,SERIES\nNSE,E,EQUITY,fixture-id,,Fixture,EQ\n'
        with tempfile.TemporaryDirectory() as root:
            t=transport(root,Mock());m=Master(t)
            context=Mock();context.__enter__=Mock(return_value=Mock(read=Mock(return_value=payload)));context.__exit__=Mock(return_value=False)
            opener=Mock();opener.open.return_value=context
            with patch('insights.data_layer.master.build_opener',return_value=opener):
                self.assertEqual(len(m.load()),1);self.assertEqual(len(m.load()),1);opener.open.assert_called_once()
