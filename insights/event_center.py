"""Independent public-feed calendar and persistent research notifications. No orders."""
import hashlib,json,math,re,sqlite3,threading,time,html
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from contextlib import contextmanager
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
from insights.config import IST

SOURCES={
 'PIB':('https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=1','rss'),
 'BBC World':('https://feeds.bbci.co.uk/news/world/rss.xml','rss'),
 'RBI':('https://www.rbi.org.in/pressreleases_rss.xml','rss'),
 'Federal Reserve':('https://www.federalreserve.gov/feeds/press_monetary.xml','rss'),
 'ECB':('https://www.ecb.europa.eu/rss/press.html','rss'),
 'BBC Business':('https://feeds.bbci.co.uk/news/business/rss.xml','rss'),
 'BLS calendar':('https://www.bls.gov/schedule/news_release/bls.ics','ics')}
LABELS={'premarket-followthrough':'Pre-Market 8 AM','analyse-notification':'Analyse','intraday':'Intraday','fo-stocks':'F&O Stocks','index-options':'Index Options','btst':'BTST','btst-closing':'BTST closing','swing-trades':'Swing Trades','positional':'Positional','multibagger':'Multibagger'}
def digest(*parts):return hashlib.sha256('|'.join(map(str,parts)).encode()).hexdigest()
def safe_url(url):
    try:
        p=urlparse(str(url));return str(url) if p.scheme in ('https','http') and p.hostname and not p.username else ''
    except ValueError:return ''
def clean(s):return html.unescape(re.sub('<[^>]*>','',str(s))).strip()[:500]
def impact(title):
    groups=[(r'\b(cpi|inflation|ppi|interest rate|monetary|fomc|repo|policy rate)\b','Rates / inflation','Banks, rate-sensitive shares, indices'),
            (r'\b(oil|crude|opec|energy|gas)\b','Energy','Oil & gas, airlines, paints'),
            (r'\b(tariff|war|sanction|conflict|trade deal)\b','Global risk / trade','Indices, exporters, importers'),
            (r'\b(gdp|employment|payroll|jobs|unemployment|industrial production|budget|tax|gst)\b','Growth / policy','Indices and cyclical sectors'),
            (r'\b(earnings|profit|results|merger|acquisition)\b','Company news','Named companies and peers')]
    for pattern,tag,sectors in groups:
        if re.search(pattern,title,re.I):return tag,sectors
    return 'General market context','Relevance requires review'
def parse_rss(raw,source,now):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('Unsafe XML')
    root=ET.fromstring(raw)
    if root.tag.lower()!='rss':raise ValueError('Not RSS')
    out=[]
    for item in root.findall('./channel/item')[:100]:
        title=clean(item.findtext('title',''));url=safe_url(item.findtext('link',''))
        if not title or not url:continue
        stamp=None
        try:
            dt=parsedate_to_datetime(item.findtext('pubDate',''))
            if dt.tzinfo:stamp=dt.timestamp()
        except (ValueError,TypeError,OverflowError):pass
        if stamp is not None and stamp>now+300:stamp=None
        tag,sectors=impact(title)
        out.append(dict(id=digest(source,item.findtext('guid') or url),title=title,url=url,source=source,kind='news',at=stamp,tag=tag,sectors=sectors))
    return out

