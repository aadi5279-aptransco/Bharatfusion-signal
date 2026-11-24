import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from patterns.types import Bar
from insights.alpha.research import Candidate, Fees, LabelConfig, Sample, label, walk_forward, uniqueness_weights, opportunity_score
from insights.alpha.journal import ResearchJournal

T = datetime(2026, 11, 24, 4, tzinfo=timezone.utc)
# Synthetic tariff only: not a production Indian fee schedule.
F = Fees('fixture','synthetic unit test',date(2026,1,1),date(2026,12,31),
         .0003,20,0,0,.00025,.00003,.000001,.00003,.000001,.18)
C = Candidate('test',T,1,2,10,.05,100000,True)
CFG = LabelConfig(horizon=3,base_slippage_bps=0,impact_bps=0)
def bars(values):
    return tuple(Bar(T+timedelta(minutes=5*i),T+timedelta(minutes=5*(i+1)),*v,100000) for i,v in enumerate(values))
B = bars([(100,101,99,100),(100,104,99,103),(103,104,102,103)])

class AlphaResearchTests(unittest.TestCase):
    def test_leakage_detector_rejects_full_sample_normalization(self):
        from insights.alpha.research import assert_prefix_causal
        assert_prefix_causal(lambda x: [sum(x[:i+1])/(i+1) for i in range(len(x))], [1,2,4])
        with self.assertRaises(ValueError):
            assert_prefix_causal(lambda x: [n/max(x) for n in x], [1,2,4])
    def test_resolved_label_ignores_later_corruption(self):
        normal=label(C,B,F,T+timedelta(hours=1),CFG)
        later=(B[0],B[1],replace(B[2],close=float('nan')))
        self.assertEqual(label(C,later,F,T+timedelta(hours=1),CFG),normal)
    def test_next_bar_entry_and_target(self):
        result=label(C,B,F,T+timedelta(hours=1),CFG)
        self.assertEqual(result['entry'],100)
        self.assertEqual(result['outcome'],'TARGET')
        self.assertEqual(result['gross_r'],1.5)
        self.assertLess(result['net_r'],1.5)
    def test_stop_first_and_gap_stop(self):
        both=bars([(100,104,97,100)])
        self.assertEqual(label(C,both,F,T+timedelta(hours=1),CFG)['outcome'],'STOP')
        gap=bars([(100,101,99,100),(95,96,94,95)])
        self.assertEqual(label(C,gap,F,T+timedelta(hours=1),CFG)['exit'],95)
    def test_short_and_time_limit(self):
        short=replace(C,direction=-1)
        result=label(short,bars([(100,101,96,97)]),F,T+timedelta(hours=1),CFG)
        self.assertEqual(result['outcome'],'TARGET');self.assertEqual(result['exit'],97)
        result=label(C,bars([(100,101,99,100)]*3),F,T+timedelta(hours=1),CFG)
        self.assertEqual(result['outcome'],'TIME')
    def test_future_candles_never_resolve_early(self):
        now=T+timedelta(minutes=5)
        self.assertEqual(label(C,B,F,now,CFG)['status'],'PENDING')
        corrupt=(B[0],replace(B[1],close=float('nan')))
        self.assertEqual(label(C,corrupt,F,now,CFG)['status'],'PENDING')
    def test_slippage_capacity_and_lots(self):
        result=label(C,B,F,T+timedelta(hours=1),replace(CFG,base_slippage_bps=10))
        self.assertGreater(result['entry'],100)
        self.assertLess(result['net_r'],label(C,B,F,T+timedelta(hours=1),CFG)['net_r'])
        self.assertEqual(label(replace(C,prior_volume=100),B,F,T+timedelta(hours=1),CFG)['status'],'REJECTED_CAPACITY')
        with self.assertRaises(ValueError):replace(C,lot_size=3)
        with self.assertRaises(ValueError):replace(C,eligibility_verified=False)
    def test_bad_bars_and_insufficient_liquidity(self):
        self.assertEqual(label(C,(replace(B[0],circuit_locked=True),),F,T+timedelta(hours=1),CFG)['status'],'QUARANTINED_LIQUIDITY')
        with self.assertRaises(ValueError):label(C,(replace(B[0],low=110),),F,T+timedelta(hours=1),CFG)
        with self.assertRaises(ValueError):label(C,B[2:],F,T+timedelta(hours=1),CFG)
    def test_dated_cost_breakdown(self):
        r=F.leg(100,100,1,T.date())
        self.assertEqual(r['brokerage'],3)
        self.assertEqual(r['stt'],0)
        self.assertEqual(r['total'],round(sum(v for k,v in r.items() if k!='total'),2))
        with self.assertRaises(ValueError):F.leg(100,100,1,date(2027,1,1))
        with self.assertRaises(ValueError):replace(F,exchange=float('nan'))
    def test_purge_and_embargo(self):
        s=[Sample(T+timedelta(days=i),T+timedelta(days=i+3)) for i in range(20)]
        folds=list(walk_forward(s,4,3,timedelta(days=1)))
        self.assertTrue(folds)
        for train,test in folds:
            self.assertTrue(all(s[i].end < s[test[0]].known_at-timedelta(days=1) for i in train))
            self.assertTrue(set(train).isdisjoint(test))
        with self.assertRaises(ValueError):list(walk_forward(list(reversed(s)),4,3,timedelta(0)))
    def test_overlap_weights(self):
        s=Sample(T,T+timedelta(days=1))
        self.assertEqual(uniqueness_weights([s,s],s.end,30),(.5,.5))
        self.assertEqual(uniqueness_weights([s],s.end,30),(1.,))
        self.assertAlmostEqual(uniqueness_weights([s],s.end+timedelta(days=30),30)[0],.5)
    def test_conservative_score(self):
        self.assertAlmostEqual(opportunity_score(.6,2,1,.1,.1,.1),.5)
        self.assertLess(opportunity_score(.4,1,1,.1,.1,regime_fit=0),0)
        with self.assertRaises(ValueError):opportunity_score(float('nan'),2,1,0,0)
    def test_journal_idempotent_and_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            j=ResearchJournal(Path(d)/'research.sqlite')
            digest=j.append('signal-1',{'net_r':1.2})
            self.assertEqual(j.append('signal-1',{'net_r':1.2}),digest)
            with self.assertRaises(ValueError):j.append('signal-1',{'net_r':2})
            with self.assertRaises(sqlite3.IntegrityError):j.db.execute('DELETE FROM events')
            j.db.rollback();self.assertTrue(j.verify());j.close()
    def test_health_api_does_not_train_or_call_broker(self):
        from insights.api import create_app
        service=Mock();client=create_app(service).test_client()
        r=client.get('/api/v1/market-insights/model-health')
        self.assertEqual(r.status_code,200)
        self.assertIsNone(r.json['champion'])
        self.assertFalse(r.json['automatic_training'])
        self.assertIsNone(r.json['metrics'])
        self.assertEqual(service.mock_calls,[])
