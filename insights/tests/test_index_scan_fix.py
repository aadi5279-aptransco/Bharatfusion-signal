import tempfile,unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import pandas as pd
from insights.config import IST
from insights.service import InsightsService
from insights.brokers.dhan import BrokerUnavailable
from insights.strategies import opening_redbar
from insights.tests.test_opening_redbar import sample
class IndexFixTests(unittest.TestCase):
    def test_utc_candles_same_redbar_result(self):
        f=sample(reds=True);now=pd.Timestamp('2026-11-12 09:35',tz=IST)
        expected=opening_redbar.evaluate(f,now)[1];f.index=f.index.tz_convert('UTC')
        actual=opening_redbar.evaluate(f,now.tz_convert('UTC'))[1]
        self.assertEqual(actual['state'],'DIRECTION_READY');self.assertEqual(actual['spot_entry'],expected['spot_entry'])
    def test_old_intraday_candles_not_new_signal(self):
        f=sample(reds=True).iloc[:4];r=opening_redbar.evaluate(f,pd.Timestamp('2026-11-12 10:15',tz=IST))
        self.assertTrue(all(x['state']!='DIRECTION_READY' for x in r))
    def test_waiting_shows_count_and_last_closes(self):
        r=opening_redbar.evaluate(sample(reds=True),pd.Timestamp('2026-11-12 09:30',tz=IST))[1]
        self.assertEqual(r['confirmation_bars'],1);self.assertEqual(len(r['last_two_closes']),1)
    def test_index_source_failure_does_not_hide_other_indices(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[]
            def history(item,*a,**k):
                calls.append(item['symbol'])
                if item['symbol']=='BANKNIFTY':raise BrokerUnavailable('Source error')
                f=sample(reds=True);f.index=f.index.tz_convert('UTC');return f
            b=SimpleNamespace(history=history,expiry_list=lambda _:[])
            s=InsightsService(b,root);s.instruments=lambda:[dict(symbol=x,kind='index') for x in ('NIFTY','BANKNIFTY')];s._fib_setups=Mock(return_value=[])
            s.scan_index_options(pd.Timestamp('2026-11-12 09:35',tz=IST).to_pydatetime());r=s.snapshot('index-options')
            self.assertEqual(calls,['NIFTY','BANKNIFTY']);self.assertTrue(any(x['state']=='DIRECTION_READY' for x in r['opening_setups'] if x['underlying']=='NIFTY'))
            self.assertTrue(any(x['state']=='DATA_UNAVAILABLE' for x in r['opening_setups'] if x['underlying']=='BANKNIFTY'));self.assertTrue(any('SENSEX' in x for x in r['scan_issues']))
    def test_scheduler_catches_non_boundary_and_prioritizes_indices(self):
        with tempfile.TemporaryDirectory() as root:
            s=InsightsService(SimpleNamespace(),root);order=[]
            for name in ('dashboard','scan_intraday','scan_fo','scan_swing_shortlist','scan_btst','scan_btst_closing','reconcile_outcomes'):
                setattr(s,name,Mock(return_value={}))
            s.scan_index_options=Mock(side_effect=lambda _:order.append('index'))
            s.refresh_liquidity=Mock(side_effect=lambda _:order.append('liquidity'))
            with patch('insights.service._holiday_set',return_value=set()):
                for clock in ('09:46','09:47','09:51'):s.run_due(pd.Timestamp('2026-11-12 '+clock,tz=IST).to_pydatetime())
            self.assertEqual(s.scan_index_options.call_count,2);self.assertEqual(order[:2],['index','liquidity'])
    def test_failed_bucket_is_retried(self):
        with tempfile.TemporaryDirectory() as root:
            s=InsightsService(SimpleNamespace(),root);s.dashboard=Mock(return_value={});s.scan_index_options=Mock(side_effect=[BrokerUnavailable('fail'),[]]);s.reconcile_outcomes=Mock()
            with patch('insights.service._holiday_set',return_value=set()):
                s.run_due(pd.Timestamp('2026-11-12 09:31',tz=IST).to_pydatetime());s.run_due(pd.Timestamp('2026-11-12 09:32',tz=IST).to_pydatetime())
            self.assertEqual(s.scan_index_options.call_count,2)
    def test_manual_refresh_api_local_only(self):
        from insights.api import create_app
        s=SimpleNamespace(request_index_refresh=Mock(return_value={'status':'STARTED'}));client=create_app(s).test_client()
        self.assertEqual(client.post('/api/v1/market-insights/index-options/refresh').status_code,202)
        self.assertEqual(client.post('/api/v1/market-insights/index-options/refresh',environ_overrides={'REMOTE_ADDR':'1.2.3.4'}).status_code,403)

    def test_direction_watch_notification_uses_underlying(self):
        from insights.event_center import EventCenter
        now=pd.Timestamp('2026-11-12 09:35',tz=IST)
        payload=dict(updated_at=now.isoformat(),opening_setups=[dict(underlying='NIFTY',strategy='First Red Bar',state='DIRECTION_READY',side='CE',spot_entry=100,spot_sl=99,spot_t1=102,spot_t2=103)])
        with tempfile.TemporaryDirectory() as root:
            service=SimpleNamespace(snapshot=lambda module:payload if module=='index-options' else {})
            center=EventCenter(root,service);center.collect(now.timestamp())
            alerts=center.notifications()['alerts'];self.assertEqual(len(alerts),1)
            self.assertEqual(alerts[0]['tab'],'Index Options');self.assertIn('NIFTY',alerts[0]['title']);self.assertEqual(alerts[0]['kind'],'watch')
