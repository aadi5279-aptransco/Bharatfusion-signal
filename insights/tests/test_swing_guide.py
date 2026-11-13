"""PDF-derived swing research: completed bars, RS ranking, setup and stop guards."""
import unittest
import pandas as pd
from insights.config import IST
from insights.strategies import swing_guide


def setup(breakout=True,low_volume=False,with_today=True):
    idx=pd.bdate_range(end='2026-11-13' if with_today else '2026-11-12',
                       periods=270,tz=IST)
    close=pd.Series([100+j*.06 for j in range(len(idx))],index=idx,dtype=float)
    if breakout:close.iloc[-1]=float(close.iloc[-2])+3
    high=close+.45
    low=close-.65
    op=close-.30
    vol=[650000.]*len(idx)
    if breakout:vol[-1]=1400000
    if low_volume:vol=[1000.]*len(idx)
    stock=pd.DataFrame(dict(open=op,high=high,low=low,
                            close=close,volume=vol),index=idx)
    benchmark=pd.DataFrame(dict(close=[100+j*.025 for j in range(len(idx))]),index=idx)
    return stock,benchmark


class PDFSwingTests(unittest.TestCase):
    def test_tight_base_breakout_and_two_r_levels(self):
        f,n=setup()
        now=pd.Timestamp('2026-11-13 16:00',tz=IST)
        r=swing_guide.evaluate(f,'DEMO',now,benchmark=n)
        self.assertIn('TIGHT BASE BREAKOUT',r['matched_setups'])
        self.assertEqual(r['relative_strength'],'AVAILABLE')
        self.assertGreater(r['entry'],r['stop'])
        self.assertGreater(r['target_2r'],r['entry'])
        self.assertIsNone(r['quantity'])
        self.assertIsNone(r['win_probability'])
        swing_guide.rank([r])
        self.assertEqual(r['readiness'],'CONDITIONAL RESEARCH')
    def test_before_1540_cannot_see_current_daily_bar(self):
        f,n=setup()
        now=pd.Timestamp('2026-11-13 15:05',tz=IST)
        r=swing_guide.evaluate(f,'DEMO',now,benchmark=n)
        self.assertEqual(r['asof'],'2026-11-12')
        self.assertNotIn('TIGHT BASE BREAKOUT',r['matched_setups'])
    def test_missing_nifty_keeps_watch_not_fake_rs(self):
        f,_=setup()
        r=swing_guide.evaluate(f,'DEMO',pd.Timestamp('2026-11-13 16:00',tz=IST))
        self.assertIn('TIGHT BASE BREAKOUT',r['matched_setups'])
        self.assertIsNone(r['entry'])
        self.assertIn('UNAVAILABLE',r['relative_strength'])
    def test_turnover_floor_blocks_spurious_penny_breakout(self):
        f,n=setup(low_volume=True)
        r=swing_guide.evaluate(f,'DEMO',pd.Timestamp('2026-11-13 16:00',tz=IST),benchmark=n)
        self.assertIsNone(r['entry'])
        self.assertEqual(r['status'],'WATCH — PRICE OR TURNOVER BELOW GUIDE FLOOR')
    def test_no_lookahead_benchmark_and_data_rejections(self):
        f,n=setup()
        now=pd.Timestamp('2026-11-13 16:00',tz=IST)
        self.assertEqual(swing_guide.evaluate(None,'TEST',now)['status'],'UNAVAILABLE')
        self.assertEqual(swing_guide.evaluate(f.iloc[:80],'TEST',now)['status'],'UNAVAILABLE')
        future=n.copy();future.index=future.index+pd.Timedelta(days=1)
        # No benchmark value for the stock's latest completed date.
        result=swing_guide.evaluate(f,'DEMO',now,benchmark=future)
        self.assertIsNone(result['entry'])
    def test_bottom_rank_is_watch_only(self):
        f,n=setup()
        t=pd.Timestamp('2026-11-13 16:00',tz=IST)
        r1=swing_guide.evaluate(f,'DEMO',t,benchmark=n)
        r2=dict(r1,symbol='WEAKER',rs_score=r1['rs_score']-10)
        rows=[r1,r2]
        swing_guide.rank(rows)
        self.assertEqual(r1['readiness'],'CONDITIONAL RESEARCH')
        self.assertEqual(r2['readiness'],'WATCH')
        self.assertIsNone(r2['entry'])


if __name__=='__main__':unittest.main()
