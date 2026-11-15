import tempfile,threading,time,unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
import pandas as pd
from insights.config import IST
from insights.positional import daily_setups,features,wilder,assess,setup,completed_five,r1_setups,PositionalScanner

NOW=datetime(2026,11,13,16,tzinfo=IST)
ITEM=dict(id='1',symbol='TEST',ticker='TEST',kind='stock',segment='NSE_EQ',instrument='EQUITY')
def bars(values,end='2026-11-13'):
    c=np.array(values,dtype=float);idx=pd.bdate_range(end=end,periods=len(c),tz=IST)
    return pd.DataFrame(dict(open=c-.5,high=c+1,low=c-1,close=c,volume=200000.),index=idx)
def five(now,price=100,low=99.8,high=100.2):
    idx=pd.date_range(pd.Timestamp(now).normalize()+pd.Timedelta(hours=9,minutes=15),pd.Timestamp(now)-pd.Timedelta(minutes=5),freq='5min')
    return pd.DataFrame(dict(open=price,high=high,low=low,close=price,volume=5000.),index=idx)
def row():
    return setup(ITEM,'Test',pd.Timestamp('2026-11-12',tz=IST),100,97,'test','5 days')
class StrategyTests(unittest.TestCase):
    def test_wilder_seed_and_recurrence(self):
        s=wilder(pd.Series([1.,2.,3.,4.]),3)
        self.assertTrue(pd.isna(s.iloc[1]));self.assertEqual(s.iloc[2],2);self.assertAlmostEqual(s.iloc[3],8/3)
    def test_supertrend_and_rsi_known_trend(self):
        f=features(bars(np.linspace(100,180,220)))
        self.assertEqual(f.rsi.iloc[-1],100);self.assertTrue(f.bull.iloc[-1]);self.assertLess(f.supertrend.iloc[-1],f.close.iloc[-1])
        f=features(bars(np.linspace(180,100,220)))
        self.assertEqual(f.rsi.iloc[-1],0);self.assertFalse(f.bull.iloc[-1]);self.assertGreater(f.supertrend.iloc[-1],f.close.iloc[-1])
    def test_pdf_momentum_exact_volume_and_stop(self):
        f=bars(np.linspace(100,180,220));f.iloc[-1,f.columns.get_loc('volume')]=300000
        rows,_=daily_setups(f,ITEM,NOW,set());r=next(r for r in rows if r['strategy']=='PDF Supertrend + RSI')
        self.assertEqual(r['sl'],round(r['entry']*.97,2));self.assertEqual(r['risk_pct'],3)
        f.iloc[-1,f.columns.get_loc('volume')]=200000
        self.assertNotIn('PDF Supertrend + RSI',[r['strategy'] for r in daily_setups(f,ITEM,NOW,set())[0]])
    def test_morning_star_and_weak_confirmation(self):
        f=bars(np.linspace(150,100,60));f.iloc[-3]=[100,101,95,96,200000];f.iloc[-2]=[95.8,96.5,95,96,200000];f.iloc[-1]=[96,100,95.5,99,300000]
        rows,_=daily_setups(f,ITEM,NOW,set());r=next(r for r in rows if r['strategy']=='PDF Morning Star')
        self.assertEqual(r['sl'],94.91);self.assertLess(r['sl'],r['entry']);self.assertGreater(r['t2'],r['t1'])
        f.iloc[-1]=[96,98,95.5,97,300000]
        self.assertNotIn('PDF Morning Star',[r['strategy'] for r in daily_setups(f,ITEM,NOW,set())[0]])
    def test_donchian_excludes_current_high(self):
        f=bars(np.linspace(100,180,220));f.iloc[-1]=[180,185,179,184,400000]
        rows,_=daily_setups(f,ITEM,NOW,set());self.assertIn('Donchian 20D breakout',[r['strategy'] for r in rows])
        f.iloc[-1,f.columns.get_loc('volume')]=100000
        self.assertNotIn('Donchian 20D breakout',[r['strategy'] for r in daily_setups(f,ITEM,NOW,set())[0]])
    def test_future_and_unfinished_daily_candles_excluded(self):
        f=bars(np.linspace(100,180,220));future=f.iloc[[-1]].copy();future.index=future.index+pd.Timedelta(days=3)
        _,d=daily_setups(pd.concat([f,future]),ITEM,NOW.replace(hour=10),set())
        self.assertEqual(d.index[-1].date().isoformat(),'2026-11-12')
    def test_stale_unknown_and_invalid_fail_closed(self):
        f=bars(np.linspace(100,180,220))
        with self.assertRaises(ValueError):daily_setups(f.iloc[:-1],ITEM,NOW,set())
        with self.assertRaises(ValueError):daily_setups(f,ITEM,NOW,None)
        f.iloc[-1,0]=float('inf')
        with self.assertRaises(ValueError):daily_setups(f,ITEM,NOW,set())
    def test_liquidity_filter(self):
        f=bars(np.linspace(100,180,220));f['volume']=100
        self.assertEqual(daily_setups(f,ITEM,NOW,set())[0],[])
    def test_missing_long_history_no_extra_signal(self):
        f=bars(np.linspace(100,180,60));f.iloc[-1]=[180,185,179,184,400000]
        self.assertNotIn('Donchian 20D breakout',[r['strategy'] for r in daily_setups(f,ITEM,NOW,set())[0]])
    def test_levels_reject_excessive_risk(self):
        self.assertIsNone(setup(ITEM,'X',pd.Timestamp(NOW),100,80,'',''))
        self.assertIsNone(setup(ITEM,'X',pd.Timestamp(NOW),100,97,'','',t1=105,t2=104))
    def test_price_readiness_and_invalidation(self):
        now=NOW.replace(hour=10,minute=0);f=five(now)
        self.assertEqual(assess(row(),f,now,set())['status'],'READY — REVIEW ENTRY')
        f.iloc[0,f.columns.get_loc('low')]=96
        self.assertEqual(assess(row(),f,now,set())['status'],'INVALIDATED — SL TOUCHED')
    def test_stale_gap_and_chase_prices(self):
        now=NOW.replace(hour=10,minute=0);f=five(now)
        self.assertEqual(assess(row(),f.iloc[:-3],now,set())['status'],'STALE PRICE')
        self.assertEqual(assess(row(),f.iloc[1:],now,set())['status'],'INCOMPLETE PRICE HISTORY')
        f=five(now,102,101.8,102.2)
        self.assertEqual(assess(row(),f,now,set())['status'],'EXTENDED — DO NOT CHASE')
    def test_target_touch_and_closed_market(self):
        now=NOW.replace(hour=10,minute=0);f=five(now);f.iloc[0,f.columns.get_loc('high')]=108
        self.assertEqual(assess(row(),f,now,set())['status'],'T2 ALREADY TOUCHED')
        self.assertEqual(assess(row(),f,NOW,set())['status'],'CLOSED — REVIEW NEXT SESSION')
    def test_incomplete_five_candle_removed(self):
        now=NOW.replace(hour=10,minute=0);f=five(now+timedelta(minutes=5))
        self.assertEqual(completed_five(f,now).index[-1].minute,55)
    def test_r1_outside_entry_window(self):
        self.assertEqual(r1_setups(bars(np.linspace(100,180,220)),None,ITEM,NOW,set()),[])

    def test_moving_momentum_sequence(self):
        f=bars(np.r_[np.linspace(100,200,220),np.linspace(199,195,10),np.linspace(195.2,202,5)])
        rows,_=daily_setups(f,ITEM,NOW,set())
        self.assertIn('Moving Momentum',[r['strategy'] for r in rows])
        # A trend without the prior oversold pullback cannot pass.
        f=bars(np.linspace(100,202,235))
        self.assertNotIn('Moving Momentum',[r['strategy'] for r in daily_setups(f,ITEM,NOW,set())[0]])
    def test_r1_completed_cross_and_missing_bar(self):
        idx=pd.DatetimeIndex([t for day in pd.bdate_range(end='2026-11-13',periods=4,tz=IST)
            for t in pd.date_range(day+pd.Timedelta(hours=9,minutes=15),periods=75 if day.date().isoformat()!='2026-11-13' else 6,freq='5min')])
        c=np.linspace(90,109,len(idx));f=pd.DataFrame(dict(open=c,high=c+.2,low=c-.2,close=c,volume=10000),index=idx)
        f.iloc[-6:-3]=[109,109.2,108.8,109,10000];f.iloc[-3:]=[112,112.3,111.8,112.1,10000]
        d=bars(np.linspace(90,108,60),end='2026-11-12');d.iloc[-1]=[108,110,100,108,200000]
        now=NOW.replace(hour=9,minute=45)
        rows=r1_setups(d,f,ITEM,now,set());self.assertEqual(len(rows),1)
        r=rows[0];self.assertEqual(r['strategy'],'PDF R1 + Supertrend');self.assertAlmostEqual(r['t2'],116)
        self.assertEqual(r1_setups(d,f.iloc[:-1],ITEM,now,set()),[])
        def mirror(frame):
            m=frame.copy();m['open']=220-frame.open;m['close']=220-frame.close
            m['high']=220-frame.low;m['low']=220-frame.high
            return m
        short=r1_setups(mirror(d),mirror(f),ITEM,now,set())
        self.assertEqual(len(short),1);self.assertEqual(short[0]['side'],'SELL')
        self.assertLess(short[0]['t2'],short[0]['t1']);self.assertGreater(short[0]['sl'],short[0]['entry'])

    def test_pdf_watch_expiry_and_prior_daily_stop(self):
        from insights.positional import carry_daily
        r=row();r['strategy']='PDF Morning Star';r['signal_at']='2026-11-06T00:00:00+05:30'
        d=features(bars(np.full(40,100.)));d=d[d.index.date<=NOW.date()]
        # Four daily bars after signal (exclude the known exchange holiday).
        d=d[d.index.date!=datetime(2026,11,10).date()]
        got=carry_daily([], [r],d,ITEM)[0]
        self.assertEqual(got['tracking_status'],'TRACK ONLY — OLDER SIGNAL')
        d.loc[d.index[-1],'low']=96
        self.assertEqual(carry_daily([], [r],d,ITEM)[0]['tracking_status'],'INVALIDATED — DAILY SL TOUCHED')
        r['signal_at']='2026-11-05T00:00:00+05:30'
        self.assertEqual(carry_daily([], [r],d,ITEM)[0]['tracking_status'],'FIVE-SESSION WATCH EXPIRED')

