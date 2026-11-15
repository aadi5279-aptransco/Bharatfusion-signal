import tempfile,threading,unittest
from datetime import datetime,timedelta
from unittest.mock import patch
import numpy as np
import pandas as pd
from insights.config import IST
from insights.strategies.ema9_trendline import check_signal,descending_trendline,completed,hourly_close,make_row,EMA9Scanner

NOW=datetime(2026,11,13,16,tzinfo=IST)
ITEM=dict(id='1',segment='NSE_EQ',symbol='TEST',kind='stock')
def breakout():
    n=80;c=np.full(n,95.);h=np.linspace(100,96,n);lo=np.full(n,94.)
    h[40]=110;h[60]=105
    # Line at 78=100.5, at 79=100.25. Confirmed pivot 60 is old enough.
    c[-2]=100.;c[-1]=101.;h[-2]=100.2;h[-1]=101.2
    idx=pd.bdate_range(end='2026-11-13',periods=n,tz=IST)
    f=pd.DataFrame(dict(open=c,high=np.maximum(h,c),low=lo,close=c,volume=200000.),index=idx)
    f.iloc[-1,f.columns.get_loc('volume')]=310000
    return f
class SignalTests(unittest.TestCase):
    def test_prior_volume_and_stop_excludes_signal(self):
        f=breakout();f.iloc[-1,f.columns.get_loc('low')]=80
        r=check_signal(f);self.assertIsNotNone(r)
        self.assertAlmostEqual(r['volume_ratio'],1.55);self.assertEqual(r['sl'],94)
        self.assertEqual(r['t2'],122);self.assertEqual(r['t1'],111.5)
    def test_strict_volume_boundary(self):
        f=breakout();f.iloc[-1,f.columns.get_loc('volume')]=300000
        self.assertIsNone(check_signal(f))
    def test_prior_close_above_line_does_not_repeat(self):
        f=breakout();f.iloc[-2]=[100.6,100.8,94,100.6,200000]
        self.assertIsNone(check_signal(f))
    def test_unconfirmed_pivot_cannot_change_line(self):
        f=breakout();before=descending_trendline(f.high.to_numpy())
        f.iloc[-3,f.columns.get_loc('high')]=200
        self.assertEqual(descending_trendline(f.high.to_numpy()),before)
    def test_equal_or_higher_pivot_resets_chain(self):
        f=breakout();f.iloc[60,f.columns.get_loc('high')]=110
        self.assertIsNone(descending_trendline(f.high.to_numpy())[0]);self.assertIsNone(check_signal(f))
    def test_minimum_history_zero_volume_and_risk(self):
        f=breakout();self.assertIsNone(check_signal(f.tail(59)))
        f.iloc[30,f.columns.get_loc('volume')]=0
        with self.assertRaises(ValueError):check_signal(f)
        f=breakout();f['low']=70;self.assertIsNone(check_signal(f))
    def test_future_suffix_does_not_change_prefix_result(self):
        f=breakout();r=check_signal(f)
        later=f.iloc[[-1]].copy();later.index=later.index+pd.Timedelta(days=3);later['high']=200
        full=pd.concat([f,later]);self.assertEqual(r,check_signal(full.iloc[:80]))
    def test_row_timeframe_identity_and_target_basis(self):
        f=breakout();r=make_row(f,ITEM,'1D')
        self.assertIn('1D',r['key']);self.assertEqual(r['trade_type'],'POSITIONAL')
        self.assertIn('UNVERIFIED',r['adjustment_status']);self.assertIn('3R',r['target_basis'])

    def test_post_signal_path_needs_every_completed_bar(self):
        from insights.strategies.ema9_trendline import price_path_complete
        now=NOW.replace(hour=11,minute=0)
        idx=pd.date_range('2026-11-13 10:15',periods=9,freq='5min',tz=IST)
        f=pd.DataFrame({'close':100},index=idx);r={'signal_end':'2026-11-13T10:15:00+05:30'}
        self.assertTrue(price_path_complete(r,f,now,set()))
        self.assertFalse(price_path_complete(r,f.drop(idx[3]),now,set()))

class PeriodTests(unittest.TestCase):
    def daily(self):
        idx=pd.bdate_range('2016-01-01','2026-11-30',tz=IST)
        return pd.DataFrame(dict(open=100.,high=101.,low=99.,close=100.,volume=200000.),index=idx)
    def test_daily_drops_today_before_close(self):
        f=completed(self.daily(),'1D',NOW.replace(hour=10),set())
        self.assertEqual(f.index[-1].date().isoformat(),'2026-11-12')
    def test_weekly_monthly_drop_forming_periods(self):
        d=self.daily();w=completed(d,'1W',NOW.replace(hour=10),set());m=completed(d,'1M',NOW,set())
        self.assertEqual(w.index[-1].date().isoformat(),'2026-11-06')
        self.assertEqual(m.index[-1].date().isoformat(),'2026-10-31')
        w=completed(d,'1W',NOW,set());self.assertEqual(w.index[-1].date().isoformat(),'2026-11-13')
        self.assertEqual(w.volume.iloc[-1],1000000)
    def test_friday_holiday_week_finishes_thursday(self):
        d=self.daily();d=d[d.index.date!=NOW.date()]
        thursday=NOW-timedelta(days=1);f=completed(d,'1W',thursday,{'2026-11-13'})
        self.assertEqual(f.index[-1].date().isoformat(),'2026-11-13')
        self.assertTrue(f.attrs['last_closed_at'].startswith('2026-11-12'))
    def test_hourly_close_and_session_stub(self):
        idx=pd.date_range('2026-11-13 09:15',periods=7,freq='h',tz=IST)
        f=pd.DataFrame(dict(open=100.,high=101.,low=99.,close=100.,volume=100000.),index=idx)
        out=completed(f,'1H',NOW,set());self.assertEqual(len(out),6);self.assertEqual(out.index[-1].hour,14)
        out=completed(f,'1H',NOW.replace(hour=11,minute=14),set());self.assertEqual(len(out),1)
        self.assertEqual(hourly_close(NOW.replace(hour=11,minute=15),set()).hour,11)
    def test_hourly_gap_rejected(self):
        idx=pd.date_range('2026-11-13 09:15',periods=6,freq='h',tz=IST)
        f=pd.DataFrame(dict(open=100.,high=101.,low=99.,close=100.,volume=100000.),index=idx).drop(idx[2])
        with self.assertRaises(ValueError):completed(f,'1H',NOW,set())
    def test_stale_and_unknown_calendar(self):
        with self.assertRaises(ValueError):completed(self.daily().loc[:'2026-11-12'],'1D',NOW,set())
        with self.assertRaises(ValueError):completed(self.daily(),'1D',NOW,None)
    def test_cache_and_timeframe_coverage(self):
        class Broker:
            calls=[]
            def daily(self,*a,**k):self.calls.append('daily');return breakout()
            def history(self,*a,**k):self.calls.append('hourly');raise ValueError('Unavailable')
        b=Broker();s=EMA9Scanner(b,lambda fn:fn())
        rows,checks=s.scan(ITEM,NOW,set());self.assertEqual(len(checks),4)
        self.assertTrue(any(c['timeframe']=='1M' and 'INSUFFICIENT' in c['status'] for c in checks))
        s.scan(ITEM,NOW+timedelta(minutes=5),set());self.assertEqual(b.calls.count('daily'),1)
        self.assertEqual(len({r['key'] for r in rows}),len(rows))
