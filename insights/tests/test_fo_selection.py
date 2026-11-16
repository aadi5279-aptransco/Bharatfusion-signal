import unittest
from insights.fo_selection import quality,top_eight

class SelectionTests(unittest.TestCase):
    def plan(self,symbol='A',score=85,side='CE'):
        return dict(underlying=symbol,direction=side,strike=100,security_id='1',selection_score=score,option_spread_pct=1)
    def chain(self,bid=9.9):
        return dict(oc={'100':{'ce':dict(top_bid_price=bid,top_ask_price=10,volume=1000,oi=2000)}})
    def test_cap_dedupe_and_order(self):
        items=[self.plan(str(i),80+i) for i in range(12)]
        out=top_eight(items+[self.plan('11',95)])
        self.assertEqual(len(out),8);self.assertEqual(len({p['underlying'] for p in out}),8)
        self.assertEqual(out[0]['selection_score'],95)
        self.assertEqual([p['selection_rank'] for p in out],list(range(1,9)))
    def test_no_padding_and_conflicting_directions(self):
        self.assertEqual(len(top_eight([self.plan()])),1)
        self.assertEqual(top_eight([self.plan(),self.plan(side='PE')]),[])
        self.assertEqual(top_eight([self.plan(score=74),self.plan(score=float('nan'))]),[])
    def test_quality_requires_tighter_spread_and_real_oi(self):
        self.assertIsNotNone(quality(self.plan(),self.chain(),{'rvol':2},{'oi_change_pct':2}))
        self.assertIsNone(quality(self.plan(),self.chain(9.5),{'rvol':2},{'oi_change_pct':2}))
        c=self.chain();c['oc']['100']['ce']['oi']=0
        self.assertIsNone(quality(self.plan(),c,{'rvol':2},{'oi_change_pct':2}))
    def test_missing_nonfinite_or_weak_evidence_rejected(self):
        for smc in ({},{'rvol':float('inf')},{'rvol':1}):
            self.assertIsNone(quality(self.plan(),self.chain(),smc,{'oi_change_pct':2}))
        self.assertIsNone(quality(dict(self.plan(),security_id=''),self.chain(),{'rvol':2},{'oi_change_pct':2}))

if __name__=='__main__':unittest.main()

class ServiceSelectionTests(unittest.TestCase):
    def test_service_publishes_only_eight_and_filters_other_watch_symbols(self):
        import tempfile
        from unittest.mock import Mock,patch
        from datetime import datetime
        from insights.config import IST
        from insights.service import InsightsService
        from insights.tests.test_service import FakeBroker
        from insights.tests.test_market_insights import history,chain
        now=datetime(2026,11,16,12,0,tzinfo=IST)
        broker=FakeBroker();broker.history=Mock(return_value=history());broker.option_chain=Mock(return_value=chain())
        broker.expiry_list=Mock(return_value=['2026-11-24'])
        smc=dict(available=True,rvol=2,up_breakout=True,down_breakdown=False,bos_up=True,bos_down=False,choch_up=False,choch_down=False,fvg_up=False,fvg_down=False)
        with tempfile.TemporaryDirectory() as root:
            service=InsightsService(broker,root)
            service.liquidity.selected=Mock(return_value=[dict(symbol='S'+str(i),future={'id':i}) for i in range(12)])
            service._opening_setups=Mock(side_effect=lambda item,now:[dict(underlying=item['symbol'],state='DIRECTION_READY')])
            service._fib_setups=Mock(return_value=[]);service._update=Mock()
            with patch('insights.service.recent_frame',return_value=True),patch('insights.service.futures.buildup',return_value=dict(direction='CE',oi_change_pct=2,reasons=[])),patch('insights.service.advanced_smc.structure',return_value=smc),patch('insights.service.advanced_smc.trend',return_value='UP'),patch('insights.service.cycle_wave.annotate',side_effect=lambda p,*args:p):
                result=service.scan_fo(now)
            self.assertEqual(len(result),8)
            payload=service._update.call_args.args[1]
            self.assertEqual(payload['eligible_before_cap'],12)
            self.assertEqual(payload['qualified'],8)
            self.assertEqual({r['underlying'] for r in payload['opening_setups']},{r['underlying'] for r in result})
