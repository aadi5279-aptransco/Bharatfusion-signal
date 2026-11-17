import unittest,tempfile,threading,json
from pathlib import Path
from datetime import datetime,timedelta
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
import pandas as pd
from insights.config import IST
from insights.index_premium import assess,quote_values,direction_checks
from insights.premarket_followthrough import completed_session,PremarketFollowthrough
from insights.service import InsightsService
NOW=datetime(2026,11,17,12,0,tzinfo=IST)
def bars(period=5,down=False,premium=False):
    c=np.linspace(100,110,40)
    if down:c=210-c
    if premium:c=np.linspace(9,10,40)
    return pd.DataFrame(dict(open=c+(.3 if down else -.3),high=c+.4,low=c-.4,close=c,volume=100000.),index=pd.date_range(end=pd.Timestamp(NOW)-pd.Timedelta(minutes=period),periods=40,freq=f'{period}min'))
def watch(side='CE'):return [dict(state='DIRECTION_READY',side=side,strategy='Red bar',reason='Two confirmed closes',trigger_ce=109,trigger_pe=101)]
def chain():return dict(last_price=110,oc={'110':dict(ce=dict(security_id='501',oi=100,implied_volatility=30),pe=dict(security_id='502',oi=100))})
def quote():return dict(last_trade_time=NOW.strftime('%d/%m/%Y %H:%M:%S'),volume=100000,depth={'buy':[dict(price=10,quantity=10)],'sell':[dict(price=10.1,quantity=10)]})
def broker(down=False):
    calls=[]
    def history(item,now,minutes,**kwargs):calls.append(item);return bars(minutes,down=down,premium=item.get('kind')=='option')
    return SimpleNamespace(expiry_list=lambda _:['2026-11-17'],option_chain=lambda *a:chain(),history=history,market_quotes=lambda items,now:{x['id']:quote() for x in items},calls=calls)
