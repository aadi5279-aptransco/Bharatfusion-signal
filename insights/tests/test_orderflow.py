import json,struct,tempfile,unittest
from datetime import datetime
from pathlib import Path
from collections import deque
from types import SimpleNamespace
from insights.config import IST
from insights.orderflow import decode,FlowEngine,analyse,stacked,IndexOrderFlow

BASE=int(datetime(2026,11,16,10,0,tzinfo=IST).timestamp())
def packet(t=BASE,volume=100,price=100,ltq=10,bid=99.95,ask=100.05):
    return dict(segment='NSE_FNO',id='123',ts=t,price=price,ltq=ltq,volume=volume,oi=1000,bid=bid,ask=ask,bid_qty=2000,ask_qty=2000)
def binary(p):
    head=struct.pack('<BHBI',8,162,2,int(p['id']))
    body=struct.pack('<fHIfIIIIIIffff',p['price'],p['ltq'],p['ts'],p['price'],p['volume'],100,100,p['oi'],1000,900,100,100,101,99)
    depth=struct.pack('<IIHHff',p['bid_qty'],p['ask_qty'],1,1,p['bid'],p['ask'])*5
    return head+body+depth

def bar(start=BASE):
    return dict(start=start,open=100,high=101,low=99,close=100.8,levels={2000:[10,100],2001:[10,100],2002:[10,100],2003:[10,100]},unknown=0,partial=False,bid_watch=deque(maxlen=30),ask_watch=deque(maxlen=30))
