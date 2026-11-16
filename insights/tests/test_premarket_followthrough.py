import tempfile,unittest,threading
from pathlib import Path
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from insights.config import IST
from insights.premarket_followthrough import completed,assess,PremarketFollowthrough
NOW=datetime(2026,11,16,9,45,tzinfo=IST)
def frames(sell=False):
    times=list(pd.date_range(datetime(2026,11,12,9,15,tzinfo=IST),periods=75,freq='5min'))+list(pd.date_range(datetime(2026,11,13,9,15,tzinfo=IST),periods=75,freq='5min'))
    times=list(pd.date_range(datetime(2026,11,11,9,15,tzinfo=IST),periods=75,freq='5min'))+times
    values=[100+i*.002 for i in range(225)]+[101,101.1,101.2,101.3,102,103]
    ix=pd.DatetimeIndex(times+list(pd.date_range(NOW.replace(hour=9,minute=15),periods=6,freq='5min')))
    if sell:values=[205-v for v in values]
    f=pd.DataFrame({'open':values,'high':[v+.15 for v in values],'low':[v-.15 for v in values],'close':values,'volume':[10000]*225+[30000]*3+[100000]*3},index=ix)
    d=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':100000.},index=pd.date_range('2025-01-01','2026-11-13',freq='B',tz=IST))
    m=f.resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    return f,d,m
class MorningTests(unittest.TestCase):
    def test_no_partial_or_future_candles(self):
        f,_,_=frames();extra=f.tail(1).copy();extra.index=pd.DatetimeIndex([NOW]);g=pd.concat([f,extra])
        self.assertEqual(len(completed(g,NOW,5)),len(f))
    def test_breakout_levels_and_vital_checks(self):
        r=assess(*frames(),{'symbol':'TEST'},NOW,set());self.assertEqual(r['status'],'BREAKOUT');self.assertTrue(r['signals'])
        for s in r['signals']:self.assertLess(s['sl'],s['entry']);self.assertLess(s['entry'],s['t1']);self.assertLess(s['t1'],s['t2'])
    def test_breakdown_levels(self):
        r=assess(*frames(True),{'symbol':'TEST'},NOW,set());self.assertEqual(r['status'],'BREAKDOWN')
        for s in r['signals']:self.assertGreater(s['sl'],s['entry']);self.assertGreater(s['entry'],s['t1']);self.assertGreater(s['t1'],s['t2'])
    def test_low_liquidity_blocks_entries(self):
        f,d,m=frames();f.loc[f.index.date==NOW.date(),'volume']=1
        self.assertEqual(assess(f,d,m,{'symbol':'TEST'},NOW,set())['signals'],[])
    def test_missing_opening_bar_rejected(self):
        f,d,m=frames()
        with self.assertRaises(ValueError):assess(f.drop(f.index[-3]),d,m,{'symbol':'TEST'},NOW,set())
    def test_stale_daily_rejected(self):
        f,d,m=frames()
        with self.assertRaises(ValueError):assess(f,d.iloc[:-1],m,{'symbol':'TEST'},NOW,set())
    def test_fixed_universe_late_start_no_replay_and_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[]
            def lookup(s):calls.append(s);return {'symbol':s}
            f,d,m=frames();sv=SimpleNamespace(root=Path(root),_job_lock=threading.Lock(),_lookup=lookup,snapshot=lambda _:dict(gainers=[{'symbol':'AAA'}],losers=[{'symbol':'BBB'},{'symbol':'AAA'}],previous_session='2026-11-13'),broker=SimpleNamespace(daily=lambda *a,**k:d,history=lambda *a,**k:f if k['minutes']==5 else m))
            watch=PremarketFollowthrough(sv,lambda:set())
            with patch('insights.premarket_followthrough.assess',side_effect=lambda f,d,m,item,*args:dict(symbol=item['symbol'],status='NO CONFIRMED ENTRY',signals=[])):
                watch.run_due(NOW.replace(hour=10,minute=0));watch.run_due(NOW.replace(hour=10,minute=1))
            self.assertEqual(calls,['AAA','BBB']);self.assertEqual(list(watch.state['passes']),['10:00'])
            self.assertEqual(PremarketFollowthrough(sv,lambda:set()).state['symbols'],['AAA','BBB'])
    def test_calendar_block_and_old_watchlist(self):
        with tempfile.TemporaryDirectory() as root:
            sv=SimpleNamespace(root=Path(root),snapshot=lambda _:dict(gainers=[{'symbol':'A'}],previous_session='2026-11-12'))
            w=PremarketFollowthrough(sv,lambda:None);w.run_due(NOW);self.assertFalse(w.state['symbols'])
            w=PremarketFollowthrough(sv,lambda:set());self.assertFalse(w.freeze(NOW))
    def test_historical_results_do_not_notify(self):
        with tempfile.TemporaryDirectory() as root:
            w=PremarketFollowthrough(SimpleNamespace(root=Path(root)),lambda:set());w.state=dict(session='2026-11-16',symbols=['A'],passes={'09:45':dict(status='COMPLETE',cutoff=NOW.isoformat(),updated_at=NOW.isoformat(),signals=[{'symbol':'A'}])})
            self.assertTrue(w.snapshot(NOW)['signals']);self.assertFalse(w.snapshot(NOW+timedelta(minutes=11))['signals'])

    def test_retry_only_failed_stock(self):
        with tempfile.TemporaryDirectory() as root:
            looked=[];attempts={}
            def lookup(s):looked.append(s);return {'symbol':s}
            f,d,m=frames();sv=SimpleNamespace(root=Path(root),_job_lock=threading.Lock(),_lookup=lookup,snapshot=lambda _:dict(gainers=[{'symbol':'AAA'},{'symbol':'BBB'}],losers=[],previous_session='2026-11-13'),broker=SimpleNamespace(daily=lambda *a,**k:d,history=lambda *a,**k:f if k['minutes']==5 else m))
            def evaluate(f,d,m,item,*args):
                symbol=item['symbol'];attempts[symbol]=attempts.get(symbol,0)+1
                if symbol=='AAA' and attempts[symbol]==1:raise ValueError('Temporary source gap')
                return dict(symbol=symbol,status='NO CONFIRMED ENTRY',signals=[])
            w=PremarketFollowthrough(sv,lambda:set())
            with patch('insights.premarket_followthrough.assess',side_effect=evaluate):
                w.run_due(NOW);w.run_due(NOW+timedelta(minutes=1));w.run_due(NOW+timedelta(minutes=2))
            self.assertEqual(looked,['AAA','BBB','AAA']);self.assertEqual(len(w.state['passes']['09:45']['rows']),2)
