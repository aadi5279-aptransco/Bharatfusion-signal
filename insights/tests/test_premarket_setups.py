import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from insights.config import IST
from insights.strategies.premarket import evaluate,rank
from insights.premarket_setups import prepare,fetch_daily
from insights.premarket_followthrough import PremarketFollowthrough,assess
from insights.premarket_compare import compare
from insights.brokers.dhan import BrokerUnavailable
from insights.tests.test_premarket_8am import daily,MockDailyBroker
from insights.tests.test_premarket_followthrough import frames,NOW
from insights.service import InsightsService

AT=pd.Timestamp('2026-11-13 08:00',tz=IST)
def liquid():
    f=daily();f['volume']=1e6
    return f

class SetupTests(unittest.TestCase):
    def test_inside_nr7_can_select_a_quiet_day_not_a_big_gainer(self):
        f=liquid();x=f.iloc[-2];p=float(x.close)
        f.iloc[-1]=[p-.1,p+.2,p-.2,p,1e6]
        row=evaluate(f,'TEST',AT)
        self.assertEqual(row['previous_day_change_pct'],0)
        self.assertTrue(row['setup_metrics']['nr7'])
        self.assertTrue(row['setup_metrics']['inside_day'])
        self.assertTrue(row['setups'])
        self.assertTrue(rank([row],str(AT))['candidates'])
        self.assertNotIn('entry',row)

    def test_volume_break_and_mirror(self):
        f=liquid();level=f.high.iloc[-21:-1].max()
        f.iloc[-1]=[level-.2,level+.4,level-.3,level+.3,2e6]
        row=evaluate(f,'UP',AT)
        self.assertTrue(any('Volume-confirmed' in x['strategy'] and x['direction']=='BUY' for x in row['setups']))
        g=f.copy()
        g['open']=300-f.open;g['close']=300-f.close;g['high']=300-f.low;g['low']=300-f.high
        row=evaluate(g,'DOWN',AT)
        self.assertTrue(any('Volume-confirmed' in x['strategy'] and x['direction']=='SELL' for x in row['setups']))

    def test_low_liquidity_and_extended_break_not_promoted(self):
        f=liquid();f.iloc[-1]=[130,131,129,130.9,2e6]
        f['volume']=100
        self.assertFalse(evaluate(f,'LOW',AT)['setups'])
        f=liquid();f.iloc[-1]=[140,145,139,144.9,2e6]
        self.assertFalse(evaluate(f,'EXTENDED',AT)['setups'])

    def test_no_lookahead_timezone_and_invalid_values(self):
        f=liquid();expected=evaluate(f,'X',AT)
        today=f.tail(1).copy();today.index=pd.DatetimeIndex([AT.normalize()])
        joined=pd.concat([f,today]);joined.index=joined.index.tz_convert('UTC')
        self.assertEqual(expected,evaluate(joined,'X',AT.tz_convert('UTC')))
        f.iloc[-1,f.columns.get_loc('high')]=float('inf')
        self.assertIsNone(evaluate(f,'X',AT))

    def test_stale_excluded_coverage_and_explanation(self):
        class Broker(MockDailyBroker):
            def daily(self,item,now,**kwargs):return liquid() if item['symbol']=='GAIN' else liquid().iloc[:-1]
        with tempfile.TemporaryDirectory() as root,patch('insights.service._holiday_set',return_value=set()):
            out=InsightsService(Broker(),root).scan_premarket(AT)
        self.assertEqual(out['stale_count'],1)
        self.assertEqual(out['coverage_pct'],50)
        self.assertEqual(len(out['audit']),2)
        self.assertFalse(out['losers'])

    def test_failed_daily_request_retried_once(self):
        calls=[]
        def daily(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:raise BrokerUnavailable('temporary')
            return liquid()
        self.assertEqual(len(fetch_daily(SimpleNamespace(daily=daily),{},AT)),85)
        self.assertEqual(len(calls),2)
        with self.assertRaises(BrokerUnavailable):fetch_daily(SimpleNamespace(daily=lambda *a,**k:(_ for _ in ()).throw(BrokerUnavailable('down'))),{},AT)

    def test_candidates_join_fixed_followthrough_universe(self):
        with tempfile.TemporaryDirectory() as root:
            service=SimpleNamespace(root=Path(root),snapshot=lambda _:dict(candidates=[{'symbol':'NEW'}],gainers=[{'symbol':'OLD'},{'symbol':'NEW'}],losers=[],previous_session='2026-11-13'))
            monitor=PremarketFollowthrough(service,lambda:set())
            self.assertTrue(monitor.freeze(NOW));self.assertEqual(monitor.state['symbols'],['NEW','OLD'])

    def test_prior_day_break_needs_two_closes_and_vital_filters(self):
        f,d,m=frames()
        out=assess(f,d,m,{'symbol':'TEST'},NOW,set())
        self.assertTrue(any(p['strategy'].startswith('Prior-day') for p in out['signals']))
        f.loc[f.index[-2],['open','high','low','close']]=[100,100.1,99.9,100]
        out=assess(f,d,m,{'symbol':'TEST'},NOW,set())
        self.assertFalse(any(p['strategy'].startswith('Prior-day') for p in out['signals']))

    def test_comparison_does_not_invent_unknown_stock_or_private_rules(self):
        service=SimpleNamespace(_lookup=lambda s:None if s=='UNKNOWN' else dict(kind='stock',symbol=s),broker=SimpleNamespace(daily=lambda *a,**k:liquid()))
        with patch('insights.service._holiday_set',return_value=set()):out=compare(service,['KNOWN','UNKNOWN'],AT)
        self.assertEqual(out['rows'][1]['status'],'NOT MAPPED')
        self.assertIn('evidence',out['rows'][0])
        self.assertIn('Does not establish Birbull',out['limitation'])

if __name__=='__main__':unittest.main()
