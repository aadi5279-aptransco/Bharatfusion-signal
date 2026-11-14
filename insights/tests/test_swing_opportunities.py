"""Offline swing finder: 20-day breakout, causal daily/weekly bars, no order path."""
import math
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch
import pandas as pd
from insights.config import IST
from insights.strategies import swing_opportunities
from insights.service import InsightsService


def daily_fixture():
    index=pd.bdate_range(end='2026-11-13',periods=340,tz=IST)
    closes=[100+0.09*j+1.6*math.sin(j/3) for j in range(len(index))]
    close=pd.Series(closes,index=index)
    df=pd.DataFrame(dict(open=close-.2,high=close+.7,
        low=close-.85,close=close,volume=[125000.]*len(index)),index=index)
    # Late breakout and volume surge; no future candle in this fixture.
    prior_high=float(df.high.iloc[-21:-1].max())
    previous=float(df.close.iloc[-2])
    df.iloc[-1,df.columns.get_loc('close')]=max(prior_high+1.6,previous+1.2)
    last=float(df.close.iloc[-1])
    df.iloc[-1,df.columns.get_loc('open')]=last-.9
    df.iloc[-1,df.columns.get_loc('high')]=last+.5
    df.iloc[-1,df.columns.get_loc('low')]=last-1.1
    df.iloc[-1,df.columns.get_loc('volume')]=300000
    return df


class SwingFinderTests(unittest.TestCase):
    def setUp(self):
        self.frame=daily_fixture()
        self.asof=datetime(2026,11,13,16,0,tzinfo=IST)
    def test_breakout_ready_with_next_session_trigger_and_risk_levels(self):
        result=swing_opportunities.evaluate(self.frame,'DEMO',self.asof)
        self.assertEqual(result['setup'],'20-DAY BREAKOUT')
        self.assertEqual(result['readiness'],'READY')
        self.assertGreater(result['entry'],result['close'])
        self.assertLess(result['stop'],result['entry'])
        self.assertGreater(result['target_3r'],result['target'])
        self.assertEqual(result['risk_reward'],2)
        self.assertIsNone(result['probability_of_win'])
    def test_current_incomplete_day_never_qualifies(self):
        at=datetime(2026,11,13,15,0,tzinfo=IST)
        result=swing_opportunities.evaluate(self.frame,'DEMO',at)
        self.assertNotEqual(result['readiness'],'READY')
        self.assertIsNone(result['entry'])
        self.assertNotEqual(result['reference_date'],'2026-11-13')
    def test_future_daily_bar_cannot_change_previous_confirmed_signal(self):
        clean=swing_opportunities.evaluate(self.frame,'DEMO',self.asof)
        future=self.frame.iloc[-1:].copy()
        future.index=pd.DatetimeIndex(['2026-11-16T00:00:00+05:30'])
        future.loc[future.index[0],'close']=5000
        future.loc[future.index[0],'high']=5001
        future.loc[future.index[0],'low']=4999
        future.loc[future.index[0],'open']=5000
        altered=swing_opportunities.evaluate(pd.concat([self.frame,future]),'DEMO',self.asof)
        self.assertEqual(clean['entry'],altered['entry'])
        self.assertEqual(clean['score'],altered['score'])
    def test_missing_history_or_invalid_ohlc_never_gives_trade(self):
        first=swing_opportunities.evaluate(self.frame.head(35),'DEMO',self.asof)
        self.assertEqual(first['status'],'UNAVAILABLE')
        self.assertIsNone(first['entry'])
        broken=self.frame.copy()
        broken.loc[broken.index[-2],'high']=0.
        result=swing_opportunities.evaluate(broken,'DEMO',self.asof)
        self.assertIsNone(result['entry'])
        self.assertEqual(result['status'],'UNAVAILABLE')
    def test_utc_index_preserves_exchange_session_and_weekly_buckets(self):
        clean=swing_opportunities.evaluate(self.frame,'DEMO',self.asof)
        converted=swing_opportunities.evaluate(self.frame.tz_convert('UTC'),'DEMO',self.asof)
        self.assertEqual(clean,converted)
    def test_mixed_index_rejects_naive_and_duplicate_instants(self):
        for stamp in (self.frame.index[-1].tz_localize(None),
                      self.frame.index[-1].tz_convert('UTC')):
            extra=self.frame.iloc[-1:].copy()
            extra.index=pd.Index([stamp])
            result=swing_opportunities.evaluate(pd.concat([self.frame,extra]),'DEMO',self.asof)
            self.assertEqual(result['status'],'UNAVAILABLE')
            self.assertIsNone(result['entry'])
    def test_watch_state_never_invents_stop_or_targets(self):
        frame=self.frame.copy()
        last=frame.index[-1]
        frame.loc[last,'close']=frame.close.iloc[-2]
        frame.loc[last,'high']=frame.high.iloc[-2]
        frame.loc[last,'low']=frame.low.iloc[-2]
        frame.loc[last,'open']=frame.open.iloc[-2]
        frame.loc[last,'volume']=100000
        out=swing_opportunities.evaluate(frame,'DEMO',self.asof)
        self.assertNotEqual(out['readiness'],'READY')
        self.assertIsNone(out['entry'])
        self.assertIsNone(out['target'])
    def test_existing_strict_swing_scan_remains_separate(self):
        from insights.strategies import swing
        before=swing.scan(self.frame,'DEMO',self.asof)
        output=swing_opportunities.evaluate(self.frame,'DEMO',self.asof)
        after=swing.scan(self.frame,'DEMO',self.asof)
        self.assertEqual(before,after)
        self.assertNotIn('original_strict_signal_overwrite',output)
    def test_completed_longterm_scan_contains_new_ready_watch_arrays(self):
        class DailyBroker:
            def configured(self):return True
            def longterm_instruments(self):
                return [dict(symbol='DEMO',id='123',kind='stock',
                             segment='NSE_EQ',instrument='EQUITY')]
            def daily(self,item,now,days=1300):return daily_fixture()
        with tempfile.TemporaryDirectory() as folder:
            svc=InsightsService(DailyBroker(),folder)
            with patch('insights.service.multibagger.evaluate',return_value=None):
                result=svc.scan_longterm(self.asof)
            data=svc.snapshot('swing-trades')
            self.assertEqual(data['status'],'DAILY SWING RESEARCH COMPLETE')
            self.assertIn('opportunity_ready',data)
            self.assertIn('opportunity_watch',data)
            self.assertEqual(result['swing_opportunity_ready'],len(data['opportunity_ready']))
            self.assertFalse(svc.health()['orders_enabled'])


if __name__=='__main__':unittest.main()

