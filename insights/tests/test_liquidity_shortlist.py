import tempfile,unittest
from datetime import datetime,timedelta
from unittest.mock import Mock,patch
from insights.config import IST
from insights.liquidity_shortlist import LiquidityShortlist,slot
from insights.service import InsightsService

NOW=datetime(2026,11,12,9,45,tzinfo=IST)
class Broker:
    def __init__(self):self.calls=[];self.fail=False;self.items=[dict(id=str(i),segment='NSE_EQ',symbol='S'+str(i),kind='stock',future={'id':'F'+str(i)} if i%2 else None) for i in range(5)]
    def instruments(self):return self.items
    def longterm_instruments(self):return self.items
    def configured(self):return True
    def market_quotes(self,items,now):
        self.calls.append([x['id'] for x in items])
        if self.fail:return {}
        return {x['id']:dict(last_price=100,volume=(int(x['id'])+1)*200000,change_pct=0,fetched_at=now.isoformat()) for x in items}
class LiquidityTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.b=Broker();self.s=LiquidityShortlist(self.b,self.tmp.name,limit=2,pause=0)
    def tearDown(self):self.tmp.cleanup()
    def test_rank_by_liquidity_not_direction_and_fo_membership(self):
        self.s.refresh(NOW)
        self.assertEqual([x['id'] for x in self.s.selected('intraday',NOW)],['4','3'])
        self.assertEqual([x['id'] for x in self.s.selected('fo-stocks',NOW)],['3','1'])
        self.assertEqual(self.s.selected('intraday',NOW),self.s.selected('swing-trades',NOW))
    def test_persist_restart_and_no_repeat_before_next_hour(self):
        self.s.refresh(NOW);self.s.refresh(NOW+timedelta(minutes=5));self.assertEqual(len(self.b.calls),1)
        fresh=LiquidityShortlist(self.b,self.tmp.name,pause=0);fresh.refresh(NOW+timedelta(minutes=10));self.assertEqual(len(self.b.calls),1)
        fresh.refresh(NOW.replace(hour=10,minute=2));self.assertEqual(len(self.b.calls),2)
    def test_failed_refresh_retains_today_without_retry_storm(self):
        self.s.refresh(NOW);old=self.s.selected('intraday',NOW);self.b.fail=True
        self.s.refresh(NOW.replace(hour=10,minute=0));self.s.refresh(NOW.replace(hour=10,minute=5))
        self.assertEqual(old,self.s.selected('intraday',NOW));self.assertEqual(len(self.b.calls),2)
        self.assertIn('FAILED',self.s.state['status'])
        self.assertEqual(self.s.selected('intraday',NOW+timedelta(days=1)),[])
    def test_full_universe_batches_and_exchange_id_collisions(self):
        self.b.items=[dict(id=str(i),symbol=str(i),kind='stock',segment='NSE_EQ') for i in range(502)]
        self.b.items.append(dict(id='501',symbol='BSE501',kind='stock',segment='BSE_EQ'))
        self.s.refresh(NOW)
        self.assertEqual([len(x) for x in self.b.calls],[500,2,1]);self.assertEqual(self.s.state['quoted'],503)
    def test_invalid_quotes_and_empty_success_remove_old_selections(self):
        self.s.refresh(NOW)
        self.b.market_quotes=lambda items,now:{x['id']:dict(last_price=1,volume=1,change_pct=0,fetched_at=now.isoformat()) for x in items}
        self.s.refresh(NOW.replace(hour=10,minute=0));self.assertEqual(self.s.selected('intraday',NOW),[])
        self.assertEqual(self.s.state['status'],'READY')
    def test_late_start_uses_latest_slot_only(self):
        self.s.refresh(NOW.replace(hour=12,minute=17));self.assertEqual(len(self.b.calls),1)
        self.assertTrue(self.s.state['attempt_slot'].endswith(':720'))
    def test_no_fo_fallback_when_list_empty(self):
        svc=InsightsService(self.b,self.tmp.name);svc._opening_setups=Mock();svc._fib_setups=Mock()
        svc.scan_fo(NOW);svc._opening_setups.assert_not_called();svc._fib_setups.assert_not_called()
    def test_swing_pass_receives_only_stored_list(self):
        svc=InsightsService(self.b,self.tmp.name);svc.liquidity=self.s;self.s.refresh(NOW);svc.scan_longterm=Mock(return_value={})
        svc.scan_swing_shortlist(NOW)
        self.assertEqual(svc.scan_longterm.call_args.kwargs['selected'],self.s.selected('swing-trades',NOW))
        self.assertTrue(svc.scan_longterm.call_args.kwargs['swing_only'])
    def test_swing_empty_selection_does_not_expand_or_update_multibagger(self):
        svc=InsightsService(self.b,self.tmp.name)
        original=svc.snapshot('multibagger')
        self.b.longterm_instruments=Mock(side_effect=AssertionError('No broad master inside strategy pass'))
        with patch('insights.service.multibagger.evaluate') as multi:
            svc.scan_longterm(NOW,selected=[],swing_only=True)
            multi.assert_not_called()
        self.assertEqual(svc.snapshot('multibagger'),original)
        self.b.longterm_instruments.assert_not_called()
    def test_fo_strategy_uses_only_its_own_list(self):
        svc=InsightsService(self.b,self.tmp.name)
        one=dict(self.b.items[0],future=None)
        svc.liquidity.state={'date':NOW.date().isoformat(),'lists':{'fo-stocks':[one]}}
        svc._opening_setups=Mock(return_value=[]);svc._fib_setups=Mock(return_value=[])
        svc.scan_fo(NOW)
        svc._opening_setups.assert_called_once_with(one,NOW)
        svc._fib_setups.assert_called_once_with(one,NOW)
