"""Two-pass discovery, shortlist-only monitoring and SMC/MTF regression tests."""
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
import pandas as pd
from insights.config import IST
from insights.service import InsightsService
from insights import advanced_smc


class DiscoveryBroker:
    def __init__(self):
        self.history_symbols=[]
    def configured(self):return True
    def instruments(self):
        return [
            dict(kind='stock',symbol='ALPHA',ticker='',segment='NSE_EQ',id='101',instrument='EQUITY'),
            dict(kind='stock',symbol='BETA',ticker='',segment='NSE_EQ',id='102',instrument='EQUITY'),
        ]
    def history(self,item,now,minutes=5,lookback_days=6,oi=False):
        self.history_symbols.append(item['symbol'])
        idx=pd.date_range('2026-11-11 09:15',periods=6,freq='5min',tz=IST)
        return pd.DataFrame(dict(open=[100]*6,high=[101]*6,low=[99]*6,
            close=[100]*6,volume=[1000]*6),index=idx)


class StagedScannerTests(unittest.TestCase):
    def setUp(self):
        self.broker=DiscoveryBroker()
        self.p945=datetime(2026,11,11,9,45,tzinfo=IST)
        self.p1000=datetime(2026,11,11,10,0,tzinfo=IST)

    def test_preview_then_final_no_broad_rechecks(self):
        with tempfile.TemporaryDirectory() as d:
            s=InsightsService(self.broker,d)
            def score(frame,now):
                return dict(up_score=75,down_score=20,rvol=2.3,close=101,
                    up_breakout=True,down_breakdown=False,data_asof='2026-11-11T09:40:00+05:30')
            with patch('insights.service.recent_frame',return_value=True),\
                 patch('insights.service.advanced_smc.rank_early',side_effect=score):
                preview=s.discover_shortlist(self.p945,final=False)
                self.assertFalse(preview['shortlist_finalized'])
                self.assertEqual(len(preview['preview_buy']),2)
                final=s.discover_shortlist(self.p1000,final=True)
                self.assertTrue(final['shortlist_finalized'])
                before=len(self.broker.history_symbols)
                s.discover_shortlist(self.p1000,final=True)
                self.assertEqual(len(self.broker.history_symbols),before)
            self.assertEqual(final['shortlist_size'],2)
            self.assertEqual(s.journal.signals(),[])

    def test_monitor_does_not_rescan_full_universe(self):
        with tempfile.TemporaryDirectory() as d:
            s=InsightsService(self.broker,d)
            s._shortlist_date='2026-11-11'
            s._shortlist_finalized=True
            s._shortlist=[dict(kind='stock',symbol='ALPHA',ticker='',segment='NSE_EQ',id='101',instrument='EQUITY')]
            # Fully completed recent 5m data is needed, but this test
            # deliberately returns no qualifying DAILY query; no 15m calls.
            with patch('insights.service.recent_frame',return_value=True),\
                 patch('insights.service.momentum_query.daily_gate',return_value=None):
                s._intraday_daily_cache[('2026-11-11','NSE_EQ','101')]=pd.DataFrame(
                    {'close':[100.]*25},index=pd.date_range('2026-10-01',periods=25,freq='B',tz=IST))
                output=s.scan_intraday(datetime(2026,11,11,10,5,tzinfo=IST))
            self.assertEqual(output['scanned'],1)
            self.assertEqual(output['data_assessed'],1)
            self.assertEqual(len(self.broker.history_symbols),1)
            self.assertEqual(set(self.broker.history_symbols),{'ALPHA'})
            self.assertEqual(output['buy_signals'],[])
            self.assertEqual(output['sell_signals'],[])
            self.assertEqual(s.journal.signals(),[])

    def test_mtf_trend_up_down_and_insufficient(self):
        ascending=pd.Series([100+i*0.5 for i in range(60)])
        descending=pd.Series([150-i*0.5 for i in range(60)])
        frame=lambda close:pd.DataFrame({'close':close})
        self.assertEqual(advanced_smc.trend(frame(ascending)),'UP')
        self.assertEqual(advanced_smc.trend(frame(descending)),'DOWN')
        self.assertEqual(advanced_smc.trend(frame(ascending.iloc[:12])),'UNAVAILABLE')

    def test_signal_fails_closed_on_missing_mtf(self):
        self.assertIsNone(advanced_smc.signal(None,None,None,'BUY','ALPHA',
            self.p1000,0,0))
        self.assertIsNone(advanced_smc.signal(None,None,None,'SELL','ALPHA',
            self.p1000,0,0))


if __name__=='__main__':unittest.main()