class Broker:
    def __init__(self):self.daily_calls=0;self.history_calls=0;self.fail=False
    def configured(self):return True
    def instruments(self):return [ITEM]
    def daily(self,*args,**kwargs):
        self.daily_calls+=1
        if self.fail:raise ValueError('source unavailable')
        f=bars(np.linspace(100,180,220),end='2026-11-12');f.iloc[-1,f.columns.get_loc('volume')]=300000;return f
    def history(self,item,now,**kwargs):self.history_calls+=1;return five(now,180,179.8,180.2)
class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.b=Broker();self.s=PositionalScanner(self.b,self.temp.name,lambda:set(),threading.Lock(),watchlist=[]);self.now=NOW.replace(hour=10,minute=0)
    def tearDown(self):self.s.stop();self.temp.cleanup()
    def test_reuses_daily_but_rechecks_5m(self):
        self.s._run(self.now);self.s._run(self.now+timedelta(minutes=5))
        # Legacy daily + EMA9 long daily are each fetched once; hourly once plus two 5m checks.
        self.assertEqual(self.b.daily_calls,2);self.assertEqual(self.b.history_calls,3)
        self.assertEqual(self.s.snapshot()['coverage']['scanned'],1)
    def test_failed_scan_invalidates_previous_rows(self):
        self.s._run(self.now);self.s.holidays=lambda:None;self.s._run(self.now)
        r=self.s.snapshot();self.assertTrue(r['stale']);self.assertEqual(r['refresh']['status'],'FAILED')
        self.assertTrue(all(x['status']=='STALE SCAN — DO NOT USE' for x in r['rows']))
    def test_five_minute_schedule_and_no_overlap(self):
        event=threading.Event()
        with patch.object(self.s,'_run',side_effect=lambda now:event.wait(2)):
            self.assertEqual(self.s.request(self.now)['status'],'STARTED')
            self.assertEqual(self.s.request(self.now)['status'],'BUSY');event.set();self.s._worker.join(3)
            self.assertEqual(self.s.request(self.now+timedelta(minutes=4))['status'],'WAITING FOR NEXT FIVE-MINUTE CYCLE')
            self.assertEqual(self.s.request(self.now+timedelta(minutes=5))['status'],'STARTED');self.s._worker.join(3)
    def test_cancel_lock_wait(self):
        self.s._deadline=time.monotonic()+240;self.s.stop()
        with self.assertRaises(TimeoutError):self.s._call(lambda:None)
    def test_get_is_cached_and_post_same_origin(self):
        from insights.api import create_app
        c=create_app(SimpleNamespace(positional_scanner=self.s)).test_client()
        self.assertEqual(c.get('/api/v1/market-insights/positional').status_code,200)
        self.assertEqual(self.b.daily_calls,0)
        self.assertEqual(c.post('/api/v1/market-insights/positional/refresh',headers={'Origin':'https://evil.example'}).status_code,403)
