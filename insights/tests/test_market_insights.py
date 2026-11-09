import unittest, tempfile, math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from insights.db import Journal
from insights.indicators import index_bias,risk_levels,clean_bars
from insights.strategies.options import chain_metrics,option_plan
from insights.strategies.equity import intraday,btst
from insights.strategies.futures import buildup
from insights.backtest import evaluate_trades
from insights.config import is_market_session,IST
from insights.brokers.dhan import DhanReadOnly,BrokerUnavailable


def history(n=320,bias=1):
    idx=pd.date_range('2026-10-01 09:15',periods=n,freq='5min',tz=IST)
    c=100+np.arange(n)*.06*bias
    return pd.DataFrame({'open':c-.01*bias,'close':c,'high':c+.1,'low':c-.1,'volume':np.full(n,2000.)},index=idx)


def chain():
    return {'last_price':100,'oc':{'90':{'ce':{'oi':80,'previous_oi':50},'pe':{'oi':240,'previous_oi':100}},'100':{'ce':{'oi':100,'previous_oi':90,'top_ask_price':10,'top_bid_price':9.9,'volume':1000,'security_id':'1','implied_volatility':15},'pe':{'oi':160,'previous_oi':130,'top_ask_price':9,'top_bid_price':8.9,'volume':1000,'security_id':'2'}},'110':{'ce':{'oi':140,'previous_oi':120},'pe':{'oi':260,'previous_oi':210}}}}

class TestJournal(unittest.TestCase):
 def test_dedupe_outcomes_real_stats(self):
  with tempfile.TemporaryDirectory() as folder:
   d=Journal(Path(folder)/'test.sqlite')
   s=dict(strategy='Test',version='1',symbol='TCS',direction='BUY',signal_at='2026-11-09T10:00:00+05:30',entry=100,sl=98,t1=103,t2=105,rr=1.5,confidence=70,reasons=['Observed breakout'])
   d.record(s);d.record(s);self.assertEqual(len(d.signals()),1)
   self.assertTrue(d.outcome(d.signals()[0]['id'],'SL','2026-11-09T10:05:00+05:30',98))
   self.assertFalse(d.outcome(d.signals()[0]['id'],'T1','2026-11-09T10:10:00+05:30',103))
   st=d.stats()[0];self.assertEqual(st['losses'],1);self.assertEqual(st['wins'],0);self.assertEqual(st['win_rate'],0)
 def test_bad_levels_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   d=Journal(Path(folder)/'j.sqlite')
   with self.assertRaises(ValueError):d.record(dict(strategy='x',version='1',symbol='TCS',direction='BUY',signal_at='a',entry=100,t1=99,t2=105,sl=98,rr=1.5,confidence=65,reasons=['x']))

class TestRules(unittest.TestCase):
 def test_uptrend_and_downtrend(self):
  a=index_bias(history(),'NIFTY');b=index_bias(history(bias=-1),'SENSEX')
  self.assertEqual(a['bias'],'Uptrend');self.assertEqual(b['bias'],'Downtrend')
  self.assertTrue(a['reasons']);self.assertIn('FII/DII', ' '.join(a['warnings']))
 def test_missing_history_returns_unavailable(self):self.assertEqual(index_bias(history(20),'NIFTY')['bias'],'UNAVAILABLE')
 def test_risk_strictness(self):
  x=risk_levels(100,2,'BUY');self.assertEqual(x['sl'],98);self.assertEqual(x['t1'],103)
  with self.assertRaises(ValueError):risk_levels(100,1,'BUY',stop=80)
 def test_intraday_before_time(self):self.assertIsNone(intraday(history(),'TCS',pd.Timestamp('2026-11-09 09:55',tz=IST),.1,.2))
 def test_btst_blocks_missing_delivery(self):self.assertIsNone(btst(history(),history(),'TCS',pd.Timestamp('2026-11-09 15:00',tz=IST),None,.3))
 def test_fo_requires_futures_oi(self):self.assertIsNone(buildup(history(),'TCS',datetime.now(IST)))
 def test_holiday_fail_closed(self):self.assertFalse(is_market_session(datetime(2026,11,9,10,0,tzinfo=IST),None))

class TestOptions(unittest.TestCase):
 def test_pcr_maxpain_support(self):
  m=chain_metrics(chain());self.assertEqual(m['pcr'],round(660/320,3));self.assertEqual(m['iv_percentile'],None)
  self.assertEqual(m['oi_support'],110)
 def test_missing_oi(self):
  with self.assertRaises(ValueError):chain_metrics({'oc':{}})
 def test_premium_level_buy_pe(self):
  x=option_plan(chain(),'NIFTY','Downtrend','2026-11-20',datetime(2026,11,9,10,0,tzinfo=IST),side_override='PE')
  self.assertIsNone(x) # put/call ratio >1.15 conflicts with bearish PE
 def test_premium_ce(self):
  x=option_plan(chain(),'NIFTY','Uptrend','2026-11-20',datetime(2026,11,9,10,0,tzinfo=IST))
  self.assertGreater(x['t1'],x['entry']);self.assertLess(x['sl'],x['entry'])

class TestBacktest(unittest.TestCase):
 def test_no_lookahead_and_stop_first(self):
  f=history(270)
  def fn(obs):
   if len(obs)==221:return dict(direction='BUY',entry=float(obs.close.iloc[-1]),sl=float(obs.close.iloc[-1]-1),t1=float(obs.close.iloc[-1]+1.5))
  r=evaluate_trades(f,fn,'Test',hold_bars=5)
  self.assertEqual(r['samples'],1);self.assertEqual(r['eligible'],0)
 def test_bad_history(self):
  with self.assertRaises(ValueError):evaluate_trades(history(10),lambda x:None,'t')

class TestBroker(unittest.TestCase):
 def test_no_credentials(self):
  d=DhanReadOnly('','');d.client_id='';d._token=''
  with self.assertRaises(BrokerUnavailable):d._sdk()
 def test_top_level_dhan_candles_response(self):
  d=DhanReadOnly('x','y')
  self.assertEqual(d._check({'open':[1],'timestamp':[123]})['open'],[1])

if __name__=='__main__':unittest.main()
