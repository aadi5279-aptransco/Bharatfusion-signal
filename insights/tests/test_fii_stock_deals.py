"""NSE cash bulk/block report + exact verified FPI/FII attribution regression tests."""
import csv
import io
import json
import tempfile
import unittest
from datetime import datetime,date
from pathlib import Path
from unittest.mock import Mock,patch
from insights.config import IST
from insights.fii_stock_deals import DealStore,FIIStockDeals,parse_report,SOURCE_PAGE

DAY=date(2026,11,12)
NOW=datetime(2026,11,13,20,0,tzinfo=IST)
HEAD=['Date','Symbol','Security Name','Client Name','Buy / Sell',
      'Quantity Traded','Trade Price / Wght. Avg. Price','Remarks']


def csv_report(day=DAY):
    b=io.StringIO();w=csv.writer(b);w.writerow(HEAD)
    for client,stock,side in (
      ('REGISTERED FPI TEST','HDFCLIFE','BUY'),
      ('REGISTERED FPI TEST','GRASIM','SELL'),
      ('UNKNOWN INSTITUTIONAL FUND','BAJFINANCE','BUY')):
        w.writerow([day.strftime('%d-%b-%Y'),stock,stock,client,
                    side,'1,00,000','850.50','-'])
    return b.getvalue().encode('utf-8')


def registry(root):
    (Path(root)/'verified_fpi_clients.json').write_text(json.dumps(
      {'clients':[{'client_name':'REGISTERED FPI TEST','category':'FPI',
         'verification_source':'https://www.sebi.gov.in/'}]}),encoding='utf-8')


class StockDealTests(unittest.TestCase):
    def test_official_nse_csv_parsing(self):
        rows=parse_report(csv_report(),'bulk')
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]['quantity'],100000)
        self.assertEqual(rows[0]['price'],850.5)
        self.assertEqual(rows[1]['side'],'SELL')
    def test_html_missing_columns_and_malformed_quantity_fail_closed(self):
        with self.assertRaises(ValueError):parse_report(b'<html>access denied</html>','bulk')
        with self.assertRaises(ValueError):parse_report(b'Invalid,Column\nfoo,bar','block')
        with self.assertRaises(ValueError):
            parse_report(csv_report().replace(b'1,00,000',b'not-a-number'),'bulk')
    def test_separate_buy_sell_only_exact_verified_registry(self):
        with tempfile.TemporaryDirectory() as root:
            registry(root)
            flow=FIIStockDeals(root,lambda:set())
            flow.store.ingest(csv_report(),'bulk',DAY,SOURCE_PAGE)
            snap=flow.snapshot(NOW)
            self.assertEqual([x['symbol'] for x in snap['bought']],['HDFCLIFE'])
            self.assertEqual([x['symbol'] for x in snap['sold']],['GRASIM'])
            self.assertEqual(snap['unclassified_disclosed_rows'],1)
            self.assertEqual(snap['unclassified_examples'][0]['symbol'],'BAJFINANCE')
            self.assertIn('NSE DISCLOSED',snap['data_scope'])
    def test_without_verified_registry_never_invents_fii_identity(self):
        with tempfile.TemporaryDirectory() as root:
            flow=FIIStockDeals(root,lambda:set())
            flow.store.ingest(csv_report(),'bulk',DAY,SOURCE_PAGE)
            snap=flow.snapshot(NOW)
            self.assertEqual(snap['bought'],[])
            self.assertEqual(snap['sold'],[])
            self.assertEqual(snap['unclassified_disclosed_rows'],3)
    def test_sqlite_closes_windows_handles_and_report_idempotence(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'deals.sqlite'
            store=DealStore(path)
            for _ in range(2):store.ingest(csv_report(),'bulk',DAY,SOURCE_PAGE)
            self.assertEqual(len(store.recent()),3)
            renamed=path.with_name('renamed.sqlite')
            path.replace(renamed);renamed.replace(path)
            self.assertTrue(store.has_day('bulk',DAY))
    def test_cannot_ingest_report_for_another_day(self):
        with tempfile.TemporaryDirectory() as root:
            store=DealStore(Path(root)/'deals.sqlite')
            with self.assertRaises(ValueError):
                store.ingest(csv_report(),'bulk',date(2026,11,11),SOURCE_PAGE)
            self.assertFalse(store.has_day('bulk',DAY))
    def test_local_official_csv_import(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'nse_disclosed_deals';folder.mkdir()
            (folder/'bulk_2026-11-12.csv').write_bytes(csv_report())
            flow=FIIStockDeals(root,lambda:set())
            imported=flow.ingest_local_files()
            self.assertEqual(imported[0]['rows'],3)
            self.assertEqual(flow.ingest_local_files(),[])
    def test_broker_api_read_only_and_refresh_returns_202(self):
        class MinimalBroker:
            def configured(self):return True
        from insights.service import InsightsService
        from insights.api import create_app
        with tempfile.TemporaryDirectory() as root:
            svc=InsightsService(MinimalBroker(),root)
            svc.fii_deals_manager.start=Mock(return_value={'status':'STARTED'})
            client=create_app(svc).test_client()
            r=client.get('/api/v1/market-insights/fii-stock-deals')
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.json['bought'],[])
            self.assertEqual(client.post('/api/v1/market-insights/fii-stock-deals/refresh').status_code,202)
            self.assertFalse(svc.health()['orders_enabled'])
    def test_access_denied_does_not_retry_multiple_dates(self):
        with tempfile.TemporaryDirectory() as root:
            fetcher=Mock(side_effect=PermissionError('HTTP 403'))
            flow=FIIStockDeals(root,lambda:set(),fetcher=fetcher)
            result=flow.sync(NOW,days=3)
            self.assertEqual(result['status'],'NSE ACCESS BLOCKED')
            self.assertEqual(fetcher.call_count,1)


if __name__=='__main__':unittest.main()
