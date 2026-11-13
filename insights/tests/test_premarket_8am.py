"""08:00 previous-session stock watchlist, causal daily data and scheduling."""
import tempfile
import unittest
from unittest.mock import Mock,patch
from datetime import datetime
import pandas as pd
from insights.config import IST
from insights.strategies import premarket
from insights.service import InsightsService


def daily():
    idx=pd.date_range(end='2026-11-12',periods=85,freq='B',tz=IST)
    prices=[100+i*.35 for i in range(len(idx))]
    return pd.DataFrame(dict(open=[x-.2 for x in prices],
        high=[x+.5 for x in prices],low=[x-.6 for x in prices],
        close=prices,volume=[100000.]*85),index=idx)


class MockDailyBroker:
    def configured(self):return True
    def instruments(self):return [
        dict(symbol='GAIN',kind='stock',id='101',segment='NSE_EQ'),
        dict(symbol='LOSS',kind='stock',id='102',segment='NSE_EQ')]
    def daily(self,item,now,days=180):
        frame=daily()
        if item['symbol']=='LOSS':
            frame=frame.copy()
            frame.loc[frame.index[-1],'close']=frame.close.iloc[-2]-4
            frame.loc[frame.index[-1],'low']=frame.low.iloc[-2]-5
            frame.loc[frame.index[-1],'high']=frame.high.iloc[-2]
            frame.loc[frame.index[-1],'open']=frame.open.iloc[-2]
        return frame


class PreMarketTests(unittest.TestCase):
    def test_previous_completed_daily_no_future_leak(self):
        f=daily()
        future=f.iloc[-1:].copy()
        future.index=pd.DatetimeIndex(['2026-11-13T00:00:00+05:30']).tz_convert(IST)
        future.loc[future.index[0],'close']=1000
        future.loc[future.index[0],'high']=1001
        x=premarket.evaluate(pd.concat([f,future]),'GAIN',
            datetime(2026,11,13,8,0,tzinfo=IST))
        self.assertEqual(x['previous_session'],'2026-11-12')
        self.assertLess(x['close'],1000)
        self.assertIsNone(x.get('entry'))
    def test_morning_scan_ranks_both_directional_sides(self):
        with tempfile.TemporaryDirectory() as folder:
            svc=InsightsService(MockDailyBroker(),folder)
            with patch('insights.service._holiday_set',return_value=set()):
                out=svc.scan_premarket(datetime(2026,11,13,8,0,tzinfo=IST))
            self.assertEqual(out['assessed'],2)
            self.assertEqual(out['previous_session'],'2026-11-12')
            self.assertEqual(out['gainers'][0]['symbol'],'GAIN')
            self.assertEqual(out['losers'][0]['symbol'],'LOSS')
            self.assertEqual(svc.journal.signals(),[])
    def test_premarket_schedules_at_8_not_weekends(self):
        with tempfile.TemporaryDirectory() as folder:
            svc=InsightsService(MockDailyBroker(),folder)
            svc.scan_premarket=Mock(return_value=dict(assessed=2))
            with patch('insights.service._holiday_set',return_value=set()):
                self.assertIn('BLOCKED',svc.run_due(datetime(2026,11,13,7,59,tzinfo=IST))['status'])
                self.assertEqual(svc.run_due(datetime(2026,11,13,8,0,tzinfo=IST))['status'],'PRE-MARKET WATCHLIST COMPLETE')
                self.assertEqual(svc.run_due(datetime(2026,11,13,8,5,tzinfo=IST))['status'],'PRE-MARKET WATCHLIST ALREADY COMPLETE')
                self.assertIn('BLOCKED',svc.run_due(datetime(2026,11,14,8,0,tzinfo=IST))['status'])
            svc.scan_premarket.assert_called_once()
    def test_after_close_cache_reloads_at_8am_without_requery(self):
        with tempfile.TemporaryDirectory() as folder:
            end=datetime(2026,11,12,16,0,tzinfo=IST)
            first=InsightsService(MockDailyBroker(),folder)
            with patch('insights.service._holiday_set',return_value=set()):
                prepared=first.scan_premarket(end)
                self.assertEqual(prepared['previous_session'],'2026-11-12')
                restored=InsightsService(MockDailyBroker(),folder)
                self.assertEqual(restored.snapshot('pre-market')['assessed'],2)
                restored.scan_premarket=Mock()
                response=restored.run_due(datetime(2026,11,13,8,0,tzinfo=IST))
                self.assertEqual(response['status'],'PRE-MARKET WATCHLIST READY FROM PRIOR CLOSE')
                restored.scan_premarket.assert_not_called()

    def test_no_lookahead_at_early_session_even_if_daily_has_today(self):
        f=daily();now=datetime(2026,11,13,8,0,tzinfo=IST)
        x=premarket.evaluate(f,'GAIN',now)
        self.assertEqual(x['status'],'PRE-MARKET WATCH — NOT A TRADE')
        self.assertIn('20',str(x['reasons']))
        self.assertNotIn('probability',x)


if __name__=='__main__':unittest.main()
