import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from types import SimpleNamespace
from insights.europe_markets import EuropeMarkets,MARKETS,normalize,session

def payload(now,symbol='^GDAXI'):
    return {'chart':{'result':[{'meta':{'symbol':symbol,'regularMarketPrice':110,'chartPreviousClose':100,'regularMarketTime':now-900,'currentTradingPeriod':{'regular':{'start':now-3600,'end':now+3600}}}}]}}
class EuropeTests(unittest.TestCase):
    def test_change_and_delay(self):
        r=normalize(payload(2000000000),MARKETS[0],2000000000)
        self.assertEqual(r['change'],10);self.assertAlmostEqual(r['change_pct'],10);self.assertEqual(r['quality'],'DELAYED QUOTE')
    def test_missing_previous_not_zero_change(self):
        p=payload(2000000000);p['chart']['result'][0]['meta'].pop('chartPreviousClose')
        self.assertIsNone(normalize(p,MARKETS[0],2000000000)['change_pct'])
    def test_invalid_quote_and_symbol(self):
        for key,val in [('symbol','WRONG'),('regularMarketPrice',float('nan')),('regularMarketTime',2000001000)]:
            p=payload(2000000000);p['chart']['result'][0]['meta'][key]=val
            with self.assertRaises(ValueError):normalize(p,MARKETS[0],2000000000)
    def test_dst_ist_and_weekend(self):
        for month,expected in [(1,'13:30'),(7,'12:30')]:
            now=datetime(2026,month,15,10,tzinfo=timezone.utc).timestamp()
            for m in MARKETS:self.assertEqual(session(m,now)['normal_open_ist'],expected)
        now=datetime(2026,11,15,10,tzinfo=timezone.utc).timestamp()
        self.assertEqual(session(MARKETS[0],now)['scheduled_session'],'OUTSIDE REGULAR HOURS')
    def test_failure_preserves_but_marks_old_quote(self):
        now=2000000000;m=EuropeMarkets(lambda s:payload(now,s))
        with patch('insights.europe_markets.time.time',return_value=now):m.refresh()
        def broken(s):raise RuntimeError('SECRET')
        m.fetch=broken;m.refresh();rows=m.snapshot(now)['markets']
        self.assertEqual(rows[0]['price'],110);self.assertIn('STALE',rows[0]['quality']);self.assertNotIn('SECRET',str(rows))
    def test_one_source_failure_does_not_stop_others(self):
        now=2000000000
        def fetch(s):
            if s=='^GDAXI':raise ValueError()
            return payload(now,s)
        m=EuropeMarkets(fetch)
        with patch('insights.europe_markets.time.time',return_value=now):m.refresh()
        r=m.snapshot(now)['markets'];self.assertEqual(r[0]['quality'],'WAITING FOR DATA');self.assertEqual(r[1]['price'],110)
    def test_snapshot_never_fetches_and_age_updates(self):
        now=2000000000;m=EuropeMarkets(lambda s:payload(now,s))
        with patch('insights.europe_markets.time.time',return_value=now):m.refresh()
        m.fetch=lambda s:self.fail('HTTP handler fetched remote source')
        self.assertIn('STALE',m.snapshot(now+190)['markets'][0]['quality'])
        self.assertEqual(m.snapshot(now+4000)['markets'][0]['provider_session'],'NO CURRENT PROVIDER SESSION')
    def test_api_isolated(self):
        from insights.api import create_app
        app=create_app(SimpleNamespace(europe_markets=EuropeMarkets()))
        r=app.test_client().get('/api/v1/market-insights/europe-markets')
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json['markets']),4)
