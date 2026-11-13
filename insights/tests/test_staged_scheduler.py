"""Scheduler boundaries: only 09:45 and 10:00 broad discovery, then cached shortlist monitoring."""
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock,patch
from insights.service import InsightsService
from insights.config import IST


class MinimalBroker:
    def configured(self):return True


class SchedulingTests(unittest.TestCase):
    def test_preliminary_final_monitor_are_separate_and_non_overlapping(self):
        with tempfile.TemporaryDirectory() as folder:
            service=InsightsService(MinimalBroker(),folder)
            service.dashboard=Mock(return_value={})
            service.discover_shortlist=Mock(return_value={})
            service.scan_intraday=Mock(return_value={})
            service.scan_index_options=Mock(return_value={})
            service.scan_fo=Mock(return_value={})
            service.scan_btst=Mock(return_value={})
            service.reconcile_outcomes=Mock(return_value=0)
            at=lambda h,m:datetime(2026,11,12,h,m,tzinfo=IST)
            with patch('insights.service._holiday_set',return_value=set()):
                self.assertEqual(service.run_due(at(9,40))['status'],'OK')
                self.assertEqual(service.discover_shortlist.call_count,0)
                self.assertEqual(service.scan_index_options.call_count,1)
                self.assertEqual(service.scan_fo.call_count,1)
                self.assertEqual(service.run_due(at(9,45))['status'],'OK')
                self.assertEqual(service.discover_shortlist.call_count,1)
                self.assertEqual(service.scan_index_options.call_count,2)
                self.assertEqual(service.scan_fo.call_count,2)
                service.run_due(at(10,0))
                self.assertEqual(service.discover_shortlist.call_count,2)
                self.assertEqual(service.scan_index_options.call_count,3)
                self.assertEqual(service.scan_fo.call_count,3)
                service.run_due(at(10,5))
                self.assertEqual(service.scan_intraday.call_count,1)
                self.assertEqual(service.scan_index_options.call_count,4)
                self.assertEqual(service.scan_fo.call_count,4)
                service.run_due(at(10,10))
                self.assertEqual(service.scan_intraday.call_count,2)
                self.assertEqual(service.scan_index_options.call_count,5)
                self.assertEqual(service.scan_fo.call_count,5)
                service.run_due(at(10,11))
                self.assertEqual(service.scan_intraday.call_count,2)
                self.assertEqual(service.scan_index_options.call_count,5)
                self.assertEqual(service.scan_fo.call_count,5)
                self.assertEqual(service.discover_shortlist.call_count,2)

    def test_holiday_makes_no_broker_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            service=InsightsService(MinimalBroker(),folder)
            service.dashboard=Mock()
            service.discover_shortlist=Mock()
            service.scan_intraday=Mock()
            with patch('insights.service._holiday_set',return_value=set()):
                result=service.run_due(datetime(2026,11,10,10,0,tzinfo=IST))
            self.assertIn('BLOCKED',result['status'])
            service.dashboard.assert_not_called()
            service.discover_shortlist.assert_not_called()
            service.scan_intraday.assert_not_called()


if __name__=='__main__':unittest.main()
