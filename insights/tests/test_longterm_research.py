"""Swing and Multibagger completed-candle, eligibility and scheduling tests."""
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch
import pandas as pd
from insights.config import IST
from insights.service import InsightsService
from insights.strategies import swing,multibagger


def daily_bars():
    index=pd.date_range(end='2026-11-12',periods=650,freq='B',tz=IST)
    # All values are synthetic TEST fixtures, never Dhan quotes.
    close=pd.Series([50+i*.14 for i in range(len(index))],index=index)
    return pd.DataFrame(dict(open=close-.3,high=close+.7,low=close-1,
                             close=close,volume=[120000]*len(index)),index=index)


def bundle(data):
    return {'asof':'2026-11-12','symbols':{
       'DEMO':dict(source='Local verified fixture',period_end='2026-09-30',**data)}}


class LongtermStrategyTests(unittest.TestCase):
    def test_swing_uses_only_completed_candles_and_validates_data(self):
        bars=daily_bars()
        self.assertEqual(swing.scan(bars.iloc[:40],'DEMO',datetime(2026,11,12,16,0,tzinfo=IST)),[])
        self.assertEqual(swing.scan(None,'DEMO'),[])
        for x in swing.scan(bars,'DEMO',datetime(2026,11,12,16,0,tzinfo=IST)):
            self.assertGreater(x['entry'],x['stop'])
            self.assertGreater(x['target'],x['entry'])
            self.assertEqual(x['risk_reward'],2.0)

    def test_multibagger_missing_sources_fail_closed(self):
        x=multibagger.evaluate(daily_bars(),'DEMO','2026-11-12')
        self.assertIsNotNone(x)
        self.assertFalse(x['eligible'])
        self.assertEqual(x['eligibility_status'],'UNVERIFIED')
        self.assertEqual(x['market_cap_cr'],None)
        self.assertIn('UNVERIFIED',[r['status'] for r in x['criteria']])
        self.assertIn('UNVERIFIED',[r['status'] for r in x['guards']])
        self.assertFalse(multibagger.within_market_cap(x,300,20000))

    def test_multibagger_eligible_only_with_verified_eligibility_sources(self):
        fundamentals=bundle(dict(market_cap_cr=15000,sales_cagr_3y=25,
           profit_cagr_3y=24,quarter_profit_yoy=30,roce=20,debt_equity=.3,
           promoter_holding=55,promoter_pledging=0,operating_cash_flow=500,peg=1.2))
        surveillance=bundle(dict(listed_exchange='NSE',listing_date='2020-10-01',
            asm=False,gsm=False,frequent_circuit_locks=False))
        x=multibagger.evaluate(daily_bars(),'DEMO','2026-11-12',
              fundamentals=fundamentals,surveillance=surveillance,rs_rank=75)
        self.assertTrue(x['eligible'])
        self.assertEqual(x['eligibility_status'],'ELIGIBLE')
        self.assertTrue(multibagger.within_market_cap(x,300,20000))
        self.assertFalse(multibagger.within_market_cap(x,300,10000))
        self.assertGreater(x['score'],0)
        self.assertEqual(x['score_max'],20)
        self.assertGreater(x['avg_daily_traded_value_lakh'],50)

    def test_asm_and_circuits_block(self):
        fundamentals=bundle(dict(market_cap_cr=800))
        surveillance=bundle(dict(listed_exchange='BSE',listing_date='2019-01-01',
                                 asm=True,gsm=False,frequent_circuit_locks=True))
        x=multibagger.evaluate(daily_bars(),'DEMO','2026-11-12',
              fundamentals=fundamentals,surveillance=surveillance)
        self.assertFalse(x['eligible'])
        self.assertEqual(x['eligibility_status'],'BLOCKED')
        self.assertIn('FAIL',[g['status'] for g in x['guards']])

    def test_stale_surveillance_does_not_pass(self):
        fundamentals=bundle(dict(market_cap_cr=800))
        surveillance=bundle(dict(listed_exchange='NSE',listing_date='2019-01-01',
                                 asm=False,gsm=False,frequent_circuit_locks=False))
        surveillance['asof']='2025-01-01'
        x=multibagger.evaluate(daily_bars(),'DEMO','2026-11-12',
              fundamentals=fundamentals,surveillance=surveillance)
        self.assertEqual(x['eligibility_status'],'UNVERIFIED')


class ResearchUniverseTests(unittest.TestCase):
    def test_nse_and_bse_cash_shares_from_cached_dhan_master(self):
        from insights.brokers.dhan import DhanReadOnly
        master=pd.DataFrame([
            dict(EXCH_ID='NSE',SEGMENT='E',INSTRUMENT='EQUITY',
                 SECURITY_ID='101',SYMBOL_NAME='NSE_EXAMPLE',SERIES='EQ'),
            dict(EXCH_ID='BSE',SEGMENT='E',INSTRUMENT='EQUITY',
                 SECURITY_ID='202',SYMBOL_NAME='BSE_EXAMPLE',SERIES='A'),
            dict(EXCH_ID='NSE',SEGMENT='D',INSTRUMENT='FUTSTK',
                 SECURITY_ID='303',SYMBOL_NAME='EXAMPLE_FUT',SERIES=''),
        ])
        with patch('data._MASTER',master):
            stocks=DhanReadOnly('dummy','dummy').longterm_instruments()
        self.assertEqual(len(stocks),2)
        self.assertEqual(set(x['segment'] for x in stocks),{'NSE_EQ','BSE_EQ'})
        self.assertTrue(all(x['kind']=='stock' for x in stocks))


class LongtermSchedulerTests(unittest.TestCase):
    def test_new_read_only_api_tabs(self):
        from insights.api import create_app
        class DummyBroker:
            def configured(self):return True
        with tempfile.TemporaryDirectory() as path:
            svc=InsightsService(DummyBroker(),path)
            client=create_app(svc).test_client()
            for suffix in ('swing-trades','multibagger'):
                response=client.get('/api/v1/market-insights/'+suffix)
                self.assertEqual(response.status_code,200)
                self.assertIn('status',response.json)
            self.assertFalse(client.get('/api/v1/health').json['orders_enabled'])

    def test_after_close_only_once_and_never_on_holiday(self):
        class DummyBroker:
            def configured(self):return True
        with tempfile.TemporaryDirectory() as path:
            svc=InsightsService(DummyBroker(),path)
            svc.scan_longterm=Mock(return_value={'swing_count':0,'multibagger_count':0})
            clock=lambda h,m:datetime(2026,11,12,h,m,tzinfo=IST)
            with patch('insights.service._holiday_set',return_value=set()):
                self.assertEqual(svc.run_due(clock(15,35))['status'].startswith('BLOCKED'),True)
                result=svc.run_due(clock(15,40))
                self.assertEqual(result['status'],'DAILY LONGTERM COMPLETE')
                self.assertEqual(result['premarket_prepared'],0)
                self.assertIn('UNAVAILABLE',result['premarket_prep_status'])
                self.assertEqual(svc.run_due(clock(15,45))['status'],'DAILY LONGTERM ALREADY COMPLETE')
                svc.scan_longterm.assert_called_once()
                self.assertIn('BLOCKED',svc.run_due(datetime(2026,11,10,15,45,tzinfo=IST))['status'])


if __name__=='__main__':unittest.main()
