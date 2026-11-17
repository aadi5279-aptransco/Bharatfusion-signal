import csv
import io
import json
import tempfile
import threading
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pandas as pd
from insights.config import IST
from insights.nifty500 import constituents,map_members,Nifty500Universe
from insights.liquidity_shortlist import LiquidityShortlist
from insights.positional import PositionalScanner,assess,setup

NOW=datetime(2026,11,17,10,tzinfo=IST)
def csv_text(count=500):
    f=io.StringIO();w=csv.writer(f)
    w.writerow(['Company Name','Industry','Symbol','Series','ISIN Code'])
    for i in range(count):w.writerow([f'Company {i}','Test',f'S{i}','EQ',f'INE{i:09d}'])
    return f.getvalue()
def equities(count=500):
    return [dict(kind='stock',segment='NSE_EQ',id=str(i+1),symbol=f'Name {i}',instrument='EQUITY',isin=f'INE{i:09d}') for i in range(count)]

class UniverseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.b=SimpleNamespace(longterm_instruments=lambda:equities())
    def test_full_official_shape_and_exact_isin_not_names(self):
        rows=constituents(csv_text());items,meta=map_members(rows,equities())
        self.assertEqual(len(items),500);self.assertEqual(meta['missing_symbols'],[])
        self.assertEqual(next(x for x in items if x['ticker']=='S0')['id'],'1')
    def test_html_truncation_duplicates_bad_isin_fail(self):
        for text in ['<html>error</html>',csv_text(499),csv_text().replace('S1,EQ','S0,EQ'),csv_text().replace('INE000000001','BAD')]:
            with self.subTest(text=text[:30]),self.assertRaises(ValueError):constituents(text)
    def test_placeholder_and_non_regular_series_are_explained(self):
        text=csv_text().replace('S0,EQ,INE000000000','DUMMYTEST,EQ,DUM000000000').replace('S1,EQ','S1,BE').replace('S2,EQ','S2,RR')
        rows=constituents(text);items,meta=map_members(rows,equities())
        self.assertEqual(len(items),497);self.assertEqual(len(meta['ineligible_constituents']),3)
    def test_missing_ambiguous_and_surveillance_not_silent(self):
        eq=equities();eq.pop();eq.append(dict(eq[0],id='9999'));eq[1]['asm_gsm_flag']='Y'
        items,m=map_members(constituents(csv_text()),eq)
        self.assertEqual(len(items),497);self.assertEqual(m['missing_symbols'],['S499'])
        self.assertEqual(m['ambiguous_symbols'],['S0']);self.assertEqual(m['surveillance_excluded'],['S1'])
    def test_bse_and_same_name_cannot_substitute_for_isin(self):
        eq=equities();eq[0]['isin']='';eq.append(dict(eq[1],isin='INE000000000',segment='BSE_EQ'))
        _,m=map_members(constituents(csv_text()),eq);self.assertEqual(m['missing_symbols'],['S0'])
    def test_daily_download_restart_and_bounded_cache(self):
        fetch=Mock(return_value=csv_text());u=Nifty500Universe(self.b,self.tmp.name,fetch)
        u.resolve(NOW);u.resolve(NOW+timedelta(minutes=5));fetch.assert_called_once()
        other=Nifty500Universe(self.b,self.tmp.name,Mock(side_effect=OSError('offline')))
        other.resolve(NOW);other.fetch.assert_not_called()
        _,meta=other.resolve(NOW+timedelta(days=1));self.assertIn('CACHED',meta['status'])
        other.resolve(NOW+timedelta(days=1,minutes=5));other.fetch.assert_called_once()
        with self.assertRaises(ValueError):other.resolve(NOW+timedelta(days=8))
        saved=json.loads(Path(self.tmp.name,'nifty500_constituents.json').read_text())
        self.assertEqual(saved['retrieved_at'],NOW.isoformat())
    def test_no_fallback_to_all_equities_on_first_download_failure(self):
        with self.assertRaises(ValueError):Nifty500Universe(self.b,self.tmp.name,lambda:'Bad response').resolve(NOW)
    def test_manual_file_is_not_redated_each_restart(self):
        import os
        p=Path(self.tmp.name,'manual.csv');p.write_text(csv_text())
        stamp=(NOW-timedelta(days=8)).timestamp();os.utime(p,(stamp,stamp))
        with patch.dict('os.environ',{'INSIGHTS_NIFTY500_FILE':str(p)}):
            with self.assertRaises(ValueError):Nifty500Universe(self.b,self.tmp.name).resolve(NOW)
    def test_dhan_master_refresh_once_per_date(self):
        from insights.brokers.dhan import DhanReadOnly
        b=DhanReadOnly();b.longterm_instruments=Mock(return_value=equities())
        with patch('data.universe') as master:
            b.nifty500_instruments(NOW);b.nifty500_instruments(NOW+timedelta(minutes=5))
            master.assert_called_once_with(reuse=False)
            b.nifty500_instruments(NOW+timedelta(days=1));self.assertEqual(master.call_count,2)

class LiquidityUniverseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.items=equities(4)
        self.items[-1]['future']={'id':'999'}
        self.b=SimpleNamespace(instruments=lambda:self.items,longterm_instruments=lambda:self.items,
             market_quotes=lambda items,now:{x['id']:dict(last_price=100,volume=int(x['id'])*200000,change_pct=0,fetched_at=now.isoformat()) for x in items})
        self.u=SimpleNamespace(resolve=Mock(return_value=(self.items[:2],dict(name='NIFTY 500',mapped=2))))
        self.s=LiquidityShortlist(self.b,self.tmp.name,limit=2,pause=0,universe=self.u)
    def test_only_nifty_in_intraday_fo_and_swing_unchanged(self):
        self.s.refresh(NOW)
        self.assertEqual([x['id'] for x in self.s.selected('intraday',NOW)],['2','1'])
        self.assertEqual([x['id'] for x in self.s.selected('fo-stocks',NOW)],['4'])
        self.assertEqual([x['id'] for x in self.s.selected('swing-trades',NOW)],['4','3'])
        self.assertEqual(self.s.metadata(NOW)['intraday_quoted'],2)
    def test_unavailable_membership_clears_intraday_but_not_fo(self):
        self.s.refresh(NOW);self.u.resolve.side_effect=ValueError('Expired constituents')
        self.s.refresh(NOW.replace(hour=11))
        self.assertEqual(self.s.selected('intraday',NOW),[])
        self.assertTrue(self.s.selected('fo-stocks',NOW));self.assertEqual(self.s.state['nifty500']['status'],'UNAVAILABLE')
    def test_old_broad_shortlist_cannot_be_reused_as_nifty(self):
        self.s.state=dict(date=NOW.date().isoformat(),lists={'intraday':self.items})
        self.assertEqual(self.s.selected('intraday',NOW),[])

class RotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.items=equities(5);self.seen=[]
        def daily(item,now,**kwargs):self.seen.append(item['id']);return pd.DataFrame()
        self.b=SimpleNamespace(configured=lambda:True,daily=daily)
        self.u=SimpleNamespace(resolve=lambda now:(self.items,dict(name='NIFTY 500',mapped=5)))
        self.s=PositionalScanner(self.b,self.tmp.name,lambda:set(),threading.Lock(),limit=2,universe=self.u)
        self.addCleanup(self.s.stop)
        self.s.ema9.scan=lambda *a:([],[])
        self.patch=patch('insights.positional.daily_setups',return_value=([],pd.DataFrame()))
        self.patch.start();self.addCleanup(self.patch.stop)
        self.session=patch('insights.positional.is_market_session',return_value=False)
        self.session.start();self.addCleanup(self.session.stop)
    def test_rotation_covers_tail_and_survives_restart(self):
        self.s._run(NOW);self.s._run(NOW+timedelta(minutes=5));self.s._run(NOW+timedelta(minutes=10))
        self.assertEqual(set(self.seen),{'1','2','3','4','5'})
        c=self.s.store._read('positional',{})['coverage'];self.assertEqual(c['unique_assessed'],5);self.assertEqual(c['remaining'],0)
        other=PositionalScanner(self.b,self.tmp.name,lambda:set(),threading.Lock(),limit=2,universe=self.u)
        self.addCleanup(other.stop);other.ema9.scan=lambda *a:([],[])
        self.seen.clear();other._run(NOW+timedelta(minutes=15));self.assertEqual(self.seen,['2','3'])
    def test_source_errors_advance_cursor(self):
        self.b.daily=Mock(side_effect=ValueError('Missing chart'))
        self.s._run(NOW);self.s._run(NOW+timedelta(minutes=5))
        ids=[c.args[0]['id'] for c in self.b.daily.call_args_list]
        self.assertEqual(ids,['1','2','3','4'])
        self.assertEqual(self.s.store._read('progress',{})['assessed'],[])
    def test_timeout_publishes_progress_and_continues_later(self):
        self.b.daily=Mock(side_effect=[pd.DataFrame(),TimeoutError('Budget exhausted'),pd.DataFrame(),pd.DataFrame()])
        self.s._run(NOW);c=self.s.store._read('positional',{})['coverage']
        self.assertTrue(c['budget_exhausted']);self.assertEqual(c['unique_assessed'],1)
        self.s._run(NOW+timedelta(minutes=5))
        self.assertEqual([c.args[0]['id'] for c in self.b.daily.call_args_list],['1','2','3','4'])
    def test_individual_rows_expire_even_if_another_batch_is_fresh(self):
        row=dict(status='READY — REVIEW ENTRY',timeframe='Daily',checked_at=(NOW-timedelta(minutes=11)).isoformat())
        self.s.store._write('positional',dict(rows=[row],coverage={},updated_at=NOW.isoformat()))
        self.assertEqual(self.s.snapshot(NOW)['rows'][0]['status'],'STALE SCAN — DO NOT USE')
    def test_missing_price_does_not_reuse_ready_status(self):
        r=assess(dict(status='READY — REVIEW ENTRY'),None,NOW,set())
        self.assertEqual(r['status'],'WAITING FOR PRICE')
    def test_nonfinite_target_is_rejected(self):
        self.assertIsNone(setup(self.items[0],'test',NOW,100,98,'reason','exit',t1=float('inf'),t2=float('inf')))
