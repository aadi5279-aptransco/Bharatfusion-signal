"""OHLCV-only SMC evidence tests: never invent order flow or trading returns."""
import unittest
from datetime import datetime
import pandas as pd
from insights import advanced_smc
from insights.config import IST


def fixtures(direction=1):
    prior_idx=pd.date_range('2026-11-11 09:15',periods=40,freq='5min',tz=IST)
    today_idx=pd.date_range('2026-11-12 09:15',periods=6,freq='5min',tz=IST)
    prior=pd.DataFrame(dict(open=[100.]*40,high=[101.]*40,low=[99.]*40,
                            close=[100.]*40,volume=[1000.]*40),index=prior_idx)
    if direction==1:
        opens=[100.,101.,101.,102.,102.,104.]
        highs=[102.,102.,103.,103.,104.,108.]
        lows=[99.,100.,100.,101.,101.,103.]
        closes=[101.,101.,102.,102.,103.,107.]
    else:
        opens=[100.,99.,99.,98.,97.,96.]
        highs=[101.,100.,100.,99.,98.,97.]
        lows=[98.,98.,97.,97.,96.,94.]
        closes=[99.,99.,98.,97.,96.,95.]
    today=pd.DataFrame(dict(open=opens,high=highs,low=lows,close=closes,
                            volume=[1000.,1000.,1200.,1500.,1700.,5000.]),index=today_idx)
    frame=pd.concat([prior,today])
    trend_values=[float(100+direction*.4*i) for i in range(65)]
    frame_htf=pd.DataFrame(dict(close=trend_values))
    return frame,frame_htf


class AdvancedSmcRules(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,12,9,45,tzinfo=IST)

    def test_buy_breakout_and_volume(self):
        five,htf=fixtures(1)
        pattern=advanced_smc.structure(five,self.now)
        self.assertTrue(pattern['up_breakout'])
        self.assertGreaterEqual(pattern['rvol'],2.0)
        selection=advanced_smc.rank_early(five,self.now)
        self.assertTrue(selection['up_breakout'])
        self.assertGreater(selection['up_score'],selection['down_score'])
        # Preconditions give 15m and 60m directional alignment.
        self.assertEqual(advanced_smc.trend(htf),'UP')

    def test_sell_breakdown_and_volume(self):
        five,htf=fixtures(-1)
        pattern=advanced_smc.structure(five,self.now)
        self.assertTrue(pattern['down_breakdown'])
        self.assertGreaterEqual(pattern['rvol'],2.0)
        self.assertEqual(advanced_smc.trend(htf),'DOWN')

    def test_reject_incomplete_early_opening_range(self):
        five,_=fixtures(1)
        # Missing 09:15 candle cannot be called an opening-range breakout.
        five=five.drop(pd.Timestamp('2026-11-12 09:15',tz=IST))
        self.assertFalse(advanced_smc.structure(five,self.now)['available'])

    def test_no_true_delta_claim_without_market_depth(self):
        five,htf=fixtures(1)
        candidate=advanced_smc.signal(five,htf,htf,'BUY','TEST',self.now,0.0,0.0)
        if candidate is not None:
            self.assertIn('UNAVAILABLE',candidate['order_flow_proxy'])
            self.assertTrue(candidate['research_only'])
            self.assertIn('UNVALIDATED',candidate['backtest_status'])

    def test_mismatched_depth_does_not_create_buy(self):
        five,htf=fixtures(1)
        candidate=advanced_smc.signal(five,htf,htf,'BUY','TEST',self.now,0.0,0.0,
            depth=dict(verified=True,bid_ask_ratio=.5))
        self.assertIsNone(candidate)


if __name__=='__main__':unittest.main()