def parse_ics(raw,source,now):
    text=raw.decode('utf-8-sig');text=re.sub(r'\r?\n[ \t]','',text)
    if 'BEGIN:VCALENDAR' not in text:raise ValueError('Not iCalendar')
    out=[]
    for block in text.split('BEGIN:VEVENT')[1:]:
        block=block.split('END:VEVENT')[0];fields={}
        for line in block.splitlines():
            if ':' in line:
                k,v=line.split(':',1);fields[k]=v.strip()
        # Do not fabricate expansion for recurrence or a cancelled release.
        if 'RRULE' in fields or fields.get('STATUS')=='CANCELLED':continue
        start=next(((k,v) for k,v in fields.items() if k.split(';')[0]=='DTSTART'),None)
        if not start:continue
        k,v=start
        try:
            if len(v)==8:continue # date-only does not specify a reliable reminder time
            if v.endswith('Z'):dt=datetime.strptime(v,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            else:
                zone=k.split('TZID=',1)[1].strip('"') if 'TZID=' in k else 'America/New_York'
                if zone in ('US-Eastern','US/Eastern'):zone='America/New_York'
                dt=datetime.strptime(v,'%Y%m%dT%H%M%S').replace(tzinfo=ZoneInfo(zone))
            stamp=dt.timestamp()
        except (ValueError,KeyError):continue
        if not now-86400<=stamp<=now+120*86400:continue
        title=clean(fields.get('SUMMARY','').replace('\\,',',').replace('\\n',' '))
        if not title:continue
        tag,sectors=impact(title)
        out.append(dict(id=digest(source,fields.get('UID',title)),title=title,url=safe_url(fields.get('URL','')) or SOURCES[source][0],source=source,kind='event',at=stamp,tag=tag,sectors=sectors))
    return out

def trade_rows(module,payload):
    """Only actual research output collections; do not turn discovery lists into trades."""
    if payload.get('stale'):return []
    rows=[]
    for key in ('signals','confirmed','opportunity_ready'):
        rows+=payload.get(key,[]) if isinstance(payload.get(key),list) else []
    rows += [dict(r,notification_watch=True) for r in payload.get('guide_layer',[]) if r.get('readiness')=='CONDITIONAL RESEARCH' and r.get('entry')]
    if module=='positional':rows=[r for r in payload.get('rows',[]) if str(r.get('status','')).startswith('READY')]
    if module=='multibagger':rows=[r for r in payload.get('candidates',[]) if r.get('eligible') is True]
    # Direction-only studies remain explicitly watches, never premium trades.
    for key in ('fib_setups','opening_setups'):
        rows += [dict(r,notification_watch=True) for r in payload.get(key,[]) if r.get('state') in ('STRUCTURE_READY','DIRECTION_READY')]
    return [r for r in rows if isinstance(r,dict) and not any(x in str(r.get('status','')).upper() for x in ('STALE','WAITING','BLOCKED','CLOSED','UNAVAILABLE','TOUCHED','NO TRADE','NO_TRADE'))]

class EventCenter:
    def __init__(self,root,service,fetch=None):
        self.service=service;self.path=Path(root)/'event_notifications.sqlite';self.lock=threading.RLock();self.stop_event=threading.Event();self.threads=[];self.error='';self.fetch=fetch or self.download
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.db() as db:db.executescript('''CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,source TEXT,kind TEXT,at REAL,body TEXT);
CREATE TABLE IF NOT EXISTS sources(name TEXT PRIMARY KEY,updated REAL,error TEXT);
CREATE TABLE IF NOT EXISTS alerts(seq INTEGER PRIMARY KEY AUTOINCREMENT,uid TEXT UNIQUE,created REAL,body TEXT,seen INTEGER DEFAULT 0);''')
        except (OSError,sqlite3.Error):self.error='Notification storage unavailable; existing scans continue.'
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=2)
        try:
            with db:yield db
        finally:db.close()
    @staticmethod
    def download(url):
        with urlopen(Request(url,headers={'User-Agent':'BharatSignal personal market reader'}),timeout=8) as r:raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Feed too large')
        return raw
    def publish(self,uid,title,body,tab,kind='research',now=None,url=''):
        now=time.time() if now is None else now
        msg=dict(title=title[:200],body=body[:1800],tab=tab,kind=kind,url=safe_url(url))
        with self.lock,self.db() as db:
            db.execute('INSERT OR IGNORE INTO alerts(uid,created,body) VALUES(?,?,?)',(uid,now,json.dumps(msg)))
            db.execute('DELETE FROM alerts WHERE created<?',(now-30*86400,))
    def refresh_source(self,source):
        url,kind=SOURCES[source];now=time.time()
        try:
            rows=(parse_rss if kind=='rss' else parse_ics)(self.fetch(url),source,now)
            with self.lock,self.db() as db:
                prior=db.execute('SELECT updated FROM sources WHERE name=?',(source,)).fetchone();initialized=bool(prior and prior[0])
                known={r[0] for r in db.execute('SELECT id FROM items WHERE source=?',(source,))}
                if kind=='ics':db.execute('DELETE FROM items WHERE source=?',(source,)) # successful calendar replaces cancellations/reschedules
                for row in rows:
                    db.execute('INSERT OR REPLACE INTO items VALUES(?,?,?,?,?)',(row['id'],source,row['kind'],row['at'],json.dumps(row)))
                db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?)',(source,now,''))
                db.execute("DELETE FROM items WHERE kind='news' AND at<?",(now-14*86400,))
            for row in rows:
                if row['kind']=='news' and (row['tag']!='General market context' or source in ('RBI','Federal Reserve','ECB')) and initialized and row['id'] not in known and row['at'] is not None and 0<=now-row['at']<=6*3600:
                    self.publish('news:'+row['id'],source+' — '+row['title'],row['tag']+' · Possible exposure: '+row['sectors']+'. Direction/impact unverified.','Event Calendar','news',url=row['url'])
        except Exception:
            with self.lock,self.db() as db:
                db.execute("INSERT INTO sources VALUES(?,NULL,?) ON CONFLICT(name) DO UPDATE SET error=excluded.error",(source,'Source unavailable or format changed; retrying'))
    def collect(self,now=None):
        now=time.time() if now is None else now;day=datetime.fromtimestamp(now,IST).date().isoformat()
        for module,label in LABELS.items():
            try:
                p=self.service.premarket_followthrough.snapshot() if module=='premarket-followthrough' else self.service.positional_scanner.snapshot() if module=='positional' else self.service.snapshot(module)
                stamp=datetime.fromisoformat(p.get('updated_at','')).timestamp()
                if not 0<=now-stamp<=600:continue
                for r in trade_rows(module,p):
                    symbol=str(r.get('symbol') or r.get('underlying') or '');strategy=str(r.get('strategy') or r.get('setup') or 'Research ranking');side=str(r.get('direction') or r.get('side') or '')
                    if not symbol:continue
                    kind='watch' if r.get('notification_watch') or module=='multibagger' else 'research'
                    vals={k:r.get(k,r.get('spot_'+k)) for k in ('entry','sl','t1','t2')}
                    vals['sl']=vals['sl'] or r.get('stop');vals['t1']=vals['t1'] or r.get('target');vals['t2']=vals['t2'] or r.get('target_3r')
                    levels=' · '.join(k.upper()+' '+str(v) for k,v in vals.items() if isinstance(v,(int,float)) and math.isfinite(v))
                    reason=r.get('reason') or '; '.join(map(str,r.get('reasons') or []))
                    body=f'{strategy} · {side} · {levels} · {reason} · {r.get("status",r.get("state","Research only"))}. Check source tab freshness; no order placed.'
                    if module in ('index-options','fo-stocks'):body+=' Watch levels are underlying prices; legacy premium quote age may be unverified.'
                    uid=digest('setup',day,module,symbol,strategy,side,r.get('expiry'),r.get('strike'))
                    self.publish(uid,f'{label} — {symbol} — {kind} setup',body,'BTST' if module=='btst-closing' else label,kind,now)
            except Exception:continue # One source cannot prevent the other alerts or the scans.
        try:
            for r in self.service.index_orderflow.snapshot().get('instruments',[]):
                s=r.get('signal')
                if not s:continue
                c=r['contract'];symbol=c['symbol']
                self.publish(digest('orderflow',symbol,s['confirmed_at']),f'Index Options — {symbol} — order-flow research',
                             f'{s["direction"]} · Entry {s["entry"]} · SL {s["sl"]} · T1 {s["t1"]} · T2 {s["t2"]} · {s["reason"]}. FUTURES reference levels, NOT option premiums.','Index Options','research',now)
        except Exception:pass
        with self.lock,self.db() as db:
            rows=db.execute("SELECT i.body FROM items i JOIN sources s ON i.source=s.name WHERE i.kind='event' AND i.at BETWEEN ? AND ? AND (s.updated>? OR i.source='User schedule') AND s.error=''",(now,now+900,now-86400)).fetchall()
        for (raw,) in rows:
            r=json.loads(raw);self.publish(digest('reminder',r['id'],r['at']), 'Event in 15 minutes or less — '+r['title'],datetime.fromtimestamp(r['at'],IST).strftime('%d %b %H:%M IST')+' · '+r['source']+' · Schedule may change.','Event Calendar','event',now,r['url'])
    def add_event(self,data):
        title=clean(data.get('title',''));url=safe_url(data.get('url',''))
        if not title or not url:raise ValueError('Title and an official source URL are required')
        try:
            dt=datetime.fromisoformat(data.get('at',''))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=IST)
            stamp=dt.timestamp()
        except (ValueError,TypeError):raise ValueError('Enter a valid event date/time in IST') from None
        now=time.time()
        if not now<stamp<=now+366*86400:raise ValueError('Event must be in the next 366 days')
        tag,sectors=impact(title);uid=digest('manual',title,stamp,url)
        row=dict(id=uid,title=title,url=url,source='User schedule',kind='event',at=stamp,tag=tag,sectors=sectors)
        with self.lock,self.db() as db:
            db.execute('INSERT OR REPLACE INTO items VALUES(?,?,?,?,?)',(uid,'User schedule','event',stamp,json.dumps(row)))
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?)',('User schedule',now,''))
        return row
    def remove_event(self,uid):
        with self.lock,self.db() as db:db.execute("DELETE FROM items WHERE id=? AND source='User schedule'",(uid,))
    def snapshot(self):
        now=time.time()
        try:
            with self.lock,self.db() as db:
                items=[json.loads(x[0]) for x in db.execute('SELECT body FROM items ORDER BY at DESC LIMIT 1200')]
                sources={x[0]:dict(updated_at=x[1],error=x[2]) for x in db.execute('SELECT * FROM sources')}
            return dict(news=[x for x in items if x['kind']=='news'][:100],events=sorted([x for x in items if x['kind']=='event' and now-86400<=x['at']],key=lambda x:x['at']),
                        sources=[dict(name=s,url=u[0],**sources.get(s,dict(updated_at=None,error='Not fetched yet'))) for s,u in SOURCES.items()],error=self.error)
        except sqlite3.Error:return dict(news=[],events=[],sources=[],error='Event storage unavailable')
    def notifications(self):
        try:
            with self.lock,self.db() as db:
                rows=db.execute('SELECT seq,created,body,seen FROM alerts ORDER BY seq DESC LIMIT 200').fetchall()
                unread=db.execute('SELECT count(*) FROM alerts WHERE seen=0').fetchone()[0]
            return dict(alerts=[dict(id=s,created=t,seen=bool(v),**json.loads(b)) for s,t,b,v in rows],unread=unread,error=self.error)
        except sqlite3.Error:return dict(alerts=[],unread=0,error='Notification storage unavailable')
    def mark_read(self,through):
        with self.lock,self.db() as db:db.execute('UPDATE alerts SET seen=1 WHERE seq<=?',(through,))
    def start(self):
        if self.threads or self.error:return
        self.stop_event.clear()
        def news_loop(source):
            while not self.stop_event.is_set():
                try:self.refresh_source(source)
                except Exception:self.error='Event refresh failed; scans are unaffected.'
                self.stop_event.wait(300)
        def alert_loop():
            while not self.stop_event.is_set():
                try:self.collect()
                except Exception:self.error='Notification update failed; scans are unaffected.'
                self.stop_event.wait(5)
        for source in SOURCES:
            t=threading.Thread(target=news_loop,args=(source,),daemon=True,name='Events-'+source);self.threads.append(t);t.start()
        t=threading.Thread(target=alert_loop,daemon=True,name='ResearchNotifications');self.threads.append(t);t.start()
    def stop(self):self.stop_event.set()
