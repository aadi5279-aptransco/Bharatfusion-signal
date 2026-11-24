import unittest
from datetime import datetime,timedelta
from unittest.mock import Mock,patch
import threading
import pandas as pd
from patterns.tests.test_engine import engulfing
from insights.config import IST
from insights.pattern_engine import evidence,bars_from_frame,inspect

NOW=datetime(2026,11,23,12,tzinfo=IST)
def frame(index):
    return pd.DataFrame(dict(open=100.,high=101.,low=99.,close=100.,volume=100000.),index=index)

class PatternAdapterTests(unittest.TestCase):
    def test_partial_day_week_month_not_used(self):
        f=frame(pd.date_range('2026-10-01','2026-11-23',freq='B',tz=IST))
        daily=bars_from_frame(f,'daily',NOW,set())
        self.assertEqual(daily[-1].time.date().isoformat(),'2026-11-20')
        weekly=bars_from_frame(f,'weekly',NOW,set())
        self.assertEqual(weekly[-1].closed_at.date().isoformat(),'2026-11-23')
        self.assertEqual(len(weekly),7) # Initial partial week not aggregated.
        monthly=bars_from_frame(f,'monthly',NOW,set())
        self.assertEqual(len(monthly),1);self.assertEqual(monthly[-1].closed_at.month,11)
    def test_missing_session_does_not_make_a_full_week(self):
        f=frame(pd.date_range('2026-11-16','2026-11-20',freq='B',tz=IST)).drop(pd.Timestamp('2026-11-18',tz=IST))
        self.assertEqual(bars_from_frame(f,'weekly',NOW,set()),())
        self.assertEqual(len(bars_from_frame(f,'weekly',NOW,{datetime(2026,11,18).date()})),1)
    def test_forming_five_minute_removed(self):
        f=frame(pd.date_range('2026-11-23 09:15',periods=5,freq='5min',tz=IST))
        b=bars_from_frame(f,'5m',NOW.replace(hour=9,minute=32),set())
        self.assertEqual(len(b),3);self.assertEqual(b[-1].closed_at.minute,30)
    def test_metadata_unknown_never_creates_entry(self):
        b=engulfing();ix=pd.date_range('2026-09-01',periods=len(b),freq='B',tz=IST)
        f=pd.DataFrame([dict(open=x.open,high=x.high,low=x.low,close=x.close,volume=x.volume) for x in b],index=ix)
        r=evidence(f,'daily',ix[-1]+pd.Timedelta(hours=16),set())
        self.assertGreater(r['confirmed'],0);self.assertEqual(r['entry_ready'],0)
        self.assertTrue(all(x['entry'] is None and not x['confirmed'] for x in r['patterns']))
        r=evidence(f,'daily',ix[-1]+pd.Timedelta(hours=16),set(),tick_size=.05,eligibility_verified=True)
        self.assertGreater(r['entry_ready'],0)
    def test_bad_sources_are_explicit(self):
        f=frame(pd.date_range('2026-11-23 09:15',periods=30,freq='5min',tz=IST))
        self.assertEqual(evidence(f,'5m',NOW,None)['status'],'UNAVAILABLE')
        f.iloc[2,0]=float('inf')
        self.assertEqual(evidence(f,'5m',NOW,set())['status'],'UNAVAILABLE')
    def test_inspector_releases_lock_and_does_not_mutate_existing_snapshots(self):
        svc=Mock();svc._job_lock=threading.Lock();svc._lookup.return_value={'symbol':'NIFTY','id':'13'}
        svc.broker.history.side_effect=RuntimeError('fixture')
        with self.assertRaises(RuntimeError):inspect(svc,'NIFTY','5m',NOW,set())
        self.assertFalse(svc._job_lock.locked());svc._update.assert_not_called()
    def test_nifty500_exact_fallback(self):
        svc=Mock();svc._job_lock=threading.Lock();svc._lookup.return_value=None
        item={'symbol':'EXAMPLE LIMITED','ticker':'EXAMPLE','segment':'NSE_EQ','id':'1'}
        svc.nifty500.resolve.return_value=([item],{})
        svc.broker.daily.return_value=frame(pd.date_range('2026-09-01','2026-11-20',freq='B',tz=IST))
        result=inspect(svc,'EXAMPLE','daily',NOW,set())
        self.assertEqual(result['symbol'],'EXAMPLE LIMITED')
        self.assertFalse(svc._job_lock.locked())

    def test_pattern_api_rejects_foreign_origin_and_invalid_body(self):
        from insights.api import create_app
        svc=Mock();app=create_app(svc);client=app.test_client()
        self.assertEqual(client.post('/api/v1/market-insights/patterns/scan',json={'symbol':'NIFTY','timeframe':'5m'},headers={'Origin':'https://example.invalid'}).status_code,403)
        self.assertEqual(client.post('/api/v1/market-insights/patterns/scan',json={'symbol':'NIFTY'}).status_code,400)
        with patch('insights.pattern_engine.inspect',return_value={'status':'READY','patterns':[]}) as call:
            r=client.post('/api/v1/market-insights/patterns/scan',json={'symbol':'NIFTY','timeframe':'5m'})
            self.assertEqual(r.status_code,200);self.assertEqual(call.call_count,1)

if __name__=='__main__':unittest.main()
