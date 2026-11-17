import tempfile,unittest,time,json
from datetime import datetime,timezone
from email.utils import formatdate
from types import SimpleNamespace
from unittest.mock import patch
from insights.event_center import EventCenter,parse_rss,parse_ics,trade_rows,safe_url,impact
NOW=1794823200

def rss(uid='one',stamp=NOW):return f'<rss><channel><item><title>Inflation policy update</title><link>https://example.org/{uid}</link><guid>{uid}</guid><pubDate>{formatdate(stamp,usegmt=True)}</pubDate></item></channel></rss>'.encode()
def service(payload=None):return SimpleNamespace(snapshot=lambda m:(payload or {}) if m=='intraday' else {},positional_scanner=SimpleNamespace(snapshot=lambda:{}),index_orderflow=SimpleNamespace(snapshot=lambda:{}))
class EventTests(unittest.TestCase):
    def test_rss_dates_links_and_tags(self):
        row=parse_rss(rss(),'Test',NOW)[0];self.assertEqual(row['at'],NOW);self.assertEqual(row['tag'],'Rates / inflation')
        self.assertEqual(safe_url('javascript:alert(1)'),'')
    def test_unsafe_xml_and_html_rejected(self):
        for raw in (b'<html></html>',b'<!DOCTYPE rss><rss/>'):
            with self.assertRaises(ValueError):parse_rss(raw,'Test',NOW)
    def test_missing_or_future_publication_no_fabricated_time(self):
        self.assertIsNone(parse_rss(rss(stamp=NOW+600),'Test',NOW)[0]['at'])
        self.assertIsNone(parse_rss(rss().replace(formatdate(NOW,usegmt=True).encode(),b'bad'),'Test',NOW)[0]['at'])
    def test_bls_timezone_and_cancelled(self):
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART;TZID=US-Eastern:20261116T083000\nSUMMARY:Consumer Price Index\nEND:VEVENT\nEND:VCALENDAR'
        r=parse_ics(raw,'BLS calendar',NOW)[0];self.assertEqual(datetime.fromtimestamp(r['at'],timezone.utc).hour,13)
        self.assertEqual(parse_ics(raw.replace(b'UID:a',b'UID:a\nSTATUS:CANCELLED'),'BLS calendar',NOW),[])
    def test_bls_summer_dst(self):
        now=datetime(2026,7,1,tzinfo=timezone.utc).timestamp()
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART;TZID=US-Eastern:20260702T083000\nSUMMARY:Employment\nEND:VEVENT\nEND:VCALENDAR'
        self.assertEqual(datetime.fromtimestamp(parse_ics(raw,'BLS calendar',now)[0]['at'],timezone.utc).hour,12)
    def test_news_baseline_new_dedupe_and_restart(self):
        with tempfile.TemporaryDirectory() as root,patch('insights.event_center.time.time',return_value=NOW):
            m=EventCenter(root,service(),fetch=lambda _:rss());m.refresh_source('RBI');self.assertEqual(m.notifications()['unread'],0)
            m.fetch=lambda _:rss('two');m.refresh_source('RBI');m.refresh_source('RBI');self.assertEqual(m.notifications()['unread'],1)
            m=EventCenter(root,service(),fetch=lambda _:rss('two'));m.refresh_source('RBI');self.assertEqual(m.notifications()['unread'],1)
    def test_failure_preserves_cache_and_last_success(self):
        with tempfile.TemporaryDirectory() as root,patch('insights.event_center.time.time',return_value=NOW):
            m=EventCenter(root,service(),fetch=lambda _:rss());m.refresh_source('RBI')
            m.fetch=lambda _:b'bad';m.refresh_source('RBI');r=m.snapshot();self.assertEqual(len(r['news']),1);s=next(x for x in r['sources'] if x['name']=='RBI');self.assertTrue(s['error']);self.assertEqual(s['updated_at'],NOW)
    def test_trade_origin_levels_and_daily_dedupe(self):
        p=dict(updated_at=datetime.fromtimestamp(NOW,timezone.utc).isoformat(),signals=[dict(symbol='ABC',strategy='Momentum',direction='BUY',entry=100,sl=98,t1=103,t2=105)])
        with tempfile.TemporaryDirectory() as root:
            m=EventCenter(root,service(p));m.collect(NOW);m.collect(NOW+5);a=m.notifications()['alerts'];self.assertEqual(len(a),1);self.assertIn('Intraday',a[0]['title']);self.assertIn('SL 98',a[0]['body'])
            m.collect(NOW+700);self.assertEqual(len(m.notifications()['alerts']),1)
    def test_waiting_and_watch_are_not_confirmed_trade(self):
        self.assertEqual(trade_rows('positional',dict(rows=[dict(status='WAITING FOR ENTRY')])),[])
        r=trade_rows('index-options',dict(opening_setups=[dict(state='DIRECTION_READY')]))[0];self.assertTrue(r['notification_watch'])
    def test_reminder_dedup_and_cancellation(self):
        with tempfile.TemporaryDirectory() as root,patch('insights.event_center.time.time',return_value=NOW):
            m=EventCenter(root,service());ev=m.add_event(dict(title='RBI policy',url='https://rbi.org.in',at=datetime.fromtimestamp(NOW+600,timezone.utc).isoformat()))
            m.collect(NOW);m.collect(NOW+1);self.assertEqual(m.notifications()['unread'],1)
            m.mark_read(m.notifications()['alerts'][0]['id']);self.assertEqual(m.notifications()['unread'],0)
            m.remove_event(ev['id']);self.assertEqual(m.snapshot()['events'],[])
    def test_api_access_and_validation(self):
        from insights.api import create_app
        with tempfile.TemporaryDirectory() as root:
            m=EventCenter(root,service());client=create_app(SimpleNamespace(event_center=m)).test_client()
            self.assertEqual(client.get('/api/v1/market-insights/event-calendar').status_code,200)
            self.assertEqual(client.get('/api/v1/market-insights/notifications').status_code,200)
            self.assertEqual(client.post('/api/v1/market-insights/notifications/read',json={'through':'bad'}).status_code,400)
            self.assertEqual(client.post('/api/v1/market-insights/notifications/read',json={'through':1},environ_overrides={'REMOTE_ADDR':'1.2.3.4'}).status_code,403)
            self.assertEqual(client.post('/api/v1/market-insights/events/add',json={}).status_code,400)


class ReadNotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.m=EventCenter(self.tmp.name,service())
        for i in range(3):self.m.publish(str(i),'Alert '+str(i),'Body','Intraday',now=NOW)
    def test_read_alerts_hidden_after_restart_and_duplicate_publish(self):
        ids=[r['id'] for r in self.m.notifications()['alerts']]
        self.m.mark_read(notification_id=ids[1])
        m=EventCenter(self.tmp.name,service());m.publish('1','Same alert','Body','Intraday',now=NOW)
        out=m.notifications()
        self.assertEqual([a['id'] for a in out['alerts']],[ids[0],ids[2]])
        self.assertEqual(out['unread'],2);self.assertEqual(out['latest_id'],ids[0])
    def test_mark_all_keeps_concurrently_created_new_alert(self):
        through=self.m.notifications()['latest_id']
        self.m.publish('new','New alert','Body','F&O Stocks',now=NOW+1)
        self.m.mark_read(through)
        out=self.m.notifications();self.assertEqual(out['unread'],1)
        self.assertEqual(out['alerts'][0]['title'],'New alert')
        self.m.mark_read(out['latest_id']);self.assertEqual(self.m.notifications()['alerts'],[])
    def test_api_individual_and_all_read_return_current_unread_only(self):
        from insights.api import create_app
        c=create_app(SimpleNamespace(event_center=self.m)).test_client()
        identifier=self.m.notifications()['alerts'][1]['id']
        r=c.post('/api/v1/market-insights/notifications/read',json={'id':identifier})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json['unread'],2)
        self.assertNotIn(identifier,[a['id'] for a in r.json['alerts']])
        r=c.post('/api/v1/market-insights/notifications/read',json={'through':r.json['latest_id']})
        self.assertEqual(r.json['alerts'],[]);self.assertEqual(c.get('/api/v1/market-insights/notifications').json['unread'],0)
        for body in ({'id':True},{'id':-1},{'id':2,'through':2},{'id':'2'},{},[]):
            self.assertEqual(c.post('/api/v1/market-insights/notifications/read',json=body).status_code,400)
    def test_unread_beyond_200_read_rows_remains_visible(self):
        first=self.m.notifications()['alerts'][-1]['id']
        for i in range(205):self.m.publish('later'+str(i),'Later','Body','Intraday',now=NOW+1)
        with self.m.db() as db:db.execute('UPDATE alerts SET seen=1 WHERE seq>?',(first,))
        self.assertEqual([r['id'] for r in self.m.notifications()['alerts']],[first])
