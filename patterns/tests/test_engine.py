import json
import unittest
from dataclasses import replace
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from patterns import Bar,Context,PatternConfig,scan,pivots
from patterns.engine import closed_bars
from patterns.candles import detect,CANDLE_NAMES
from patterns.math import atr_series,rounded

IST=ZoneInfo('Asia/Kolkata')
START=datetime(2026,1,1,tzinfo=IST)
def daily(values,volume=100000):
    return tuple(Bar(START+timedelta(days=i),START+timedelta(days=i,hours=15,minutes=40),*v,volume) for i,v in enumerate(values))
def flat(n=35):return [(100,101,99,100)]*n

def engulfing():
    values=[(130-i,131-i,129-i,130-i) for i in range(35)]
    values += [(96,96.1,93.9,94),(93.8,97.2,93.7,97),(97.1,99.1,97,99)]
    b=daily(values);return b[:-1]+(replace(b[-1],volume=300000),)

class CandleCatalogueTests(unittest.TestCase):
    def test_every_requested_candle_has_a_positive_geometry_fixture(self):
        a=(104,104.2,99.8,100);up=(100,104.2,99.8,104)
        fixtures={
         'Doji':[(100,101,99,100.01)],
         'Dragonfly Doji':[(100,100.1,97,100.02)],
         'Gravestone Doji':[(100,103,99.9,100.02)],
         'Hammer':[(100,100.5,98,100.4)],
         'Hanging Man':[(100,100.5,98,100.4)],
         'Inverted Hammer':[(100,102.4,99.9,100.4)],
         'Shooting Star':[(100,102.4,99.9,100.4)],
         'Bullish Marubozu':[(100,102,100,102)],
         'Bearish Marubozu':[(102,102,100,100)],
         'Spinning Top':[(100,102,98,100.5)],
         'Bullish Engulfing':[a,(99.9,104.5,99.8,104.4)],
         'Bearish Engulfing':[up,(104.1,104.2,99.5,99.6)],
         'Piercing':[a,(99.7,103.2,99.6,103)],
         'Dark Cloud':[up,(104.3,104.4,100.8,101)],
         'Bullish Harami':[a,(101,101.7,100.9,101.5)],
         'Bearish Harami':[up,(103,103.1,102.3,102.5)],
         'Tweezer Bottom':[a,(100,103.2,99.8,103)],
         'Tweezer Top':[up,(104,104.2,100.8,101)],
         'Morning Star':[a,(99.6,100,99.4,99.8),(100,103.2,99.9,103)],
         'Evening Star':[up,(104.2,104.6,104,104.4),(104,104.1,100.8,101)],
         'Three White Soldiers':[(100,102.1,99.9,102),(101,103.1,100.9,103),(102,104.1,101.9,104)],
         'Three Black Crows':[(104,104.1,101.9,102),(103,103.1,100.9,101),(102,102.1,99.9,100)],
         'Three Inside Up':[a,(101,101.7,100.9,101.5),(101.6,104.6,101.5,104.5)],
         'Three Inside Down':[up,(103,103.1,102.3,102.5),(102.4,102.5,99.4,99.5)]}
        self.assertEqual(set(fixtures),set(CANDLE_NAMES))
        for name,seq in fixtures.items():
            with self.subTest(name=name):
                b=daily(flat()+seq)
                self.assertIn(name,[x.name for x in detect(b,len(b)-1,2,PatternConfig())])
                scaled=tuple(replace(x,open=x.open*10,high=x.high*10,low=x.low*10,close=x.close*10) for x in b)
                self.assertIn(name,[x.name for x in detect(scaled,len(scaled)-1,20,PatternConfig())])
    def test_gap_policy_is_explicit(self):
        b=daily(flat()+[(104,104.2,99.8,100),(99.9,103.1,99.8,103)])
        self.assertIn('Piercing',[x.name for x in detect(b,len(b)-1,2,PatternConfig())])
        self.assertNotIn('Piercing',[x.name for x in detect(b,len(b)-1,2,PatternConfig(require_gaps=True))])
    def test_all_flat_is_not_directional_morphology(self):
        b=daily([(100,100,100,100)]*40)
        self.assertEqual(detect(b,39,2,PatternConfig()),())

