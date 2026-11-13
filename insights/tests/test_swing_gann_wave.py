"""Completed daily/weekly Gann and confirmed wave evidence for Swing Trades."""
import unittest
import pandas as pd
from insights.config import IST
from insights import swing_gann_wave
from insights.strategies import swing


def frame():
    idx=pd.date_range('2025-01-01',periods=420,freq='B',tz=IST)
    # Synthetic OHLCV; no real-market accuracy inference.
    c=pd.Series([100+i*.15+3*((i%30)/30) for i in range(len(idx))],index=idx)
    return pd.DataFrame(dict(open=c-.3,high=c+1,low=c-1,close=c,
                             volume=[120000]*len(c)),index=idx)


class SwingGannWaveTests(unittest.TestCase):
    def test_daily_weekly_layers_from_completed_daily(self):
        f=frame()
        now=pd.Timestamp(f.index[-1])+pd.Timedelta(hours=16)
        result=swing_gann_wave.assess(f,now)
        self.assertEqual(result['status'],'EVIDENCE ONLY')
        self.assertEqual(result['timeframe'],'COMPLETED DAILY AND WEEKLY')
        self.assertIsNotNone(result['gann']['support'])
        self.assertIsNotNone(result['gann']['resistance'])
        self.assertIn('daily_structure',result['wave'])
        self.assertNotIn('win_probability',result)
    def test_today_ongoing_daily_bar_excluded(self):
        f=frame()
        now=f.index[-1]+pd.Timedelta(hours=12)
        result=swing_gann_wave.assess(f,now)
        self.assertNotEqual(result['price_asof'][:10],f.index[-1].date().isoformat())
    def test_partial_week_is_not_used_for_weekly_pivots(self):
        f=frame()
        # A Thursday does not complete that week's W-FRI aggregate.
        thu=f.index[f.index.weekday==3][-1]
        daily=f[f.index<=thu]
        result=swing_gann_wave.assess(daily,thu+pd.Timedelta(hours=16))
        for pivot in result['wave']['weekly_confirmed_pivots']:
            self.assertLessEqual(pd.Timestamp(pivot['confirmed_after']).date(),thu.date())
    def test_annotate_preserves_swing_trade_levels(self):
        f=frame()
        now=f.index[-1]+pd.Timedelta(hours=16)
        existing=dict(strategy='21/50 EMA trend pullback',
                      entry=123,stop=117,target=135,target_3r=141,
                      risk_reward=2.0,trend_strength=50)
        annotated=swing_gann_wave.annotate(existing,f,now)
        for key,value in existing.items():self.assertEqual(annotated[key],value)
        self.assertIn('swing_gann_wave',annotated)
    def test_missing_daily_and_naive_time_fail_closed(self):
        f=frame()
        self.assertEqual(swing_gann_wave.assess(None,f.index[-1])['status'],'UNAVAILABLE')
        self.assertEqual(swing_gann_wave.assess(f,pd.Timestamp('2026-06-01'))['status'],'UNAVAILABLE')
    def test_original_swing_scan_still_rejects_insufficient_candles(self):
        f=frame().head(30)
        self.assertEqual(swing.scan(f,'EXAMPLE',f.index[-1]+pd.Timedelta(hours=16)),[])


if __name__=='__main__':unittest.main()