class FlowTests(unittest.TestCase):
    def test_binary_contract_fields_and_concatenation(self):
        p=packet();d=decode(binary(p)*2);self.assertEqual(len(d),2)
        self.assertEqual(d[0]['volume'],100);self.assertEqual(d[0]['oi'],1000);self.assertAlmostEqual(d[0]['bid'],99.95,places=3)
    def test_malformed_and_disconnect_rejected(self):
        for value in (b'',b'bad',binary(packet())[:-1]):
            if not value:continue
            with self.assertRaises(ValueError):decode(value)
        with self.assertRaises(ConnectionError):decode(struct.pack('<BHBIH',50,10,2,123,805))
    def test_initial_volume_baseline_and_duplicate_ltq(self):
        e=FlowEngine(.05);p=packet(volume=10000);e.feed(p,BASE);self.assertIsNone(e.bar)
        e.feed(packet(t=BASE+1,volume=10010,price=100.05),BASE+1)
        self.assertEqual(sum(sum(v) for v in e.bar['levels'].values()),10)
        e.feed(packet(t=BASE+1,volume=10010,price=100.05),BASE+1)
        self.assertEqual(sum(sum(v) for v in e.bar['levels'].values()),10)
    def test_aggregated_volume_not_all_assigned_to_last_trade(self):
        e=FlowEngine(.05);e.feed(packet(),BASE);e.feed(packet(t=BASE+1,volume=200,price=100.05,ltq=10),BASE+1)
        self.assertEqual(e.bar['unknown'],90);self.assertEqual(sum(sum(v) for v in e.bar['levels'].values()),10)
    def test_unclassifiable_unchanged_price_is_unknown(self):
        e=FlowEngine(.05);e.feed(packet(),BASE);e.feed(packet(t=BASE+1,volume=110),BASE+1)
        self.assertEqual(e.bar['unknown'],10)
    def test_stale_future_invalid_and_offgrid(self):
        e=FlowEngine(.05)
        self.assertFalse(e.feed(packet(),BASE+11));self.assertFalse(e.feed(packet(t=BASE+1),BASE))
        with self.assertRaises(ValueError):e.feed(packet(price=100.02),BASE)
    def test_gap_reset_and_day_reset(self):
        e=FlowEngine(.05);e.feed(packet(),BASE);e.cvd=100
        e.feed(packet(t=BASE+31,volume=130),BASE+31);self.assertEqual(e.cvd,0);self.assertIsNone(e.bar)
        e.cvd=50;e.feed(packet(t=BASE+86400,volume=10),BASE+86400);self.assertEqual(e.cvd,0)
    def test_out_of_order_does_not_change_baseline(self):
        e=FlowEngine(.05);e.feed(packet(t=BASE+3),BASE+3);self.assertFalse(e.feed(packet(t=BASE+2,volume=120),BASE+3));self.assertEqual(e.last['volume'],100)
    def test_diagonal_stacked_and_warmup_gate(self):
        b=bar();self.assertIsNone(analyse(b,[],.05,1000)['signal'])
        h=[{'volume':400,'range':2}]*20;r=analyse(b,h,.05,1000)
        self.assertEqual(r['signal'],'LONG');self.assertEqual(len(r['buy_imbalances']),3)
        self.assertTrue(stacked([1,2,3]));self.assertFalse(stacked([1,3,4]))
    def test_unknown_coverage_blocks_signal(self):
        b=bar();b['unknown']=1000
        self.assertIsNone(analyse(b,[{'volume':400,'range':2}]*20,.05,1000)['signal'])
    def test_absorption_requires_same_price_defense(self):
        b=bar();b.update(high=100.5,low=100,close=100.4,levels={2000:[1000,10]})
        b['bid_watch']=deque([(2000,2000)]*30,maxlen=30)
        h=[{'volume':400,'range':2}]*20
        self.assertEqual(analyse(b,h,.05,1000)['signal'],'LONG')
        b['bid_watch'][0]=(1999,2000);self.assertIsNone(analyse(b,h,.05,1000)['signal'])
    def test_next_bar_confirmation_and_levels(self):
        e=FlowEngine(.05);e.history=deque([dict(volume=400,range=2,signal=None,high=101,low=99,cvd=0)]*20,maxlen=120)
        e.bar=bar();e.bar['low']=99.5;e.close();self.assertIsNone(e.signal)
        e.bar=bar(BASE+60);e.bar.update(close=101,high=101.1);e.close()
        self.assertEqual(e.signal['direction'],'LONG');self.assertLess(e.signal['sl'],e.signal['entry']);self.assertGreater(e.signal['t2'],e.signal['t1'])
    def test_stale_signal_hidden_and_touch_invalidated(self):
        e=FlowEngine(.05);e.feed(packet(),BASE)
        e.signal=dict(direction='LONG',sl=99,t1=101,confirmed_at=BASE)
        self.assertIsNone(e.snapshot(BASE+11)['signal'])
        e.feed(packet(t=BASE+1,price=101,volume=110),BASE+1);self.assertIsNone(e.signal)
    def test_quote_only_book_moves_break_defense(self):
        e=FlowEngine(.05);e.feed(packet(),BASE);e.feed(packet(t=BASE+1,volume=110,price=100.05),BASE+1)
        e.feed(packet(t=BASE+1,volume=110,price=100.05,bid=99.9),BASE+1)
        self.assertEqual(e.bar['bid_watch'][-1][0],1998)
    def test_recording_and_api_do_not_leak_credentials(self):
        import threading
        from insights.api import create_app
        with tempfile.TemporaryDirectory() as root:
            manager=IndexOrderFlow(SimpleNamespace(),root,lambda:set(),threading.Lock())
            manager.engines={'NSE_FNO:123':FlowEngine(.05)};manager.contracts={'NSE_FNO:123':dict(id='123',symbol='TEST')}
            manager.ingest(binary(packet()),BASE)
            lines=list((Path(root)/'index_orderflow').glob('*.jsonl'));self.assertEqual(len(lines),1)
            record=json.loads(lines[0].read_text());self.assertEqual(record['tick_size'],.05);self.assertNotIn('token',record)
            client=create_app(SimpleNamespace(index_orderflow=manager)).test_client()
            self.assertEqual(client.get('/api/v1/market-insights/index-orderflow').status_code,200)
    def test_replay_matches_live_engine_and_connection_reset(self):
        from insights.orderflow_replay import replay
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ticks.jsonl';rows=[];e=FlowEngine(.05)
            for i in range(130):
                p=packet(t=BASE+i,volume=100+i*10,price=100.05 if i%2 else 100)
                e.feed(p,BASE+i);rows.append(dict(instrument='TEST',stream_epoch=1,tick_size=.05,received=BASE+i,packet=p))
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            result=replay(path)['instruments']['TEST'];self.assertEqual(result['cvd'],e.snapshot(BASE+129)['cvd'])
            self.assertEqual(result['warmup_bars'],e.snapshot(BASE+129)['warmup_bars'])
            rows[-1]['stream_epoch']=2;path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(replay(path)['instruments']['TEST']['warmup_bars'],0)
    def test_bearish_confirmation_has_stop_above_entry(self):
        e=FlowEngine(.05);e.history=deque([dict(volume=400,range=2,signal=None,high=101,low=99,cvd=0)]*20,maxlen=120)
        b=bar();b['levels']={2000:[100,10],2001:[100,10],2002:[100,10],2003:[100,10]};b.update(close=100,high=100.5)
        e.bar=b;e.close();b=bar(BASE+60);b['levels']={2000:[100,10]};b['close']=99.9;e.bar=b;e.close()
        self.assertEqual(e.signal['direction'],'SHORT');self.assertGreater(e.signal['sl'],e.signal['entry']);self.assertLess(e.signal['t2'],e.signal['t1'])

    def test_snapshot_blocks_already_crossed_new_plan(self):
        e=FlowEngine(.05);e.feed(packet(price=102),BASE)
        e.signal=dict(direction='LONG',sl=99,t1=101,confirmed_at=BASE)
        self.assertIsNone(e.snapshot(BASE)['signal'])
    def test_targets_respect_instrument_tick_grid(self):
        e=FlowEngine(.05);e.history=deque([dict(volume=400,range=2,signal=None,high=101,low=99,cvd=0)]*20,maxlen=120)
        e.bar=bar();e.bar['low']=99.5;e.close()
        e.bar=bar(BASE+60);e.bar.update(close=101,high=101.1);e.close()
        for key in ('entry','sl','t1','t2'):
            self.assertAlmostEqual(e.signal[key]/.05,round(e.signal[key]/.05))
