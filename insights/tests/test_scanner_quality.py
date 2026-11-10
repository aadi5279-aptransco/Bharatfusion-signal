"""Fail-closed live scanner quality checks; fixtures never call Dhan."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
import pandas as pd

from insights.config import IST
from insights.scanner_quality import current_completed_bar, recent_frame, recent_context
from insights.service import InsightsService
from insights.strategies import equity


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,11,11,10,15,tzinfo=IST)

    def test_fresh_and_completed_5m(self):
        self.assertTrue(current_completed_bar('2026-11-11T10:10:00+05:30',self.now))
        self.assertFalse(current_completed_bar('2026-11-11T10:15:00+05:30',self.now))
        self.assertFalse(current_completed_bar('2026-11-11T09:20:00+05:30',self.now))
        self.assertFalse(current_completed_bar('2026-11-09T15:25:00+05:30',self.now))
        self.assertFalse(current_completed_bar('2026-11-11T10:10:00',self.now))
        self.assertFalse(current_completed_bar(None,self.now))

    def test_recent_context_accepts_only_same_session(self):
        a={'session_date':'2026-11-11','asof':'2026-11-11T10:10:00+05:30','bias':'Uptrend'}
        self.assertTrue(recent_context(a,self.now))
        self.assertFalse(recent_context({**a,'session_date':'2026-11-09'},self.now))
        self.assertFalse(recent_context({**a,'asof':'2026-11-09T15:25:00+05:30'},self.now))
        self.assertFalse(recent_context({**a,'bias':'UNAVAILABLE'},self.now))

    def test_recent_frame_rejects_stale_and_incomplete(self):
        f=pd.DataFrame({'close':[10.]},index=pd.DatetimeIndex(['2026-11-11T10:10:00+05:30']))
        self.assertTrue(recent_frame(f,self.now))
        self.assertFalse(recent_frame(f.iloc[:0],self.now))
        f.index=pd.DatetimeIndex(['2026-11-09T15:25:00+05:30'])
        self.assertFalse(recent_frame(f,self.now))

    def test_intraday_time_gate_1015(self):
        # The strategy must not score after only the first 45 minutes.
        self.assertIsNone(equity.intraday(None,'TEST',datetime(2026,11,11,10,10,tzinfo=IST),0,0))

    def test_default_stock_selection_prioritizes_sector_mapping(self):
        class Broker:
            def configured(self):return True
            def instruments(self):
                return [dict(kind='stock',symbol='AAAA',ticker='',id='1'),
                        dict(kind='stock',symbol='TCS',ticker='',id='2'),
                        dict(kind='stock',symbol='ZZZZ',ticker='',id='3')]
        with tempfile.TemporaryDirectory() as d,patch('insights.service._sector_map',return_value={'TCS':'IT'}):
            s=InsightsService(Broker(),d)
            self.assertEqual(s._stock_list()[0]['symbol'],'TCS')

    def test_stale_intraday_context_gives_no_candidates(self):
        class Broker:
            def configured(self):return True
            def instruments(self):return [dict(kind='stock',symbol='TCS',ticker='',id='1')]
        with tempfile.TemporaryDirectory() as d:
            service=InsightsService(Broker(),d)
            service._snapshots['dashboard']={'indices':[dict(symbol='NIFTY',bias='Uptrend',session_date='2026-11-09',asof='2026-11-09T15:25:00+05:30',session_change=1)],'sectors':[]}
            result=service.scan_intraday(self.now)
            self.assertEqual(result['data_assessed'],0)
            self.assertEqual(result['signals'],[])
            self.assertIn('NO VERIFIED',result['status'])
            self.assertEqual(service.journal.signals(),[])


if __name__=='__main__':unittest.main()
