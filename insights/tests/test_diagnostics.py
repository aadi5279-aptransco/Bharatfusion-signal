"""Read-only scanner diagnostics and holiday regression."""
import tempfile,unittest
from datetime import datetime
import pandas as pd
from insights.config import IST,is_market_session
from insights.service import InsightsService
from insights.diagnostics import report

class FakeBroker:
 def __init__(self):self.calls=[]
 def configured(self):return True
 def instruments(self):
  self.calls.append('instruments')
  return [dict(kind='index',symbol='NIFTY',id='13',segment='IDX_I',instrument='INDEX'),
          dict(kind='stock',symbol='RELIANCE',id='123',segment='NSE_EQ',instrument='EQUITY')]
 def history(self,item,now=None,minutes=5,oi=False,**kwargs):
  self.calls.append('history')
  idx=pd.date_range('2026-11-09 15:10',periods=3,freq='5min',tz=IST)
  f=pd.DataFrame(dict(open=[100.]*3,high=[101.]*3,low=[99.]*3,
      close=[100.]*3,volume=[1000.]*3),index=idx)
  if oi:f['oi']=[200.]*3
  return f
 def expiry_list(self,item):self.calls.append('expiry_list');return ['2026-11-20']
 def option_chain(self,item,expiry):
  self.calls.append('option_chain')
  return {'oc':{'25000':{'ce':{'oi':100},'pe':{'oi':120}}}}

class ScannerReadinessTests(unittest.TestCase):
 def test_market_holiday_blocks_and_next_day_allowed(self):
  self.assertFalse(is_market_session(datetime(2026,11,10,10,0,tzinfo=IST),set()))
  self.assertTrue(is_market_session(datetime(2026,11,11,10,0,tzinfo=IST),set()))
  self.assertFalse(is_market_session(datetime(2026,11,11,10,0,tzinfo=IST),None))
 def test_cached_preflight_does_not_call_dhan(self):
  with tempfile.TemporaryDirectory() as path:
   broker=FakeBroker();service=InsightsService(broker,path)
   r=report(service,datetime(2026,11,10,10,0,tzinfo=IST))
   self.assertFalse(r['market_session_now'])
   self.assertEqual(broker.calls,[])
   self.assertFalse(r['orders_enabled'])
   self.assertEqual(service.journal.signals(),[])
 def test_explicit_historical_probe_is_read_only(self):
  with tempfile.TemporaryDirectory() as path:
   broker=FakeBroker();service=InsightsService(broker,path)
   r=report(service,datetime(2026,11,10,10,0,tzinfo=IST),probe=True)
   self.assertEqual(r['probes']['nifty_5m']['status'],'PASS')
   self.assertTrue(r['probes']['nifty_5m']['historical_only'])
   self.assertEqual(r['probes']['index_option_chain']['status'],'PASS')
   self.assertEqual(service.journal.signals(),[])
 def test_holiday_scheduler_writes_no_scans(self):
  with tempfile.TemporaryDirectory() as path:
   broker=FakeBroker();service=InsightsService(broker,path)
   self.assertIn('BLOCKED',service.run_due(datetime(2026,11,10,10,0,tzinfo=IST))['status'])
   self.assertEqual(broker.calls,[])
 def test_missing_index_context_is_diagnostic_not_signal(self):
  with tempfile.TemporaryDirectory() as path:
   service=InsightsService(FakeBroker(),path)
   r=service.scan_intraday(datetime(2026,11,11,10,5,tzinfo=IST))
   self.assertEqual(r['data_assessed'],0)
   self.assertEqual(r['signals'],[])
   self.assertIn('NO VERIFIED NIFTY/SECTOR',r['status'])

if __name__=='__main__':unittest.main()
