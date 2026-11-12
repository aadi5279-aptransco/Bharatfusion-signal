"""Fib+SMC and OI conservative read-only regression tests."""
import unittest
from datetime import datetime
import pandas as pd
from insights.config import IST
from insights.strategies import fib_smc,fib_oi


def make_spot():
    stamps=pd.date_range('2026-11-12 09:15',periods=75,freq='5min',tz=IST)
    values=[101+0.015*i for i in range(75)]
    return pd.DataFrame(dict(open=[x-.1 for x in values],
       high=[x+.45 for x in values],low=[x-.45 for x in values],
       close=values,volume=[10000]*75),index=stamps)


class FibRulesTests(unittest.TestCase):
    def test_0945_reference_uses_exact_first_6_candles(self):
        f=make_spot()
        before=fib_smc.evaluate(f,datetime(2026,11,12,9,44,tzinfo=IST),'0945')
        self.assertEqual(before['state'],'WAITING')
        now=datetime(2026,11,12,10,5,tzinfo=IST)
        x=fib_smc.evaluate(f,now,'0945')
        self.assertEqual(x['reference']['interval'],'09:15–09:45')
        self.assertAlmostEqual(x['fib']['0'],min(f.low.iloc[:6]))
        self.assertAlmostEqual(x['fib']['1'],max(f.high.iloc[:6]))
        self.assertLess(x['fib']['0.44'],x['fib']['0.5'])
        self.assertEqual(x['source'],'COMPLETED 5m SPOT/CASH CANDLES')

    def test_1245_waits_for_1315_close_plus_confirmations(self):
        f=make_spot()
        x=fib_smc.evaluate(f,datetime(2026,11,12,13,10,tzinfo=IST),'1245')
        self.assertEqual(x['state'],'WAITING')
        y=fib_smc.evaluate(f,datetime(2026,11,12,13,15,tzinfo=IST),'1245')
        self.assertEqual(y['state'],'WAITING')  # first post-reference candle absent
        z=fib_smc.evaluate(f,datetime(2026,11,12,13,30,tzinfo=IST),'1245')
        self.assertEqual(z['reference']['interval'],'12:45–13:15')
        self.assertIn(z['state'],('NO_TRADE','WATCH','STRUCTURE_READY'))
        self.assertEqual(z['reference']['color'],'GREEN')

    def test_missing_exact_reference_bar_cannot_fake_range(self):
        f=make_spot()
        f=f.drop(pd.Timestamp('2026-11-12 09:30',tz=IST))
        x=fib_smc.evaluate(f,datetime(2026,11,12,10,10,tzinfo=IST),'0945')
        self.assertEqual(x['state'],'WAITING')
        self.assertIn('Missing exact',x['reason'])

    def test_oi_unavailable_never_becomes_confirmed(self):
        row={'state':'STRUCTURE_READY','side':'CE','spot_price':102}
        result=fib_oi.decide(row)
        self.assertIn('WATCH_ONLY',result['trade_status'])
        self.assertEqual(result['oi']['status'],'UNAVAILABLE')

    def test_oi_contradiction_blocks(self):
        chain=dict(oc={
          '100':{'ce':{'oi':150,'previous_oi':100},'pe':{'oi':100,'previous_oi':150}},
          '105':{'ce':{'oi':150,'previous_oi':100},'pe':{'oi':100,'previous_oi':150}}})
        oi=fib_oi.chain_evidence(chain,'CE',101)
        self.assertEqual(oi['status'],'CONTRADICTS')
        result=fib_oi.decide({'state':'STRUCTURE_READY','side':'CE','spot_price':101},
                              chain,{'status':'CONFIRMED'})
        self.assertIn('SKIP',result['trade_status'])

    def test_previous_session_futures_oi_never_confirms(self):
        idx=pd.DatetimeIndex(['2026-11-11T15:00:00+05:30',
                              '2026-11-11T15:15:00+05:30'])
        candles=pd.DataFrame(dict(close=[100,101],oi=[1000,1100]),index=idx)
        evidence=fib_oi.futures_evidence(
            candles,'CE',datetime(2026,11,12,10,15,tzinfo=IST))
        self.assertEqual(evidence['status'],'UNAVAILABLE')
        self.assertIn('stale',evidence['reason'].lower())

    def test_oi_agreement_requires_futures_and_chain(self):
        chain=dict(oc={
          '100':{'ce':{'oi':50,'previous_oi':100},'pe':{'oi':200,'previous_oi':100}},
          '105':{'ce':{'oi':50,'previous_oi':100},'pe':{'oi':200,'previous_oi':100}}})
        row={'state':'STRUCTURE_READY','side':'CE','spot_price':101}
        self.assertEqual(fib_oi.chain_evidence(chain,'CE',101)['status'],'CONFIRMED')
        self.assertIn('WATCH_ONLY',fib_oi.decide(row,chain)['trade_status'])
        self.assertIn('OI_CONFIRMED_SPOT_RESEARCH',
                      fib_oi.decide(row,chain,{'status':'CONFIRMED'})['trade_status'])


if __name__=='__main__':unittest.main()
