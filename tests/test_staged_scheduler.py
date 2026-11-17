"""Scheduled broad liquidity discovery and five-minute shortlist monitoring."""
import tempfile,unittest
from datetime import datetime
from unittest.mock import Mock,patch
from insights.service import InsightsService
from insights.config import IST
from insights.tests.test_liquidity_shortlist import Broker

class SchedulingTests(unittest.TestCase):
    def prepare(self,root):
        b=Broker();s=InsightsService(b,root);s.liquidity.pause=0
        s.nifty500.resolve=Mock(return_value=(b.items,dict(name='NIFTY 500',mapped=len(b.items))))
        for name in ('dashboard','scan_intraday','scan_fo','scan_swing_shortlist','scan_index_options','scan_btst','scan_btst_closing','reconcile_outcomes'):setattr(s,name,Mock(return_value={}))
        return s,b
    def test_all_refresh_slots_and_only_shortlist_checks_between(self):
        with tempfile.TemporaryDirectory() as root:
            s,b=self.prepare(root);at=lambda h,m:datetime(2026,11,12,h,m,tzinfo=IST)
            with patch('insights.service._holiday_set',return_value=set()):
                s.run_due(at(9,40));self.assertEqual(len(b.calls),0);s.scan_fo.assert_not_called()
                for count,(h,m) in enumerate(((9,45),(10,0),(11,0),(12,0),(13,0),(14,0),(15,0)),1):
                    s.run_due(at(h,m));self.assertEqual(len(b.calls),count)
                    calls=s.scan_intraday.call_count
                    s.run_due(at(h,m));self.assertEqual(s.scan_intraday.call_count,calls)
                    s.run_due(at(h,m+5));self.assertEqual(len(b.calls),count)
                    self.assertEqual(s.scan_intraday.call_count,calls+1)
                self.assertEqual(s.scan_intraday.call_count,s.scan_fo.call_count)
                self.assertEqual(s.scan_fo.call_count,s.scan_swing_shortlist.call_count)
    def test_delayed_tick_and_late_start_do_not_replay_old_slots(self):
        with tempfile.TemporaryDirectory() as root:
            s,b=self.prepare(root);at=lambda m:datetime(2026,11,12,12,m,tzinfo=IST)
            with patch('insights.service._holiday_set',return_value=set()):
                s.run_due(at(17));self.assertEqual(len(b.calls),1);self.assertEqual(s.scan_intraday.call_count,1)
                s.run_due(at(18));self.assertEqual(s.scan_intraday.call_count,1)
                s.run_due(at(21));self.assertEqual(s.scan_intraday.call_count,2);self.assertEqual(len(b.calls),1)
    def test_holiday_and_overlap_do_not_request_quotes(self):
        with tempfile.TemporaryDirectory() as root:
            s,b=self.prepare(root)
            with patch('insights.service._holiday_set',return_value=set()):
                s.run_due(datetime(2026,11,10,10,0,tzinfo=IST));self.assertFalse(b.calls)
                s._job_lock.acquire()
                try:s.run_due(datetime(2026,11,12,10,0,tzinfo=IST));self.assertFalse(b.calls)
                finally:s._job_lock.release()
