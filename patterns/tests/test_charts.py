import unittest
from dataclasses import replace
from datetime import datetime,timedelta
from patterns import PatternConfig,Context,Bar,scan
from patterns.charts import detect,CHART_NAMES
from patterns.tests.test_engine import daily,IST

CFG=PatternConfig(pivot_left=1,pivot_right=1,zigzag_atr=.5,min_pattern_bars=4)
def path(points,prefix=None,tail=None):
    values=list(prefix or [100]*35)
    for a,b in zip(points,points[1:]):values.extend(a+(b-a)*k/5 for k in range(5))
    values.append(points[-1]);values.extend(tail or [points[-1]+.2,points[-1]+.3,points[-1]+.4])
    return daily([(v,v+.1,v-.1,v) for v in values])
def names(b,cfg=CFG,tf='daily',ctx=Context()):return {x.name for x in detect(b,tf,2,cfg,ctx)}

class ChartTests(unittest.TestCase):
    def test_pivot_geometry_catalogue(self):
        examples={
        'Double Top':[105,95,105,100], 'Double Bottom':[95,105,95,100],
        'Triple Top':[105,95,105,95,105,100], 'Triple Bottom':[95,105,95,105,95,100],
        'Head and Shoulders':[105,95,112,95,105,100], 'Inverse Head and Shoulders':[95,105,88,105,95,100],
        'Ascending Triangle':[110,95,110,98,110,101,110,103],
        'Descending Triangle':[105,90,102,90,99,90,97,90],
        'Symmetrical Triangle':[110,90,108,92,106,94,104,96],
        'Rectangle':[110,90,110,90,110,90,110,90],
        'Rising Wedge':[110,100,112,104,114,108,116,112],
        'Falling Wedge':[110,100,106,98,102,96,98,94],
        'Bull Flag':[110,105,109,104,108,103,107,102],
        'Bear Flag':[90,95,91,96,92,97,93,98],
        'Bull Pennant':[110,100,109,101,108,102,107,103],
        'Bear Pennant':[100,90,99,91,98,92,97,93],
        'VCP':[90,110,95,109,99,108,103,107]}
        for name,points in examples.items():
            prefix=[60+i for i in range(35)] if name.startswith('Bull') else [150-i for i in range(35)] if name.startswith('Bear') else None
            b=path(points,prefix)
            if name=='VCP':b=tuple(replace(x,volume=10000 if i>len(b)-7 else 100000) for i,x in enumerate(b))
            with self.subTest(name=name):self.assertIn(name,names(b))
    def test_rounding_cup_and_handle(self):
        # A sampled smooth parabola, not a single V-shaped impulse.
        curve=[90+10*((i-20)/20)**2 for i in range(41)]
        b=daily([(v,v+.1,v-.1,v) for v in curve+[100.2]])
        self.assertIn('Rounding Bottom',names(b))
        cup=curve+[99,98,98.5,99,101]
        self.assertIn('Cup and Handle',names(daily([(v,v+.1,v-.1,v) for v in cup])))
    def test_prior_range_catalogue_and_ath_evidence(self):
        b=daily([(100,102,98,100)]*270+[(100,101,99,100),(100,100.5,99.5,100),(103,104,102,103)])
        result=names(b,ctx=Context(all_time_history=True))
        self.assertTrue({'NR4','NR7','Inside Bar','52-week Breakout','All-time High Breakout'}<=result)
        self.assertNotIn('All-time High Breakout',names(b))
        self.assertIn('Darvas Box',names(path([105,95,105,100])))
    def test_orb_needs_actual_open_and_closed_breakout(self):
        start=datetime(2026,11,23,9,15,tzinfo=IST)
        old=datetime(2026,11,20,9,15,tzinfo=IST)
        b=tuple(Bar(old+timedelta(minutes=5*i),old+timedelta(minutes=5*(i+1)),100,101,99,100,100000) for i in range(30))
        b+=tuple(Bar(start+timedelta(minutes=5*i),start+timedelta(minutes=5*(i+1)),100,101,99,100,100000) for i in range(3))
        b+=(Bar(start+timedelta(minutes=15),start+timedelta(minutes=20),100,102.2,99.9,102,300000),)
        self.assertIn('Opening Range Breakout',names(b,tf='5m'))
        signal=next(p for p in scan(b,'5m',b[-1].closed_at,CFG) if p.pattern=='Opening Range Breakout' and p.confirmed)
        self.assertEqual(signal.target,103)
        chased=b[:-1]+(replace(b[-1],high=105,close=104),)
        self.assertFalse(any(p.pattern=='Opening Range Breakout' and p.confirmed for p in scan(chased,'5m',b[-1].closed_at,CFG)))
        self.assertNotIn('Opening Range Breakout',names(b[:30]+b[31:],tf='5m'))
        lowvol=b[:-1]+(replace(b[-1],volume=1000),)
        self.assertFalse(any(p.confirmed for p in scan(lowvol,'5m',b[-1].closed_at,CFG)))
    def test_no_repeated_breakout_after_already_beyond_level(self):
        b=daily([(100,101,99,100)]*270+[(102,103,102,103),(104,105,104,105)])
        r=scan(b,'daily',b[-1].closed_at)
        # Lack of fresh volume alone must not be needed to stop a repeated signal.
        self.assertFalse(any(p.pattern=='52-week Breakout' and p.confirmed for p in r))
    def test_catalogue_is_complete(self):
        self.assertEqual(len(CHART_NAMES),26)
    def test_no_lookahead_for_every_chart_prefix(self):
        b=path([110,90,108,92,106,94,104,96])
        for i in range(30,len(b)):
            self.assertEqual(scan(b[:i+1],'daily',b[i].closed_at,CFG),scan(b,'daily',b[i].closed_at,CFG))

if __name__=='__main__':unittest.main()
