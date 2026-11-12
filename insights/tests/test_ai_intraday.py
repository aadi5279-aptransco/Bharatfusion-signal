"""Exact 8 daily + 3 15m query and explainable top-10 risk model tests.

Fixtures are synthetic OHLCV only. No broker, no ML training, no fills.
"""
import unittest
from datetime import datetime
import pandas as pd
from insights.config import IST
from insights.strategies import momentum_query
from insights import ai_rank


NOW=datetime(2026,11,12,10,15,tzinfo=IST)


def daily_bars(direction=1):
    idx=pd.date_range(end='2026-11-11',periods=45,freq='B',tz=IST)
    c=pd.Series([115+direction*.13*i for i in range(45)],index=idx)
    return pd.DataFrame({'open':c-.1,'high':c+.55,'low':c-.55,
        'close':c,'volume':[800000]*45},index=idx)


def five_bars(direction=1,volume=1300000):
    old=pd.date_range('2026-11-11 09:15',periods=25,freq='5min',tz=IST)
    now=pd.date_range('2026-11-12 09:15',periods=12,freq='5min',tz=IST)
    today_start=124 if direction==1 else 107
    old_c=[116.]*25 if direction==1 else [114.]*25
    today_c=[today_start+direction*.45*i for i in range(12)]
    close=pd.Series(old_c+today_c,index=old.append(now),dtype=float)
    opens=close.copy()
    opens.iloc[25:]=[x-.15*direction for x in today_c]
    if direction==1:opens.iloc[25]=123
    else:opens.iloc[25]=108
    return pd.DataFrame({'open':opens,
       'high':pd.concat([opens,close],axis=1).max(axis=1)+.2,
       'low':pd.concat([opens,close],axis=1).min(axis=1)-.2,
       'close':close,'volume':[100000]*25+[volume]*12},index=close.index)


def fifteen_bars(direction=1,large=True):
    idx=pd.date_range(end='2026-11-12 10:00',periods=46,freq='15min',tz=IST)
    close=pd.Series([114+direction*.18*i for i in range(46)],index=idx)
    vol=[1000000.]*45+[5000000. if large else 1000000.]
    return pd.DataFrame({'open':close-.1,'high':close+.6,
        'low':close-.6,'close':close,'volume':vol},index=idx)


class MomentumQueryTests(unittest.TestCase):
    def test_buy_needs_all_daily_and_15m_rules(self):
        f=five_bars(1);d=daily_bars(1);h=fifteen_bars(1)
        day=momentum_query.daily_gate(f,d,NOW,'BUY')
        self.assertIsNotNone(day)
        self.assertTrue(day['pass_all'],day['checks'])
        self.assertEqual(len(day['checks']),8)
        self.assertEqual(day['daily_status'].startswith('PROVISIONAL'),True)
        quarter=momentum_query.fifteen_gate(h,NOW,'BUY')
        self.assertTrue(quarter['pass_all'],quarter['checks'])
        self.assertEqual(len(quarter['checks']),3)
        self.assertFalse(momentum_query.daily_gate(f,d,NOW,'SELL')['pass_all'])

    def test_sell_requires_downside_and_volume(self):
        f=five_bars(-1);d=daily_bars(-1);h=fifteen_bars(-1)
        daily=momentum_query.daily_gate(f,d,NOW,'SELL')
        self.assertTrue(daily['pass_all'],daily['checks'])
        self.assertTrue(momentum_query.fifteen_gate(h,NOW,'SELL')['pass_all'])
        low_volume=five_bars(-1,volume=5000)
        self.assertFalse(momentum_query.daily_gate(low_volume,d,NOW,'SELL')['pass_all'])
        self.assertFalse(momentum_query.fifteen_gate(fifteen_bars(-1,False),NOW,'SELL')['pass_all'])

    def test_missing_and_stale_market_data_never_pass(self):
        f=five_bars(1);d=daily_bars(1)
        self.assertIsNone(momentum_query.daily_gate(f.iloc[:-5],d,NOW,'BUY'))
        self.assertIsNone(momentum_query.daily_gate(f,d.iloc[:15],NOW,'BUY'))
        h=fifteen_bars(1)
        self.assertIsNone(momentum_query.fifteen_gate(h.iloc[:-4],NOW,'BUY'))


class RankingTests(unittest.TestCase):
    def test_ranked_trade_has_bounded_stop_and_conditional_entry(self):
        f=five_bars(1);d=daily_bars(1);h=fifteen_bars(1)
        candidate=momentum_query.candidate(f,d,h,'DEMO',NOW,'BUY')
        self.assertIsNotNone(candidate)
        x=ai_rank.assess(candidate,f,h)
        self.assertIsNotNone(x)
        self.assertGreater(x['entry'],x['sl'])
        self.assertGreater(x['t1'],x['entry'])
        self.assertLessEqual(x['stop_distance_pct'],2)
        self.assertIn('NOT A FILL',x['entry_type'])
        self.assertIn('NOT TRAINED ML',x['score_type'])
        self.assertEqual(x['backtest_status'],'UNVALIDATED')

    def test_top_ten_sorted_and_no_forced_fill(self):
        items=[{'symbol':'S'+str(i),'direction':'BUY','ai_score':i+1,
             'stop_distance_pct':1,'daily_volume_ratio':2} for i in range(15)]
        best=ai_rank.top_ten(items)
        self.assertEqual(len(best),10)
        self.assertEqual(best[0]['ai_score'],15)
        self.assertEqual(ai_rank.top_ten([]),[])


if __name__=='__main__':unittest.main()
