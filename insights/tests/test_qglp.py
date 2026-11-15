import csv,io,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from insights.config import IST
from insights.qglp import COLUMNS,parse,evaluate,QGLPResearch
TODAY=datetime.now(IST).date()
def row(name='Example',**kw):
    r=dict(name=name,mcap_cr=1000,roce=20,roe=18,sales_g3=20,profit_g3=25,de=.3,pe=20,promoter=60,pledge=0,cfo3=300,pat3=300,symbol='',sector='Manufacturing');r.update(kw);return r
def raw(rows):
    b=io.StringIO();w=csv.DictWriter(b,fieldnames=list(COLUMNS.values()));w.writeheader();w.writerows(rows);return b.getvalue().encode()
def bundle(rows):return dict(rows=rows,asof=str(TODAY),period_end=str(TODAY-timedelta(days=60)),source='Test export')
class QGLPTests(unittest.TestCase):
    def test_uploaded_headers_numeric_and_bom(self):
        b=io.StringIO();w=csv.writer(b);w.writerow(COLUMNS.keys());r=row(mcap_cr='1,000',roce='20%');w.writerow(r.values())
        p=parse(('\ufeff'+b.getvalue()).encode());self.assertEqual(p[0]['mcap_cr'],1000);self.assertEqual(p[0]['roce'],20)
    def test_missing_headers_fail_closed(self):
        with self.assertRaises(ValueError):parse(b'Name,ROCE\nTest,20\n')
    def test_missing_pledge_not_zero(self):
        r=evaluate(bundle(parse(raw([row(pledge='')]))),TODAY)['rows'][0]
        self.assertEqual(r['status'],'UNVERIFIED');self.assertIsNone(r['score'])
    def test_nonfinite_values_not_qualified(self):
        r=evaluate(bundle(parse(raw([row(roe='inf')]))),TODAY)['rows'][0];self.assertEqual(r['status'],'UNVERIFIED')
    def test_hard_filter_failure(self):
        r=evaluate(bundle([row(de=.71)]),TODAY)['rows'][0];self.assertEqual(r['status'],'REJECTED')
    def test_negative_profit_never_positive_cash_ratio(self):
        r=evaluate(bundle([row(cfo3=-100,pat3=-100)]),TODAY)['rows'][0];self.assertNotEqual(r['status'],'QUALIFIED');self.assertIsNone(r['cash_conv'])
    def test_relative_direction_and_ties(self):
        r=evaluate(bundle([row('Better',roce=30,de=.1),row('Other',roce=20,de=.5)]),TODAY)['rows'];self.assertEqual(r[0]['name'],'Better');self.assertGreater(r[0]['score'],r[1]['score'])
        r=evaluate(bundle([row('A'),row('B')]),TODAY)['rows'];self.assertEqual([x['score'] for x in r],[50,50]);self.assertEqual([x['rank'] for x in r],[1,1])
    def test_singleton_not_perfect(self):self.assertEqual(evaluate(bundle([row()]),TODAY)['rows'][0]['score'],50)
    def test_stale_and_financial_sector(self):
        b=bundle([row()]);b['asof']=b['period_end']=str(TODAY-timedelta(days=211));self.assertEqual(evaluate(b,TODAY)['qualified'],0)
        self.assertEqual(evaluate(bundle([row(sector='Banking')]),TODAY)['rows'][0]['status'],'UNSUPPORTED SECTOR')
    def test_duplicate_rows_and_columns_rejected(self):
        with self.assertRaises(ValueError):parse(raw([row(),row()]))
        with self.assertRaises(ValueError):parse(raw([row()]).replace(b'name,',b'Name,name,'))
    def test_persistence_and_invalid_import_preserves_old(self):
        with tempfile.TemporaryDirectory() as root:
            m=QGLPResearch(root);b=bundle([]);m.import_csv(raw([row()]),b['asof'],b['period_end'],b['source'])
            with self.assertRaises(ValueError):m.import_csv(b'bad',b['asof'],b['period_end'],b['source'])
            self.assertEqual(QGLPResearch(root).snapshot()['qualified'],1)
    def test_future_dates_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):QGLPResearch(root).import_csv(raw([row()]),str(TODAY+timedelta(days=1)),str(TODAY),'Test')
    def test_api_import_and_remote_rejection(self):
        from insights.api import create_app
        with tempfile.TemporaryDirectory() as root:
            client=create_app(SimpleNamespace(qglp_research=QGLPResearch(root))).test_client();b=bundle([])
            payload=lambda:dict(file=(io.BytesIO(raw([row()])),'test.csv'),asof=b['asof'],period_end=b['period_end'],source='Test export')
            self.assertEqual(client.post('/api/v1/market-insights/qglp/import',data=payload()).status_code,200)
            self.assertEqual(client.post('/api/v1/market-insights/qglp/import',data=payload(),environ_overrides={'REMOTE_ADDR':'1.2.3.4'}).status_code,403)
            self.assertEqual(client.get('/api/v1/market-insights/qglp').json['qualified'],1)
            self.assertEqual(client.get('/api/v1/market-insights/qglp/template').status_code,200)
