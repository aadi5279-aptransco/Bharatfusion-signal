"""ATM option suggestions, quote safeguards, mapped tickers and top-20 movers.

Synthetic, offline fixtures: no real quotes or claimed backtest accuracy.
"""
import tempfile
import unittest
from datetime import datetime
import pandas as pd
from insights.config import IST
from insights import atm_recommendation
from insights.service import InsightsService


NOW=datetime(2026,11,13,9,30,tzinfo=IST)


def five_bars(down=False):
    idx=pd.date_range('2026-11-13 09:15',periods=3,freq='5min',tz=IST)
    close=[100.,98.,97.] if down else [100.,102.,103.]
    return pd.DataFrame(dict(open=[100.,101.,102.] if not down else [100.,99.,98.],
        high=[101.,103.,104.] if not down else [101.,100.,99.],
        low=[99.,100.,101.] if not down else [99.,97.,96.],
        close=close,volume=[1000]*3),index=idx)


def option_chain(ask=10,bid=9.8,volume=100):
    def legs(sid):
        return dict(ce=dict(security_id=sid,oi=100,previous_oi=90,
             top_ask_price=ask,top_bid_price=bid,volume=volume),
             pe=dict(security_id='PE'+sid,oi=100,previous_oi=90,
             top_ask_price=ask,top_bid_price=bid,volume=volume))
    return dict(last_price=101.8,oc={'100':legs('CE100'),'105':legs('CE105')})


class AnalyseATMBroker:
    def configured(self):return True
    def instruments(self):
        return [dict(kind='index',symbol='NIFTY',segment='IDX_I',
                   instrument='INDEX',id='13'),
            dict(kind='stock',symbol='BAJAJ FINANCE LIMITED',ticker='',
                segment='NSE_EQ',instrument='EQUITY',id='317',
                future=dict(symbol='BAJFINANCE-Nov2026-FUT',id='900',
                            segment='NSE_FNO',instrument='FUTSTK'))]
    def market_quotes(self,items,now):
        return {'317':dict(change_pct=1.5,last_price=100,volume=1000,
                    baseline_type='PREVIOUS_CLOSE',fetched_at=now.isoformat())}
    def history(self,item,now,minutes=5,lookback_days=10):
        if minutes==5:return five_bars()
        return pd.DataFrame()
    def expiry_list(self,item):return ['2026-11-20']
    def option_chain(self,item,expiry):return option_chain()


class ATMTests(unittest.TestCase):
    def test_atm_ce_contract_and_premium_risk_levels_from_real_fixture_bid_ask(self):
        report=atm_recommendation.evaluate(option_chain(),'2026-11-20',
             'NIFTY',NOW,set(),five=five_bars())
        self.assertEqual(report['direction'],'CE')
        self.assertEqual(report['atm_strike'],100)
        self.assertEqual(report['contract']['security_id'],'CE100')
        self.assertEqual(report['entry'],10)
        self.assertEqual(report['sl'],8)
        self.assertEqual(report['t1'],13)
        self.assertEqual(report['t2'],15)
        self.assertIsNone(report['probability_of_win'])
        self.assertTrue(report['research_only'])
        self.assertEqual(report['quote_freshness'],'NOT VERIFIED')
    def test_atm_pe_uses_lower_break_and_buys_put_premium(self):
        report=atm_recommendation.evaluate(option_chain(),'2026-11-20',
             'NIFTY',NOW,set(),five=five_bars(down=True))
        self.assertEqual(report['direction'],'PE')
        self.assertEqual(report['contract']['security_id'],'PECE100')
        self.assertGreater(report['t1'],report['entry'])
    def test_no_bias_keeps_atm_strike_but_not_entry(self):
        report=atm_recommendation.evaluate(option_chain(),'2026-11-20',
             'NIFTY',NOW,set())
        self.assertEqual(report['atm_strike'],100)
        self.assertIsNone(report['entry'])
        self.assertIn('WATCH',report['status'])
    def test_spread_above_five_percent_has_no_premium_plan(self):
        report=atm_recommendation.evaluate(option_chain(ask=10,bid=8),
             '2026-11-20','NIFTY',NOW,set(),five=five_bars())
        self.assertEqual(report['atm_strike'],100)
        self.assertIsNone(report['entry'])
        self.assertIn('ILLIQUID',report['status'])
    def test_no_security_id_blocks_scenario(self):
        chain=option_chain()
        chain['oc']['100']['ce'].pop('security_id')
        report=atm_recommendation.evaluate(chain,'2026-11-20','NIFTY',
             NOW,set(),five=five_bars())
        self.assertIsNone(report['entry'])
        self.assertIn('SECURITY ID',report['status'])
    def test_manual_side_not_independently_supported_is_watch_only(self):
        report=atm_recommendation.evaluate(option_chain(),'2026-11-20',
             'NIFTY',NOW,set(),five=five_bars(),requested_side='PE')
        self.assertEqual(report['direction'],'PE')
        self.assertIsNone(report['entry'])
        self.assertIn('UNCONFIRMED',report['status'])
    def test_manual_fno_future_root_resolves(self):
        with tempfile.TemporaryDirectory() as directory:
            svc=InsightsService(AnalyseATMBroker(),directory)
            self.assertEqual(svc._lookup('BAJFINANCE')['id'],'317')
            hints=svc.analyse_choices(NOW)['fno_symbols']
            self.assertEqual(hints[0]['ticker'],'BAJFINANCE')
            r=svc.analyse('BAJFINANCE',NOW)
            self.assertEqual(r['symbol'],'BAJAJ FINANCE LIMITED')
            self.assertEqual(r['atm_recommendation']['atm_strike'],100)
            self.assertIsNone(r['probability_of_win'])
            self.assertEqual(svc.journal.signals(),[])
    def test_no_chain_still_returns_cash_research(self):
        with tempfile.TemporaryDirectory() as directory:
            svc=InsightsService(AnalyseATMBroker(),directory)
            svc.broker.option_chain=lambda *args: (_ for _ in ()).throw(ValueError('Not available'))
            r=svc.analyse('BAJFINANCE',NOW)
            self.assertIsNone(r['atm_recommendation']['entry'])
            self.assertTrue(len(r['candles'])>0)
    def test_top_twenty_each_and_manual_fno_list(self):
        class ManyBroker(AnalyseATMBroker):
            def instruments(self):
                return [dict(kind='stock',symbol='S%02d'%i,id=str(i),
                        segment='NSE_EQ',instrument='EQUITY') for i in range(50)]
            def market_quotes(self,items,now):
                return {str(i):dict(change_pct=i-24.5,last_price=100,
                         volume=10,baseline_type='PREVIOUS_CLOSE',
                         fetched_at=now.isoformat()) for i in range(50)}
        with tempfile.TemporaryDirectory() as directory:
            svc=InsightsService(ManyBroker(),directory)
            result=svc.analyse_choices(NOW)
            self.assertEqual(len(result['gainers']),20)
            self.assertEqual(len(result['losers']),20)
            self.assertEqual(len(result['fno_symbols']),50)
            self.assertEqual(result['gainers'][0]['symbol'],'S49')
            self.assertEqual(result['losers'][0]['symbol'],'S00')


if __name__=='__main__':unittest.main()
