"""Synthetic pre-close BTST research: no lookahead, matched-time volume, scheduler."""
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock,patch
import pandas as pd
from insights.config import IST
from insights.service import InsightsService
from insights.strategies import btst_closing


def frames():
    sessions=list(pd.bdate_range(end='2026-11-12',periods=23,tz=IST))
    sessions.append(pd.Timestamp('2026-11-13',tz=IST))
    rows=[]
    for d in sessions:
        for j in range(75):
            stamp=d+pd.Timedelta(hours=9,minutes=15+5*j)
            recent=d.date()==datetime(2026,11,13).date()
            op=(100+.13*j if recent else 100+.02*j)
            close=op+(.12 if recent else .01)
            rows.append((stamp,op,close+.04,op-.35,close,2200 if recent else 1000))
    five=pd.DataFrame(rows,columns=['time','open','high','low','close','volume']).set_index('time')
    dates=pd.bdate_range(end='2026-11-12',periods=75,tz=IST)
    closes=pd.Series([99+.11*j for j in range(75)],index=dates)
    daily=pd.DataFrame(dict(open=closes-.15,high=closes+.55,
          low=closes-.75,close=closes,volume=75000.),index=dates)
    return five,daily


class BTSTClosingTests(unittest.TestCase):
    def setUp(self):
        self.f,self.d=frames()
        self.now=lambda hour,minute:datetime(2026,11,13,hour,minute,tzinfo=IST)
    def test_preview_1430_has_candidates_but_not_entry(self):
        out=btst_closing.evaluate(self.f,self.d,self.now(14,30),'SAMPLE')
        self.assertEqual(out['phase'],'PRELIMINARY')
        self.assertIsNone(out['entry'])
        self.assertGreaterEqual(out['matched_volume']['count'],15)
        self.assertGreater(out['matched_volume']['ratio'],1.5)
    def test_confirm_1505_has_risk_levels_not_win_probability(self):
        out=btst_closing.evaluate(self.f,self.d,self.now(15,5),'SAMPLE')
        self.assertTrue(out['status'].startswith('CONFIRMED'))
        self.assertGreater(out['entry'],out['sl'])
        self.assertGreater(out['t2'],out['t1'])
        self.assertIsNone(out['probability_of_win'])
        self.assertEqual(out['matched_volume']['historical_cutoff'],'15:00')
        self.assertEqual(out['event_risk'],'FRIDAY / WEEKEND GAP RISK')
    def test_later_candles_cannot_leak_into_1430_preview(self):
        full=btst_closing.evaluate(self.f,self.d,self.now(14,30),'SAMPLE')
        clipped=self.f[self.f.index<pd.Timestamp(self.now(14,30))]
        short=btst_closing.evaluate(clipped,self.d,self.now(14,30),'SAMPLE')
        self.assertEqual(full['observed_close'],short['observed_close'])
        self.assertEqual(full['matched_volume'],short['matched_volume'])
    def test_missing_volume_reference_prevents_entry(self):
        same_day=self.f[self.f.index.date==datetime(2026,11,13).date()]
        out=btst_closing.evaluate(same_day,self.d,self.now(15,5),'SAMPLE')
        self.assertIsNone(out['entry'])
        self.assertIn('matched_volume_ratio_at_least_1_5',out['blockers'])
    def test_optional_delivery_and_oi_do_not_become_fake(self):
        out=btst_closing.evaluate(self.f,self.d,self.now(15,5),'SAMPLE')
        self.assertIsNone(out['delivery']['current_pct'])
        self.assertEqual(out['futures_oi']['classification'],'UNAVAILABLE')
        supplied=btst_closing.evaluate(self.f,self.d,self.now(15,5),'SAMPLE',
                    delivery_pct=51,previous_delivery_pct=39)
        self.assertTrue(supplied['delivery']['rising'])
    def test_incomplete_or_gapped_same_day_fails_closed(self):
        today=self.f.index.date==datetime(2026,11,13).date()
        row=self.f.index[today][10]
        broken=self.f.drop(row)
        result=btst_closing.evaluate(broken,self.d,self.now(15,5),'SAMPLE')
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertIsNone(result['entry'])
    def test_scheduler_checkpoints_1430_1505_1520_once(self):
        class Broker:
            def configured(self):return True
        with tempfile.TemporaryDirectory() as folder:
            svc=InsightsService(Broker(),folder)
            svc.dashboard=Mock(return_value={})
            svc.discover_shortlist=Mock(return_value={})
            svc.scan_index_options=Mock(return_value={})
            svc.scan_fo=Mock(return_value={})
            svc.scan_intraday=Mock(return_value={})
            svc.scan_btst=Mock(return_value={})
            svc.scan_btst_closing=Mock(return_value={})
            svc.reconcile_outcomes=Mock(return_value=0)
            with patch('insights.service._holiday_set',return_value=set()):
                for clock in ((14,30),(14,30),(15,5),(15,20)):
                    svc.run_due(self.now(*clock))
                self.assertEqual(svc.scan_btst_closing.call_count,3)
                self.assertEqual(svc.scan_btst.call_count,1)


if __name__=='__main__':unittest.main()
