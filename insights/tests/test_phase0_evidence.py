"""Regression cases from the user's Phase 0 report; offline fixtures only."""
import unittest
from unittest.mock import Mock
import pandas as pd
from insights.config import IST
from insights.data_layer.evidence import candle_evidence,result_status
from insights.data_layer.transport import DataError
from insights.tests.test_phase0_data import transport
import tempfile

def bars(stamps):
    return pd.DataFrame(dict(open=100.,high=101.,low=99.,close=100.,volume=10.),
        index=pd.DatetimeIndex(stamps))
NOW=pd.Timestamp('2026-11-22 22:52',tz=IST)
ITEM=dict(id='fixture-id',segment='NSE_EQ',instrument='EQUITY',kind='stock')

class ReportEvidenceTests(unittest.TestCase):
    def test_request_boundary_does_not_invent_missing_morning(self):
        f=bars(pd.date_range('2026-11-16 10:00',periods=66,freq='5min',tz=IST))
        r=candle_evidence(f,5,NOW,ITEM,requested_start=pd.Timestamp('2026-11-16 09:57:23',tz=IST))
        self.assertEqual(r['returned_quality']['sessions'][0]['missing_full_grid_bars'],0)
        self.assertNotIn('OBSERVED_SESSION_COVERAGE_INCOMPLETE',r['warnings'])
    def test_boundary_exclusion_preserves_missing_tail(self):
        f=bars(pd.date_range('2026-11-16 10:00',periods=63,freq='5min',tz=IST))
        r=candle_evidence(f,5,NOW,ITEM,requested_start=pd.Timestamp('2026-11-16 09:57:23',tz=IST))
        self.assertEqual(r['returned_quality']['sessions'][0]['missing_full_grid_bars'],3)
        self.assertIn('OBSERVED_SESSION_COVERAGE_INCOMPLETE',r['warnings'])
    def test_null_mapping_never_passes(self):
        self.assertEqual(result_status(None),'UNAVAILABLE')
    def test_missing_tail_is_detected_without_internal_gap(self):
        f=bars(pd.date_range('2026-11-20 09:15',periods=360,freq='min',tz=IST))
        r=candle_evidence(f,1,NOW,ITEM)
        self.assertEqual(r['returned_quality']['sessions'][0]['missing_full_grid_bars'],15)
        self.assertEqual(result_status(r),'REVIEW')
    def test_raw_and_returned_last_are_separate(self):
        f=bars(pd.date_range('2026-11-20 09:15',periods=6,freq='60min',tz=IST))
        r=candle_evidence(f,60,NOW,ITEM,{'last_bar':'2026-11-20T15:15:00+05:30'})
        self.assertIn('14:15',r['returned_quality']['last'])
        self.assertIn('15:15',r['download_quality']['last_bar'])
    def test_sparse_off_grid_options_do_not_pass(self):
        f=bars(pd.date_range('2026-11-20 11:56',periods=5,freq='5min',tz=IST))
        r=candle_evidence(f,5,NOW,dict(ITEM,kind='option'))
        self.assertIn('OFF_REGULAR_SESSION_GRID',r['warnings'])
        self.assertIn('BELOW_200_BAR_RESEARCH_BASELINE',r['warnings'])
        self.assertIn('REQUESTED_OI_MISSING',r['warnings'])
    def test_after_session_and_partial_bars_need_review(self):
        f=bars(pd.DatetimeIndex(['2026-11-20 15:15','2026-11-20 15:35'],tz=IST))
        r=candle_evidence(f,60,NOW,dict(ITEM,kind='future'))
        self.assertIn('OUTSIDE_REGULAR_SESSION_REFERENCE',r['warnings'])
        self.assertIn('SESSION_END_PARTIAL_BARS_REQUIRE_REVIEW',r['warnings'])
    def test_live_tail_is_not_expected_before_completion(self):
        f=bars(pd.date_range('2026-11-20 09:15',periods=9,freq='5min',tz=IST))
        r=candle_evidence(f,5,pd.Timestamp('2026-11-20 10:00',tz=IST),ITEM)
        self.assertEqual(r['returned_quality']['sessions'][0]['missing_full_grid_bars'],0)
    def test_provider_error_code_preserved_without_message(self):
        with tempfile.TemporaryDirectory() as root:
            sender=Mock(return_value=dict(status='failure',errorCode='DH-907',remarks='fixture-secret'))
            with self.assertRaises(DataError) as raised:
                transport(root,sender).request('POST','/charts/historical',{})
            self.assertEqual(raised.exception.code,'DH-907')
            self.assertNotIn('fixture-secret',str(raised.exception))
    def test_arbitrary_provider_code_is_not_exposed(self):
        self.assertEqual(DataError('Failure',code='fixture-secret').code,'DATA_ERROR')

if __name__=='__main__':
    unittest.main()
