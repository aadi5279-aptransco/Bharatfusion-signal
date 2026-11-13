"""Analyse movers, optional chain, Gann/time-cycle/swing evidence.

Synthetic fixtures only. No historical performance/ML probability claims.
"""
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
import pandas as pd
from insights.config import IST
from insights.service import InsightsService
from insights import cycle_wave,analyse_engine


def bars(minutes=5,n=260,now=None):
    now=now or datetime(2026,11,13,11,0,tzinfo=IST)
    idx=pd.date_range(end=pd.Timestamp(now)-pd.Timedelta(minutes=minutes),
                      periods=n,freq=f'{minutes}min',tz=IST)
    close=pd.Series([100+i*.08 for i in range(n)],index=idx)
    return pd.DataFrame(dict(open=close-.15,high=close+.4,
        low=close-.5,close=close,volume=[5000.]*n),index=idx)


class FakeBroker:
    def configured(self):return True
    def instruments(self):
        return [dict(kind='index',symbol='NIFTY',id='13',
                     segment='IDX_I',instrument='INDEX'),
                dict(kind='stock',symbol='SAMPLETEST',id='100',
                     segment='NSE_EQ',instrument='EQUITY'),
                dict(kind='stock',symbol='SMALL',id='101',
                     segment='NSE_EQ',instrument='EQUITY')]
    def market_quotes(self,items,now):
        return {'100':dict(change_pct=3.2,last_price=103,
                   baseline_type='PREVIOUS_CLOSE',volume=100000,fetched_at=now.isoformat()),
                '101':dict(change_pct=-2.5,last_price=97,
                   baseline_type='PREVIOUS_CLOSE',volume=150000,fetched_at=now.isoformat())}
    def history(self,item,now,minutes=5,lookback_days=10):
        return bars(minutes=minutes,n=260,now=now)
    def expiry_list(self,item):
        raise ValueError('NO F&O CONTRACT FOR CASH STOCK')


class AnalyseTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,13,11,0,tzinfo=IST)
    def test_all_indices_and_positive_negative_movers(self):
        with tempfile.TemporaryDirectory() as d:
            svc=InsightsService(FakeBroker(),d)
            c=svc.analyse_choices(self.now)
            self.assertEqual(c['indices'][0]['symbol'],'NIFTY')
            self.assertEqual(c['gainers'][0]['symbol'],'SAMPLETEST')
            self.assertEqual(c['losers'][0]['symbol'],'SMALL')
            self.assertEqual(c['coverage'],2)
            self.assertTrue(c['gainers'][0]['baseline_type']=='PREVIOUS_CLOSE')
    def test_cash_stock_analysis_survives_missing_option_chain(self):
        with tempfile.TemporaryDirectory() as d:
            svc=InsightsService(FakeBroker(),d)
            d=svc.analyse('SAMPLETEST',self.now)
            self.assertEqual(d['symbol'],'SAMPLETEST')
            self.assertIsNone(d['metrics'])
            self.assertIn('UNAVAILABLE',d['chain_status'])
            self.assertIsNone(d['probability_of_win'])
            self.assertIn('probability_status',d)
            self.assertTrue(len(d['candles'])>0)
    def test_gann_no_future_pivots_or_prediction(self):
        f=bars(n=100)
        out=cycle_wave.assess(f,self.now)
        self.assertEqual(out['status'],'EVIDENCE ONLY')
        self.assertEqual(out['wave']['wave_count'][:10],'UNVERIFIED')
        for p in out['wave']['recent_confirmed_pivots']:
            self.assertLessEqual(pd.Timestamp(p['confirmed_after']),f.index[-1])
    def test_probability_unavailable_when_data_stale(self):
        old=bars(now=datetime(2026,11,11,11,0,tzinfo=IST))
        result=analyse_engine.evaluate(old,old,old,self.now)
        self.assertIsNone(result['win_probability'])
        self.assertIsNone(result['entry_plan'])
    def test_no_trading_or_raw_order_call(self):
        with tempfile.TemporaryDirectory() as d:
            broker=FakeBroker();svc=InsightsService(broker,d)
            svc.analyse_choices(self.now)
            svc.analyse('SAMPLETEST',self.now)
            self.assertEqual(svc.journal.signals(),[])
            self.assertFalse(svc.health()['orders_enabled'])


if __name__=='__main__':unittest.main()
