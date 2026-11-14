import tempfile,threading,unittest
from datetime import datetime,date,timedelta
from types import SimpleNamespace
import pandas as pd
from insights.config import IST
from insights.stock_scanner import StockScanner,daily_row,matches,read_metadata,session_date,validate_filters

NOW=datetime(2026,11,13,16,tzinfo=IST)
ITEM=dict(id='1',segment='NSE_EQ',kind='stock',symbol='TEST',ticker='TEST',scanner_fno=True,future={'symbol':'TEST-FUT'})
def frame(n=260):
    idx=pd.bdate_range(end='2026-11-13',periods=n,tz=IST)
    c=pd.Series(range(100,100+n),index=idx,dtype=float)
    return pd.DataFrame(dict(open=c,high=c+1,low=c-1,close=c,volume=1000.))
class Broker:
    def __init__(self):self.calls=0;self.fail=False
    def configured(self):return True
    def instruments(self):return [dict(ITEM,id=str(i),symbol='TEST'+str(i)) for i in range(3)]
    longterm_instruments=instruments
    def daily(self,*a,**k):
        self.calls+=1
        if self.fail:raise ValueError('Unavailable')
        return frame()
class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=Broker();self.s=StockScanner(self.b,self.tmp.name,lambda:set(),threading.Lock(),delay=0)
    def tearDown(self):self.tmp.cleanup()
    def run_batch(self,offset=0,limit=2):
        self.s._run(dict(universe='fno',exchange='NSE',symbols='',offset=offset,limit=limit),NOW)
    def test_completed_only_and_prior_volume(self):
        f=frame();f.iloc[-1,f.columns.get_loc('volume')]=5000
        r=daily_row(f,ITEM,NOW,date(2026,11,13));self.assertEqual(r['rvol'],5)
        r=daily_row(f,ITEM,NOW.replace(hour=10),date(2026,11,12));self.assertEqual(r['asof'],'2026-11-12')
    def test_missing_history_cannot_pass(self):
        r=daily_row(frame(21),ITEM,NOW,None)
        self.assertIsNone(r['sma200']);self.assertIsNone(r['high52'])
        self.assertFalse(matches(r,{'sma200':'above'}));self.assertFalse(matches(r,{'pe_max':20}))
    def test_flat_rsi(self):
        f=frame(30);f[['open','close']]=100.;f['high']=101.;f['low']=99.
        self.assertEqual(daily_row(f,ITEM,NOW,None)['rsi'],50)
    def test_invalid_candles(self):
        f=frame();f.iloc[-1,0]=-1
        with self.assertRaises(ValueError):daily_row(f,ITEM,NOW,None)
    def test_weekend_holiday_calendar(self):
        self.assertEqual(session_date(NOW+timedelta(days=1),set()),date(2026,11,13))
        self.assertEqual(session_date(NOW,{'2026-11-13'}),date(2026,11,12))
        self.assertIsNone(session_date(NOW,None))
    def test_filter_validation(self):
        for f in ({'price_min':10,'price_max':2},{'price_min':'nan'},{'foo':1}):
            with self.assertRaises(ValueError):validate_filters(f)
    def test_batches_accumulate_and_cache(self):
        self.run_batch();self.assertEqual(self.s.snapshot(now=NOW)['loaded'],2)
        self.run_batch(2);self.assertEqual(self.s.snapshot(now=NOW)['loaded'],3)
        self.run_batch();self.assertEqual(self.b.calls,3)
    def test_wrong_continuation_retains(self):
        self.run_batch();self.run_batch(1)
        self.assertEqual(self.s.snapshot(now=NOW)['refresh']['status'],'FAILED')
        self.assertEqual(self.s.snapshot(now=NOW)['loaded'],2)
    def test_failed_refresh_retains(self):
        self.run_batch();self.b.fail=True
        with self.s.connect() as db:db.execute('DELETE FROM scanner_cache')
        self.run_batch();self.assertEqual(self.s.snapshot(now=NOW)['loaded'],2)
        self.assertTrue(self.s.snapshot(now=NOW)['refresh']['previous_retained'])
    def test_metadata_atomic_and_expiry(self):
        raw=b'Exchange,Security ID,As of,Source,PE\nNSE,0,2026-11-13,https://example.com,12\n'
        self.s.import_metadata(raw,NOW);self.run_batch()
        self.assertEqual(self.s.snapshot({'pe_max':20},now=NOW)['total'],1)
        with self.assertRaises(ValueError):self.s.import_metadata(raw.replace(b',12',b',nan'),NOW)
        self.assertEqual(self.s.snapshot({'pe_max':20},now=NOW)['total'],1)
        self.assertEqual(self.s.snapshot({'pe_max':20},now=NOW+timedelta(days=181))['total'],0)
    def test_missing_sort_last_and_paging(self):
        self.run_batch()
        self.s.import_metadata(b'Exchange,Security ID,As of,Source,PE\nNSE,1,2026-11-13,https://example.com,12\n',NOW)
        for order in ('asc','desc'):
            r=self.s.snapshot(sort='pe',order=order,page_size=1,now=NOW)
            self.assertEqual(r['rows'][0]['security_id'],'1');self.assertEqual(r['pages'],2)
    def test_cancel_waiting_lock(self):
        self.s.cancel()
        with self.assertRaises(InterruptedError):self.s._call(lambda:None)
    def test_future_and_duplicate_metadata_rejected(self):
        head=b'Exchange,Security ID,As of,Source\n';r=b'NSE,1,2026-11-13,https://example.com\n'
        for raw in (head+r+r,head+r.replace(b'2026-11-13',b'2027-01-01')):
            with self.assertRaises(ValueError):read_metadata(raw,NOW)
    def test_api_validation_export_and_origin(self):
        import json
        from insights.api import create_app
        client=create_app(SimpleNamespace(stock_scanner=self.s)).test_client()
        base='/api/v1/market-insights/scanner'
        self.assertEqual(client.get(base+'?filters=[]').status_code,400)
        self.assertEqual(client.post(base+'/refresh',json={},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(client.post(base+'/metadata').status_code,400)
        self.run_batch()
        saved=self.s._read('snapshot',{})
        saved['rows'][0]['symbol']='=FORMULA()';self.s._write('snapshot',saved)
        export=client.get(base+'/export',query_string={'filters':json.dumps({'search':'=FORMULA'})})
        self.assertEqual(export.status_code,200)
        self.assertIn("'=FORMULA()",export.text)
        self.assertNotIn('TEST1',export.text)
    def test_installer_copies_scanner_and_preserves_env(self):
        from pathlib import Path
        from tools.install_fii_holdings_update import install
        with tempfile.TemporaryDirectory() as folder:
            source=Path(__file__).resolve().parents[2];target=Path(folder)
            (target/'insights').mkdir();(target/'insights/service.py').write_text('old')
            (target/'web').mkdir();(target/'web/package.json').write_text('{}')
            (target/'.env').write_text('preserve')
            backup=install(source,target)
            self.assertEqual((backup/'insights/service.py').read_text(),'old')
            self.assertTrue((target/'web/src/scanner.js').is_file())
            self.assertEqual((target/'.env').read_text(),'preserve')