class PremiumTests(unittest.TestCase):
    def test_entry_is_premium_not_strike(self):
        b=broker();rows=assess(b,dict(symbol='NIFTY'),bars(),watch(),NOW,set());r=rows[0]
        self.assertEqual(r['blockers'],[]);self.assertEqual(r['entry'],10.1);self.assertEqual(r['strike'],110)
        self.assertLess(r['sl'],r['entry']);self.assertLess(r['entry'],r['t1']);self.assertLess(r['t1'],r['t2']);self.assertIsNone(rows[1]['entry'])
        self.assertEqual(b.calls[-1]['id'],'501');self.assertTrue(any('EXPIRY' in w for w in r['warnings']))
    def test_pe_premium_buy_targets(self):
        b=broker(True);b.option_chain=lambda *a:dict(chain(),last_price=100)
        r=assess(b,dict(symbol='SENSEX'),bars(down=True),watch('PE'),NOW,set())[1]
        self.assertEqual(r['blockers'],[]);self.assertEqual(r['entry'],10.1);self.assertGreater(r['t1'],r['entry']);self.assertEqual(b.calls[-1]['segment'],'BSE_FNO')
    def test_stale_missing_timestamp_and_spread_block(self):
        for q in [dict(quote(),last_trade_time='01/01/1980 00:00:00'),dict(quote(),last_trade_time=None),dict(quote(),depth={'buy':[{'price':8,'quantity':1}],'sell':[{'price':10,'quantity':1}]})]:
            b=broker();b.market_quotes=lambda *a:{'501':q};r=assess(b,dict(symbol='NIFTY'),bars(),watch(),NOW,set())[0]
            self.assertIsNone(r['entry']);self.assertTrue(r['blockers'])
    def test_receipt_latency_and_future_trade(self):
        q=dict(quote(),fetched_at=(NOW+timedelta(seconds=20)).isoformat(),last_trade_time=(NOW+timedelta(seconds=19)).strftime('%d/%m/%Y %H:%M:%S'))
        self.assertEqual(quote_values(q,NOW)[1],10.1)
        q['last_trade_time']=(NOW+timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M:%S')
        with self.assertRaises(ValueError):quote_values(q,NOW)
    def test_rejection_wick_and_conflict_block(self):
        f=bars();f.loc[f.index[-1],'high']=115
        _,blocks,_=direction_checks(f,bars(15),bars(60),watch()+watch('PE'),'CE',NOW,set())
        self.assertTrue(any('wick' in b for b in blocks));self.assertTrue(any('Conflicting' in b for b in blocks))
    def test_missing_premium_no_cash_substitution(self):
        b=broker();orig=b.history
        def missing(item,*a,**k):
            if item.get('kind')=='option':raise ValueError('Premium data missing')
            return orig(item,*a,**k)
        b.history=missing;r=assess(b,dict(symbol='NIFTY'),bars(),watch(),NOW,set())[0]
        self.assertIsNone(r['entry']);self.assertIn('Premium data missing',r['blockers'])
    def test_closed_market_blocks(self):
        r=assess(broker(),dict(symbol='NIFTY'),bars(),watch(),NOW.replace(hour=18),set())[0]
        self.assertIsNone(r['entry']);self.assertIn('Outside verified market session',r['blockers'])
class SessionTests(unittest.TestCase):
    def test_completed_session_night_weekend_holiday(self):
        for now,want in [(NOW.replace(hour=23),'2026-11-17'),(NOW.replace(hour=2),'2026-11-16'),(datetime(2026,11,15,22,tzinfo=IST),'2026-11-13'),(datetime(2026,11,10,22,tzinfo=IST),'2026-11-09')]:self.assertEqual(str(completed_session(now,set())),want)
    def test_premarket_before_failing_longterm(self):
        with tempfile.TemporaryDirectory() as root:
            s=InsightsService(SimpleNamespace(daily=lambda:None,instruments=lambda:[]),root);s.scan_premarket=Mock(return_value={'assessed':5});s.scan_longterm=Mock(side_effect=ValueError('Other module failed'))
            with patch('insights.service._holiday_set',return_value=set()):s.run_due(NOW.replace(hour=23))
            s.scan_premarket.assert_called_once()
    def test_overnight_dated_cache_no_repeat(self):
        with tempfile.TemporaryDirectory() as root:
            s=InsightsService(SimpleNamespace(daily=lambda:None,instruments=lambda:[]),root)
            def prepare(now):s._snapshots['pre-market']=dict(previous_session='2026-11-16',assessed=5);return {'assessed':5}
            s.scan_premarket=Mock(side_effect=prepare)
            with patch('insights.service._holiday_set',return_value=set()):s.run_due(NOW.replace(hour=2));s.run_due(NOW.replace(hour=3))
            s.scan_premarket.assert_called_once()
    def test_continuous_five_minute_cycles_and_no_replay(self):
        with tempfile.TemporaryDirectory() as root:
            item=dict(symbol='A');svc=SimpleNamespace(root=Path(root),_job_lock=threading.Lock(),_lookup=lambda _:item,snapshot=lambda _:dict(gainers=[item],previous_session='2026-11-16'),broker=SimpleNamespace(daily=lambda *a,**k:bars(),history=lambda *a,**k:bars()))
            w=PremarketFollowthrough(svc,lambda:set())
            with patch('insights.premarket_followthrough.assess',return_value=dict(symbol='A',signals=[])) as check:
                for h,m in [(9,30),(9,31),(9,35),(11,17),(15,25),(15,30)]:w.run_due(NOW.replace(hour=h,minute=m))
            self.assertEqual(check.call_count,4);self.assertEqual(set(w.state['passes']),{'09:30','09:35','11:15','15:25'})
            self.assertEqual(w.snapshot(NOW.replace(hour=15,minute=26))['latest']['cutoff'],'2026-11-17T15:25:00+05:30')
    def test_dated_archive_restore(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'premarket_archive';p.mkdir();(p/'2026-11-16.json').write_text(json.dumps(dict(previous_session='2026-11-16',candidates=[dict(symbol='A')],gainers=[],losers=[])))
            w=PremarketFollowthrough(SimpleNamespace(root=Path(root),snapshot=lambda _:{}),lambda:set())
            self.assertTrue(w.freeze(NOW));self.assertEqual(w.state['symbols'],['A'])

class BoundaryCacheTests(unittest.TestCase):
    def test_five_minute_boundary_never_reuses_previous_bar_cache(self):
        from insights.brokers.dhan import DhanReadOnly
        b=DhanReadOnly('test','test');item=dict(symbol='NIFTY',id='13',segment='IDX_I',instrument='INDEX',kind='index')
        idx=pd.date_range('2026-11-17 09:15',periods=5,freq='5min',tz=IST)
        raw=dict(timestamp=[int(t.timestamp()) for t in idx],open=[100]*5,high=[101]*5,low=[99]*5,close=[100]*5,volume=[0]*5)
        sdk=SimpleNamespace(intraday_minute_data=Mock(return_value=raw))
        with patch.object(b,'_sdk',return_value=sdk):
            before=b.history(item,NOW.replace(hour=9,minute=34));after=b.history(item,NOW.replace(hour=9,minute=35))
            again=b.history(item,NOW.replace(hour=9,minute=36))
        self.assertEqual(before.index[-1].minute,25);self.assertEqual(after.index[-1].minute,30)
        self.assertEqual(sdk.intraday_minute_data.call_count,2);self.assertEqual(len(b._history_cache),1)

class EarlyHourTests(unittest.TestCase):
    def test_previous_session_hourly_context_only_until_first_hour_closes(self):
        now=NOW.replace(hour=9,minute=35)
        f=bars();f.index=f.index-(pd.Timestamp(NOW)-pd.Timestamp(now))
        m=bars(15);m.index=m.index-(pd.Timestamp(NOW)-pd.Timestamp(now))
        h=bars(60);h.index=pd.date_range(end=pd.Timestamp('2026-11-16 14:15',tz=IST),periods=40,freq='60min')
        _,_,reasons=direction_checks(f,m,h,watch(),'CE',now,set())
        self.assertTrue(any('prior completed session' in r for r in reasons))
        with self.assertRaises(ValueError):direction_checks(f,m,h,watch(),'CE',now.replace(hour=10,minute=15),set())
