"""Fail-closed core weekend blockers when entry history is insufficient."""
import unittest
import pandas as pd
from engine import analyze, IST


class WarmupWindowRegressionTests(unittest.TestCase):
    def test_weekend_reports_window_blocker_even_during_warmup(self):
        idx=pd.date_range('2026-11-14 09:15',periods=12,freq='min',tz=IST)
        f=pd.DataFrame(dict(open=[100.]*len(idx),high=[101.]*len(idx),
             low=[99.]*len(idx),close=[100.]*len(idx),volume=[1000.]*len(idx)),index=idx)
        result=analyze(f,'TEST',now=pd.Timestamp('2026-11-14 10:00',tz=IST))
        self.assertEqual(result['action'],'WAIT')
        self.assertTrue(any('Need at least 60' in x for x in result['blockers']))
        self.assertTrue(any('Outside entry window' in x for x in result['blockers']))
        self.assertIsNone(result['entry'])


if __name__=='__main__':unittest.main()
