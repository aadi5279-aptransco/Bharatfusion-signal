"""Independent, read-only European index context; never consumed by strategies."""
import copy,json,math,threading,time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request,urlopen
from urllib.parse import quote
from insights.config import IST

MARKETS=[('DAX','Germany','^GDAXI','Europe/Berlin',9),('CAC 40','France','^FCHI','Europe/Paris',9),
         ('EURO STOXX 50','Eurozone','^STOXX50E','Europe/Berlin',9),('FTSE 100','United Kingdom','^FTSE','Europe/London',8)]

def number(value):
    if isinstance(value,bool):return None
    try:
        value=float(value)
        return value if math.isfinite(value) else None
    except (ValueError,TypeError):return None

def session(market,now):
    local=datetime.fromtimestamp(now,ZoneInfo(market[3]));start=local.replace(hour=market[4],minute=0,second=0,microsecond=0)
    end=start.replace(hour=16 if market[4]==8 else 17,minute=30)
    active=local.weekday()<5 and start<=local<end
    return dict(scheduled_session='REGULAR HOURS — CALENDAR UNVERIFIED' if active else 'OUTSIDE REGULAR HOURS',
                normal_open_ist=start.astimezone(IST).strftime('%H:%M'),normal_close_ist=end.astimezone(IST).strftime('%H:%M'))

def normalize(payload,market,now):
    chart=payload['chart']
    if chart.get('error'):raise ValueError('Provider error')
    meta=chart['result'][0]['meta']
    if meta.get('symbol')!=market[2]:raise ValueError('Unexpected symbol')
    price=number(meta.get('regularMarketPrice'));previous=number(meta.get('chartPreviousClose'));stamp=number(meta.get('regularMarketTime'))
    if price is None or price<=0 or stamp is None or stamp<=0 or stamp>now+60:raise ValueError('Invalid quote')
    if previous is None or previous<=0:previous=None
    period=meta.get('currentTradingPeriod',{}).get('regular',{})
    start=number(period.get('start'));end=number(period.get('end'))
    active=bool(start is not None and end is not None and start<=now<end)
    age=max(0,now-stamp)
    return dict(price=price,change=round(price-previous,4) if previous else None,
                change_pct=round((price/previous-1)*100,3) if previous else None,
                previous_close=previous,quote_at=stamp,fetched_at=now,
                provider_session='WITHIN PROVIDER SESSION WINDOW' if active else 'NO CURRENT PROVIDER SESSION',
                quality='DELAYED QUOTE' if age<=1200 else 'STALE / LAST AVAILABLE QUOTE',
                session_start=start,session_end=end,source='Yahoo Finance — delayed; no real-time guarantee')

class EuropeMarkets:
    def __init__(self,fetch=None):
        self.fetch=fetch or self._fetch;self.lock=threading.Lock();self.rows={};self.errors={}
        self.stop_event=threading.Event();self.thread=None
    @staticmethod
    def _fetch(symbol):
        url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?interval=1m&range=1d'
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=8) as r:
            raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Oversized response')
        return json.loads(raw)
    def refresh(self):
        for market in MARKETS:
            if self.stop_event.is_set():break
            try:
                result=normalize(self.fetch(market[2]),market,time.time())
                with self.lock:self.rows[market[2]]=result;self.errors.pop(market[2],None)
            except Exception:
                with self.lock:self.errors[market[2]]='Source unavailable — retrying automatically'
    def snapshot(self,now=None):
        now=time.time() if now is None else now
        with self.lock:rows=copy.deepcopy(self.rows);errors=dict(self.errors)
        out=[]
        for market in MARKETS:
            row=rows.get(market[2],{})
            row.update(name=market[0],region=market[1],symbol=market[2],**session(market,now))
            row['error']=errors.get(market[2]);row['age_seconds']=max(0,int(now-row['quote_at'])) if row.get('quote_at') else None
            if not row.get('quote_at'):row['quality']='WAITING FOR DATA'
            elif row['error'] or now-row['quote_at']>1200 or now-row['fetched_at']>180:row['quality']='STALE / LAST AVAILABLE QUOTE'
            start=row.get('session_start');end=row.get('session_end')
            row['provider_session']='WITHIN PROVIDER SESSION WINDOW' if start is not None and end is not None and start<=now<end else 'NO CURRENT PROVIDER SESSION'
            out.append(row)
        return dict(markets=out,refresh_seconds=60,note='European context only, not a prediction of NIFTY. Delayed data; holidays and exceptional closures are not independently verified.')
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear()
        def loop():
            while not self.stop_event.is_set():
                self.refresh();self.stop_event.wait(60)
        self.thread=threading.Thread(target=loop,daemon=True,name='EuropeMarketContext');self.thread.start()
    def stop(self):self.stop_event.set()