class TemporalTests(unittest.TestCase):
    def test_confirmation_waits_for_next_close(self):
        b=engulfing();before=scan(b,'daily',b[-2].closed_at)
        self.assertTrue(any(p.pattern=='Bullish Engulfing' and not p.confirmed for p in before))
        after=scan(b,'daily',b[-1].closed_at)
        p=next(p for p in after if p.pattern=='Bullish Engulfing')
        self.assertTrue(p.confirmed);self.assertEqual(p.available_at,b[-1].closed_at)
        self.assertGreater(p.entry,p.stop);self.assertGreater(p.target,p.entry)
        self.assertEqual(p.end,b[-2].time)
    def test_future_append_and_mutation_cannot_change_asof(self):
        b=engulfing();asof=b[-1].closed_at;expected=scan(b,'daily',asof)
        future=replace(b[-1],time=b[-1].time+timedelta(days=1),closed_at=asof+timedelta(days=1),close=float('nan'))
        self.assertEqual(scan(b+(future,),'daily',asof),expected)
        self.assertEqual(scan(b+(replace(future,close=9000,high=10000),),'daily',asof),expected)
    def test_every_prefix_matches_full_frame_asof(self):
        b=engulfing()
        for i in range(25,len(b)):
            self.assertEqual(scan(b[:i+1],'daily',b[i].closed_at),scan(b,'daily',b[i].closed_at))
    def test_pivots_have_right_delay_and_never_move(self):
        b=daily([(100,101+(5 if i%10==5 else 0),99-(5 if i%10==0 else 0),100) for i in range(80)])
        cfg=PatternConfig(pivot_left=2,pivot_right=2)
        full=pivots(b,cfg);self.assertTrue(full)
        for i in range(20,len(b)):
            self.assertEqual(pivots(b[:i],cfg),tuple(p for p in full if p.confirmed_index<i))
            self.assertTrue(all(p.confirmed_index==p.index+2 for p in pivots(b[:i],cfg)))
    def test_nonfinite_duplicate_naive_and_offgrid_fail(self):
        b=engulfing()
        for bad in (b+(b[-1],), b[:-1]+(replace(b[-1],volume=float('inf')),), b[:-1]+(replace(b[-1],time=b[-1].time.replace(tzinfo=None)),)):
            with self.assertRaises(ValueError):scan(bad,'daily',b[-1].closed_at)
        t=START.replace(hour=11,minute=56)
        with self.assertRaises(ValueError):closed_bars((Bar(t,t+timedelta(minutes=5),100,101,99,100,10),),'5m',t+timedelta(hours=1))
    def test_locked_or_illiquid_confirmation_cannot_create_entry(self):
        b=engulfing()
        for last in (replace(b[-1],circuit_locked=True),replace(b[-1],eligible=False),replace(b[-1],volume=0)):
            result=scan(b[:-1]+(last,),'daily',last.closed_at)
            self.assertFalse(any(p.confirmed for p in result));self.assertTrue(all(p.entry is None for p in result))
    def test_incomplete_week_and_month_rejected(self):
        t=datetime(2026,11,23,tzinfo=IST)
        for tf,end in [('weekly',t+timedelta(days=4)),('monthly',t+timedelta(days=5))]:
            with self.assertRaises(ValueError):closed_bars((Bar(t,end,100,101,99,100,1000),),tf,end)
    def test_context_cannot_come_from_future(self):
        b=engulfing()
        with self.assertRaises(ValueError):scan(b,'daily',b[-1].closed_at,context=Context(known_at=b[-1].closed_at+timedelta(seconds=1)))
    def test_serialization_is_json_finite_and_stable(self):
        b=engulfing();r=scan(b,'daily',b[-1].closed_at)
        self.assertEqual(json.dumps([x.to_dict() for x in r],allow_nan=False),json.dumps([x.to_dict() for x in scan(b,'daily',b[-1].closed_at)],allow_nan=False))
    def test_optional_confirmation(self):
        b=engulfing()[:-1]
        cfg=PatternConfig(require_confirmation=False,require_volume=False)
        self.assertTrue(any(p.confirmed and p.pattern=='Bullish Engulfing' for p in scan(b,'daily',b[-1].closed_at,cfg)))
    def test_wilder_seed_and_tick_rounding(self):
        b=daily([(10,11+i,9,10) for i in range(16)])
        a=atr_series(b,14);self.assertIsNone(a[12]);self.assertAlmostEqual(a[13],8.5)
        self.assertAlmostEqual(a[14],(8.5*13+16)/14)
        self.assertEqual(rounded(100.03,.05,True),100.05);self.assertEqual(rounded(100.03,.05,False),100)
    def test_invalid_config(self):
        for kwargs in ({'pivot_right':0},{'volume_multiple':float('nan')},{'doji_body':.5}):
            with self.assertRaises(ValueError):PatternConfig(**kwargs)

if __name__=='__main__':unittest.main()
