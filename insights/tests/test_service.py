import tempfile,unittest
from datetime import datetime
from pathlib import Path
import pandas as pd
from insights.config import IST
from insights.service import InsightsService
from insights.brokers.dhan import DhanReadOnly


class FakeBroker:
 def configured(self):return True
 def instruments(self):return [dict(kind='index',symbol='NIFTY',segment='IDX_I',id='13',instrument='INDEX'),dict(kind='stock',symbol='RELIANCE',segment='NSE_EQ',id='123',instrument='EQUITY')]
 def expiry_list(self,item):return ['2026-11-20']
 def option_chain(self,item,expiry):
  return {'last_price':100,'oc':{'100':{
      'ce':{'oi':100,'previous_oi':80,'top_ask_price':10,'top_bid_price':9.9,'volume':10,'security_id':'2026'},
      'pe':{'oi':200,'previous_oi':190,'top_ask_price':10,'top_bid_price':9.9,'volume':10,'security_id':'2027'}}}}
 def history(self,item,now,minutes=5,lookback_days=6,oi=False):
  # Prices are deliberately fixture-only; production never creates synthetic candles.
  idx=pd.date_range('2026-11-09 10:05',periods=3,freq='5min',tz=IST)
  return pd.DataFrame(dict(open=[100,101,102],high=[102,105,106],low=[99,100,102],close=[101,104,105],volume=[500,500,500]),index=idx)

class ServiceTests(unittest.TestCase):
 def test_dashboard_uses_last_completed_historical_session(self):
  with tempfile.TemporaryDirectory() as d:
   service=InsightsService(FakeBroker(),d)
   result=service.dashboard(datetime(2026,11,10,21,0,tzinfo=IST))
   self.assertEqual(result['status'],'HISTORICAL SNAPSHOT — NOT LIVE')
   self.assertEqual(result['session_date'],'2026-11-09')
   self.assertTrue(result['not_live'])
   self.assertEqual(result['source'],'DHAN COMPLETED CANDLES')
   self.assertEqual(result['indices'][0]['session_date'],'2026-11-09')
 def test_manual_refresh_runs_without_starting_orders(self):
  with tempfile.TemporaryDirectory() as d:
   service=InsightsService(FakeBroker(),d)
   result=service.request_dashboard_refresh(datetime(2026,11,10,21,0,tzinfo=IST))
   self.assertEqual(result['status'],'STARTED')
   service._manual_thread.join(timeout=5)
   self.assertFalse(service._manual_thread.is_alive())
   health=service.health()
   self.assertEqual(health['manual_refresh']['status'],'SUCCEEDED')
   self.assertIn('dashboard',health['updated_at'])
   self.assertEqual(service.request_dashboard_refresh()['status'],'RATE_LIMITED')
   self.assertFalse(health['orders_enabled'])
 def test_manual_refresh_endpoint_is_read_only(self):
  with tempfile.TemporaryDirectory() as d:
   from insights.api import create_app
   service=InsightsService(FakeBroker(),d)
   client=create_app(service).test_client()
   response=client.post('/api/v1/market-insights/dashboard/refresh')
   self.assertEqual(response.status_code,202)
   service._manual_thread.join(timeout=5)
   self.assertEqual(client.get('/api/v1/health').json['manual_refresh']['status'],'SUCCEEDED')
   self.assertEqual(client.get('/api/v1/market-insights/dashboard').json['not_live'],True)
   self.assertEqual(client.get('/api/v1/health').json['orders_enabled'],False)
 def test_health_has_no_token(self):
  with tempfile.TemporaryDirectory() as d:
   s=InsightsService(FakeBroker(),d)
   self.assertTrue(s.health()['read_only'])
   self.assertNotIn('access_token',str(s.health()))
 def test_option_analyse_reports_missing_validity_without_fabrication(self):
  with tempfile.TemporaryDirectory() as d:
   s=InsightsService(FakeBroker(),d)
   r=s.analyse('NIFTY',datetime(2026,11,9,10,0,tzinfo=IST))
   self.assertEqual(r['metrics']['iv_percentile'],None)
   self.assertEqual(r['metrics']['pcr'],2)
   self.assertEqual(r['status'].split(' ')[0],'RESEARCH')
   self.assertEqual(r['analysis']['status'].split(' ')[0],'UNAVAILABLE')
   self.assertIsNone(r['entry_plan'])
   self.assertIsNone(r['probability_of_win'])
 def test_recorded_stop_before_target_in_same_bar(self):
  with tempfile.TemporaryDirectory() as d:
   b=FakeBroker();s=InsightsService(b,d)
   k=dict(strategy='x',version='1',symbol='RELIANCE',direction='BUY',signal_at='2026-11-09T10:00:00+05:30',entry=100,sl=99,t1=102,t2=103,rr=2,confidence=80,reasons=['test'],instrument_id='123',segment='NSE_EQ',instrument_type='EQUITY')
   s.journal.record(k)
   self.assertEqual(s.reconcile_outcomes(datetime(2026,11,9,10,30,tzinfo=IST)),1)
   self.assertEqual(s.journal.signals()[0]['status'],'SL')
 def test_unsupported_instrument_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   s=InsightsService(FakeBroker(),d)
   with self.assertRaises(ValueError):s.analyse('NOT_A_DHAN_INSTRUMENT',datetime(2026,11,9,10,0,tzinfo=IST))

if __name__=='__main__':unittest.main()
