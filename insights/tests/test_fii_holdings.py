"""Ownership comparisons never masquerade as verified daily cash deals."""
import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock
from insights.config import IST
from insights.fii_holdings import FIIHoldings,parse_company,parse_csv,symbols_from

NOW=datetime(2026,11,13,20,tzinfo=IST)
URL='https://www.screener.in/company/DEMO/consolidated/'

def page(symbol='DEMO',previous='5.00%',current='6.25%',pq='Jun 2026',cq='Sep 2026'):
    return (f'<a href="https://www.nseindia.com/get-quotes/equity?symbol={symbol}">NSE</a>'
      '<div id="quarterly-shp"><div><table><tr><th></th>'
      f'<th>{pq}</th><th>{cq}</th></tr>'
      '<tr><td>Promoters +</td><td>70%</td><td>71%</td></tr>'
      f'<tr><td><button>FIIs <span>+</span></button></td><td>{previous}</td><td>{current}</td></tr>'
      '</table></div></div><div id="yearly-shp"><table><tr><th></th><th>Mar 2025</th><th>Mar 2026</th></tr>'
      '<tr><td>FIIs +</td><td>90%</td><td>1%</td></tr></table></div>').encode()

class HoldingTests(unittest.TestCase):
    def test_quarterly_table_only_and_percentage_points(self):
        r=parse_company(page(),'DEMO',NOW,URL)
        self.assertEqual(r['change_pp'],1.25)
        self.assertEqual(r['direction'],'INCREASED')
        self.assertEqual(r['current_quarter'],'2026-09-30')
    def test_reduction_and_unchanged(self):
        self.assertEqual(parse_company(page(current='4%'),'DEMO',NOW,URL)['direction'],'DECREASED')
        self.assertEqual(parse_company(page(current='5%'),'DEMO',NOW,URL)['direction'],'UNCHANGED')
    def test_missing_latest_does_not_fall_back_or_become_zero(self):
        for value in ('','—','NaN','101%','-1%'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_company(page(current=value),'DEMO',NOW,URL)
    def test_future_gapped_and_wrong_symbol_rejected(self):
        for raw in (page(cq='Dec 2026'),page(pq='Mar 2026'),page(symbol='OTHER'),b'<html>login</html>'):
            with self.assertRaises(ValueError):parse_company(raw,'DEMO',NOW,URL)
    def test_symbol_validation_and_dedup(self):
        self.assertEqual(symbols_from('demo, DEMO OTHER'),['DEMO','OTHER'])
        for value in ('','https://localhost/a',None,' '.join('S'+str(i) for i in range(201))):
            with self.assertRaises(ValueError):symbols_from(value)
    def test_dated_csv(self):
        raw=b'Symbol,Previous pct,Current pct,Previous quarter,Current quarter\nDEMO,5,4,2026-06-30,2026-09-30\n'
        r=parse_csv(raw,NOW)[0]
        self.assertEqual(r['change_pp'],-1)
        self.assertTrue(r['period_verified'])
        self.assertIn('USER IMPORT',r['source'])
    def test_screener_export_is_period_unverified_and_no_guessed_symbol(self):
        raw=b'Name,FII holding,Change in FII holding\nDemo Limited,6.25,1.25\nOther Limited,0,-2\n'
        rows=parse_csv(raw,NOW)
        self.assertEqual(rows[0]['previous_pct'],5)
        self.assertFalse(rows[0]['period_verified'])
        self.assertIsNone(rows[0]['symbol'])
        self.assertEqual(rows[1]['direction'],'DECREASED')
    def test_bad_csv_rejected_atomically(self):
        for raw in (b'Name,FII holding,Change in FII holding\nDemo,,2\n',
                    b'Name,FII holding,Change in FII holding\nDemo,1,2\n',
                    b'Name,FII holding,Change in FII holding\nDemo,5,1\nDemo,6,1\n',
                    b'Name,FII holding,Change in FII holding\nDemo,5,NaN\n',
                    b'<html>login</html>',b''):
            with self.assertRaises(ValueError):parse_csv(raw,NOW)
    def test_scan_cache_and_restart_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            fetcher=Mock(return_value=(page(),URL));m=FIIHoldings(root,fetcher,delay=0)
            m._scan(['DEMO'],NOW);m._scan(['DEMO'],NOW)
            self.assertEqual(fetcher.call_count,1)
            snap=FIIHoldings(root).snapshot(NOW)
            self.assertEqual(len(snap['increased']),1)
            self.assertEqual(snap['coverage']['cached'],1)
            self.assertEqual(snap['decreased'],[])
            # Closing handles matters on Windows.
            renamed=Path(root)/'moved.sqlite';m.path.replace(renamed);renamed.replace(m.path)
    def test_access_denial_stops_and_preserves_previous_list(self):
        with tempfile.TemporaryDirectory() as root:
            m=FIIHoldings(root,Mock(return_value=(page(),URL)),delay=0)
            m._scan(['DEMO'],NOW)
            m.fetcher=Mock(side_effect=PermissionError('Denied'))
            m._scan(['OTHER','THIRD'],NOW)
            snap=m.snapshot(NOW)
            self.assertEqual(m.fetcher.call_count,1)
            self.assertEqual(snap['refresh']['status'],'ACCESS BLOCKED')
            self.assertEqual(snap['increased'][0]['symbol'],'DEMO')
            self.assertEqual(snap['refresh']['coverage']['not_attempted'],['THIRD'])
    def test_partial_scan_reports_missing_symbols(self):
        with tempfile.TemporaryDirectory() as root:
            m=FIIHoldings(root,Mock(side_effect=[(page(),URL),ValueError('No report')]),delay=0)
            m._scan(['DEMO','OTHER'],NOW);s=m.snapshot(NOW)
            self.assertEqual(s['coverage']['available'],1)
            self.assertEqual(s['coverage']['requested'],2)
            self.assertEqual(s['coverage']['failures'][0]['symbol'],'OTHER')
    def test_import_failure_preserves_data(self):
        with tempfile.TemporaryDirectory() as root:
            m=FIIHoldings(root)
            m.import_csv(b'Name,FII holding,Change in FII holding\nDemo,5,1\n',NOW)
            with self.assertRaises(ValueError):m.import_csv(b'Name,FII holding\nInvalid,5\n',NOW)
            self.assertEqual(len(m.snapshot(NOW)['increased']),1)
    def test_stale_reporting_date_is_visible(self):
        with tempfile.TemporaryDirectory() as root:
            m=FIIHoldings(root,Mock(return_value=(page(pq='Dec 2025',cq='Mar 2026'),URL)),delay=0)
            m._scan(['DEMO'],NOW)
            self.assertTrue(m.snapshot(NOW)['increased'][0]['stale_quarter'])
    def test_api_import_and_validation(self):
        from insights.service import InsightsService
        from insights.api import create_app
        class Broker:
            def configured(self):return True
        with tempfile.TemporaryDirectory() as root:
            s=InsightsService(Broker(),root);client=create_app(s).test_client()
            s.fii_holdings_manager.start=Mock(return_value={'status':'STARTED'})
            self.assertEqual(client.post('/api/v1/market-insights/fii-holdings/refresh',json={'symbols':'DEMO'}).status_code,202)
            self.assertEqual(client.post('/api/v1/market-insights/fii-holdings/refresh',json=[]).status_code,400)
            self.assertEqual(client.post('/api/v1/market-insights/fii-holdings/refresh',json={'symbols':'DEMO'},headers={'Origin':'https://other.example'}).status_code,403)
            r=client.post('/api/v1/market-insights/fii-holdings/import',data={'file':(io.BytesIO(b'Name,FII holding,Change in FII holding\nDemo,5,1\n'),'data.csv')})
            self.assertEqual(r.status_code,200)
            self.assertEqual(len(client.get('/api/v1/market-insights/fii-holdings').json['increased']),1)
            self.assertIn(b'Previous quarter',client.get('/api/v1/market-insights/fii-holdings/template').data)
            self.assertEqual(client.get('/api/v1/market-insights/fii-stock-deals').json['bought'],[])
            self.assertFalse(s.health()['orders_enabled'])

if __name__=='__main__':unittest.main()
