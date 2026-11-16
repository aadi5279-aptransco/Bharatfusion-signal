import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from insights import smc_expert
from insights.config import IST

NOW=pd.Timestamp('2026-11-16 12:00',tz=IST)
def bars(period=5):
    c=100+np.arange(100)*.03+np.sin(np.arange(100))* .2
    c[-1]+=1
    return pd.DataFrame(dict(open=c-.1,high=c+.15,low=c-.15,close=c,volume=1000.),index=pd.date_range(end=NOW-pd.Timedelta(minutes=period),periods=100,freq=f'{period}min'))
def chain():
    leg=dict(security_id='1',top_bid_price=10.1,top_ask_price=10.2,volume=1000,oi=1000)
    return dict(last_price=float(bars().close.iloc[-1]),oc={'103':dict(ce=leg,pe=dict(leg,security_id='2'))})
def model():
    frames={p:bars(p) for p in (5,15,60)}
    frames[5].iloc[-1,frames[5].columns.get_loc('open')]=float(frames[5].close.iloc[-2])
    frames[5].iloc[-1,frames[5].columns.get_loc('low')]=float(frames[5].open.iloc[-1])-.1
    return smc_expert.evaluate(frames,chain(),{'pcr':1},dict(symbol='NIFTY',kind='index'),'2026-11-24',NOW,set())

class ExpertTests(unittest.TestCase):
    def test_new_break_of_confirmed_pivot_and_mirror(self):
        f=bars();p=smc_expert.patterns(f)
        self.assertTrue(p['CE']['bos']);self.assertFalse(p['PE']['bos'])
        mirror=f.copy();mirror['open']=210-f.open;mirror['close']=210-f.close;mirror['high']=210-f.low;mirror['low']=210-f.high
        self.assertTrue(smc_expert.patterns(mirror)['PE']['bos'])
    def test_missing_or_stale_data_has_no_premium_levels(self):
        out=smc_expert.evaluate({},chain(),{},dict(kind='index'),'2026-11-24',NOW,set())
        self.assertEqual(out['status'],'WATCH');self.assertTrue(out['blockers'])
        with self.assertRaises(ValueError):smc_expert.completed(bars().iloc[:-5],NOW,5)
    def test_future_candles_removed_timezone_and_nonfinite(self):
        f=bars();extra=f.tail(1).copy();extra.index=pd.DatetimeIndex([NOW]);extra['close']=1e9;extra['high']=1e9
        merged=pd.concat([f,extra]);merged.index=merged.index.tz_convert('UTC')
        self.assertEqual(len(smc_expert.completed(merged,NOW,5)),len(f))
        f.iloc[-1,f.columns.get_loc('high')]=float('inf')
        with self.assertRaises(ValueError):smc_expert.completed(f,NOW,5)
    def test_qualified_model_is_expert_not_fake_probability(self):
        m=model();self.assertEqual(m['status'],'AWAITING OPTION CANDLES')
        self.assertIsNone(m['probability_of_win']);self.assertIsNone(m['recommendation']['entry'])
        self.assertIn('NOT TRAINED',m['training_status'])
    def test_chain_contradiction_and_manual_side_do_not_get_levels(self):
        frames={p:bars(p) for p in (5,15,60)}
        m=smc_expert.evaluate(frames,chain(),{'pcr':.2},dict(symbol='NIFTY',kind='index'),'2026-11-24',NOW,set(),requested_side='PE')
        self.assertTrue(any('PCR' in s for s in m['blockers']))
        self.assertTrue(any('conflicts' in s for s in m['blockers']))
        self.assertNotIn('recommendation',m)
    def test_option_own_history_levels_and_chase_rejection(self):
        m=model();f=bars();f[['open','high','low','close']]=f[['open','high','low','close']]*0+10
        f['high']=10.2;f['low']=9.8;f['open']=9.9
        out=smc_expert.premium_levels(m,f,NOW);r=out['recommendation']
        self.assertLess(r['sl'],r['entry']);self.assertLess(r['entry'],r['t1']);self.assertLess(r['t1'],r['t2'])
        self.assertIsNone(m['recommendation']['entry'])
        with self.assertRaises(ValueError):smc_expert.premium_levels(m,f.assign(open=1,high=1.2,low=.8,close=1),NOW)
    def test_market_closed_blocks_model(self):
        with patch('insights.smc_expert.is_market_session',return_value=False):
            m=model()
        self.assertIn('Outside verified market session',m['blockers'])

class WorkflowTests(unittest.TestCase):
    def test_selected_contract_history_drives_new_levels_and_missing_history_blocks(self):
        from types import SimpleNamespace
        from insights.analyse_workflow import analyse
        from insights.brokers.dhan import BrokerUnavailable
        calls=[]
        def history(item,now,minutes,**kwargs):
            if item['kind']=='option':
                calls.append(item)
                f=bars();f['open']=9.9;f['high']=10.2;f['low']=9.8;f['close']=10
                return f
            f=bars(minutes)
            if minutes==5:
                f.iloc[-1,f.columns.get_loc('open')]=f.close.iloc[-2]
                f.iloc[-1,f.columns.get_loc('low')]=f.open.iloc[-1]-.1
            return f
        broker=SimpleNamespace(history=history,expiry_list=lambda _:['2026-11-24'],option_chain=lambda *args:chain())
        service=SimpleNamespace(_lookup=lambda _:dict(symbol='NIFTY',kind='index',id='13',segment='IDX_I'),broker=broker)
        r=analyse(service,'NIFTY',NOW,None,set(),lambda s:s)
        self.assertEqual(r['smc_atm']['entry'],10.2)
        self.assertEqual(calls[0]['id'],'1');self.assertEqual(calls[0]['instrument'],'OPTIDX')
        self.assertEqual(r['smc_model']['status'],'RESEARCH SCENARIO')
        def missing(item,*args,**kwargs):
            if item['kind']=='option':raise BrokerUnavailable('no premium history')
            return history(item,*args,**kwargs)
        broker.history=missing
        r=analyse(service,'NIFTY',NOW,None,set(),lambda s:s)
        self.assertIsNone(r['smc_atm']['entry']);self.assertTrue(r['smc_model']['blockers'])
