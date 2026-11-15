"""Index-futures FULL-feed research. No orders; inferred, sampled trade flow."""
import json,math,struct,threading,time,uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from insights.config import IST,is_market_session

SEGMENTS={2:'NSE_FNO',8:'BSE_FNO'}
def decode(message):
    """Dhan v2 little-endian FULL packet, including concatenated frames."""
    if not isinstance(message,bytes):raise ValueError('Expected binary feed')
    out=[];offset=0
    while offset<len(message):
        if len(message)-offset<8:raise ValueError('Truncated header')
        code,length,segment,security=struct.unpack_from('<BHBI',message,offset)
        if length<8 or offset+length>len(message):raise ValueError('Invalid packet length')
        if code==50:raise ConnectionError('Provider disconnected the market feed')
        if code==8:
            if length!=162:raise ValueError('Unexpected FULL packet size')
            v=struct.unpack_from('<fHIfIIIIIIffff',message,offset+8)
            bidq,askq,_,_,bid,ask=struct.unpack_from('<IIHHff',message,offset+62)
            out.append(dict(segment=SEGMENTS.get(segment,str(segment)),id=str(security),price=v[0],ltq=v[1],
                ts=v[2],volume=v[4],oi=v[7],bid=bid,ask=ask,bid_qty=bidq,ask_qty=askq))
        offset+=length
    return out

def stacked(levels):
    run=0;previous=None
    for p in sorted(levels):
        run=run+1 if previous is not None and p==previous+1 else 1
        if run>=3:return True
        previous=p
    return False

def analyse(bar,history,tick,big_qty):
    levels=bar['levels'];buy=[];sell=[]
    for p,(s,b) in levels.items():
        below=levels.get(p-1);above=levels.get(p+1)
        if below and below[0]>0 and b>=3*below[0]:buy.append(p)
        if above and above[1]>0 and s>=3*above[1]:sell.append(p)
    delta=sum(b-s for s,b in levels.values());classified=sum(s+b for s,b in levels.values())
    total=classified+bar['unknown'];quality=classified/total if total else 0
    rng=bar['high']-bar['low'];ab=None
    if len(history)>=20:
        avgvol=sum(x['volume'] for x in list(history)[-20:])/20
        avgrange=sum(x['range'] for x in list(history)[-20:])/20
        if rng>0 and total>=1.5*avgvol and rng<=.7*avgrange:
            if delta<0 and bar['close']>=bar['low']+.6*rng:ab='BULLISH ABSORPTION'
            elif delta>0 and bar['close']<=bar['low']+.4*rng:ab='BEARISH ABSORPTION'
    def defended(side):
        h=bar[side+'_watch']
        return len(h)==30 and len({p for p,q in h})==1 and min(q for p,q in h)>=big_qty
    signal=None;reason=None
    if len(history)>=20 and quality>=.8 and not bar['partial']:
        if stacked(buy) and delta>0:signal='LONG';reason='3+ consecutive diagonal buy imbalances with positive inferred delta'
        elif stacked(sell) and delta<0:signal='SHORT';reason='3+ consecutive diagonal sell imbalances with negative inferred delta'
        elif ab=='BULLISH ABSORPTION' and defended('bid'):signal='LONG';reason='Narrow high-volume bar with sell delta; same bid level sustained (proxy)'
        elif ab=='BEARISH ABSORPTION' and defended('ask'):signal='SHORT';reason='Narrow high-volume bar with buy delta; same ask level sustained (proxy)'
    return dict(start=bar['start'],open=bar['open'],high=bar['high'],low=bar['low'],close=bar['close'],range=rng,
        delta=delta,volume=total,classified=classified,unknown=bar['unknown'],classification_pct=round(quality*100,1),
        buy_imbalances=[round(p*tick,6) for p in sorted(buy)],sell_imbalances=[round(p*tick,6) for p in sorted(sell)],
        absorption=ab,signal=signal,reason=reason,
        footprint=[dict(price=round(p*tick,6),sell=s,buy=b) for p,(s,b) in sorted(levels.items(),reverse=True)][:150])

class FlowEngine:
    def __init__(self,tick,big_qty=1000):
        if not math.isfinite(tick) or tick<=0:raise ValueError('Verified positive instrument tick size required')
        self.tick=tick;self.big_qty=big_qty;self.resets=0;self.reset()
    def reset(self):
        self.last=None;self.bar=None;self.history=deque(maxlen=120);self.cvd=0;self.signal=None;self.resets+=1;self.last_received=None
    def close(self):
        if self.bar is None:return
        b=analyse(self.bar,self.history,self.tick,self.big_qty);previous=self.history[-1] if self.history else None
        self.cvd+=b['delta'];b['cvd']=self.cvd;b['divergence']=None
        if previous:
            if b['high']>previous['high'] and b['cvd']<previous['cvd']:b['divergence']='BEARISH PRICE/CVD DIVERGENCE'
            elif b['low']<previous['low'] and b['cvd']>previous['cvd']:b['divergence']='BULLISH PRICE/CVD DIVERGENCE'
        self.signal=None
        if previous and previous['signal'] and b['start']==previous['start']+60 and b['classification_pct']>=80 and not self.bar['partial']:
            side=previous['signal'];sign=1 if side=='LONG' else -1
            if sign*(b['close']-previous['close'])>0 and sign*b['delta']>0:
                entry=b['close'];stop=previous['low']-self.tick if sign==1 else previous['high']+self.tick;risk=sign*(entry-stop)
                if 0<risk/entry<=.02:
                    self.signal=dict(direction=side,option_bias='CE research' if sign==1 else 'PE research',
                        entry=round(round(entry/self.tick)*self.tick,6),sl=round(round(stop/self.tick)*self.tick,6),
                        t1=round(round((entry+sign*1.5*risk)/self.tick)*self.tick,6),t2=round(round((entry+sign*2.5*risk)/self.tick)*self.tick,6),
                        reason=previous['reason']+'; next closed minute confirms',confirmed_at=b['start']+60,
                        level_basis='INDEX FUTURES PRICES — NOT OPTION PREMIUMS')
        if not self.bar['partial']:self.history.append(b)
        self.bar=None
    def feed(self,p,received):
        if not all(math.isfinite(float(p[k])) for k in ('price','ltq','volume','ts','bid','ask','bid_qty','ask_qty')):return False
        if p['price']<=0 or p['volume']<0 or p['ltq']<0 or not 0<=received-p['ts']<=10:return False
        grid=round(p['price']/self.tick)
        if abs(p['price']-grid*self.tick)>max(.002,self.tick*.01):raise ValueError('Price is off instrument tick grid')
        if self.last and p['ts']<self.last['ts']:return False
        if self.last and (datetime.fromtimestamp(p['ts'],IST).date()!=datetime.fromtimestamp(self.last['ts'],IST).date() or p['volume']<self.last['volume'] or received-self.last_received>30):self.reset()
        self.last_received=received
        if self.signal:
            plan=self.signal
            touched=(p['price']<=plan['sl'] or p['price']>=plan['t1']) if plan['direction']=='LONG' else (p['price']>=plan['sl'] or p['price']<=plan['t1'])
            if touched:self.signal=None
        prior=self.last;self.last=dict(p)
        if prior is None:return True # Establish day-volume baseline; never assign historical volume to one tick.
        inc=p['volume']-prior['volume']
        if inc<=0:
            if self.bar:
                for which in ('bid','ask'):
                    if p[which]>0:self.bar[which+'_watch'].append((round(p[which]/self.tick),p[which+'_qty']))
            return True # Quote-only/duplicate FULL packet, no repeated LTQ.
        start=int(p['ts']//60)*60
        if self.bar and self.bar['start']!=start:self.close()
        if self.bar is None:
            self.bar=dict(start=start,open=p['price'],high=p['price'],low=p['price'],close=p['price'],levels={},unknown=0,
                partial=not self.history and int(prior['ts']//60)*60==start,bid_watch=deque(maxlen=30),ask_watch=deque(maxlen=30))
        b=self.bar;b['high']=max(b['high'],p['price']);b['low']=min(b['low'],p['price']);b['close']=p['price']
        qty=min(inc,p['ltq']);side=None
        # Prior book reduces the risk of comparing a trade with a book changed by that same trade.
        if p['ts']-prior['ts']<=2 and 0<prior['bid']<prior['ask']:
            if p['price']>=prior['ask']:side=1
            elif p['price']<=prior['bid']:side=0
        if side is None:
            if p['price']>prior['price']:side=1
            elif p['price']<prior['price']:side=0
        b['unknown']+=inc-(qty if side is not None else 0)
        if side is not None:b['levels'].setdefault(grid,[0,0])[side]+=qty
        for which in ('bid','ask'):
            if p[which]>0:b[which+'_watch'].append((round(p[which]/self.tick),p[which+'_qty']))
        return True
    def flush(self,now):
        if self.bar and now>=self.bar['start']+60:
            if self.last and self.bar['start']+60-self.last['ts']<=10:self.close()
            else:self.bar=None;self.signal=None
    def snapshot(self,now):
        self.flush(now);fresh=self.last_received is not None and self.last is not None and 0<=now-self.last_received<=10 and 0<=now-self.last['ts']<=10
        if self.signal and self.last:
            plan=self.signal;price=self.last['price']
            if (price<=plan['sl'] or price>=plan['t1']) if plan['direction']=='LONG' else (price>=plan['sl'] or price<=plan['t1']):self.signal=None
        return dict(status='LIVE — INFERRED FLOW' if fresh else 'STALE / WAITING FOR FEED',
            warmup_bars=len(self.history),required_warmup=20,cvd=self.cvd,cvd_scope='OBSERVED CONNECTION SEGMENT; RESETS ON SESSION/FEED GAP',
            last_trade_at=self.last['ts'] if self.last else None,latest=self.history[-1] if self.history else None,
            signal=self.signal if fresh and self.signal and now-self.signal['confirmed_at']<=90 else None,
            reset_count=self.resets,tick_size=self.tick)

class IndexOrderFlow:
    def __init__(self,broker,root,holidays,job_lock):
        self.broker=broker;self.root=Path(root)/'index_orderflow';self.holidays=holidays;self.job_lock=job_lock
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None;self.ws=None
        self.engines={};self.contracts={};self.mapping_issues=[];self.status='WAITING FOR MARKET SESSION';self.stream_epoch=0;self.error='';self.recorded=0;self.recording_error=False
    def snapshot(self):
        now=time.time()
        with self.lock:
            rows=[dict(contract=self.contracts[k],**e.snapshot(now)) for k,e in self.engines.items()]
            if not is_market_session(datetime.fromtimestamp(now,IST),self.holidays()):
                for row in rows:row['signal']=None;row['status']='MARKET CLOSED / CALENDAR REQUIRED'
            return dict(status=self.status,error=self.error,recorded_packets=self.recorded,recording_error=self.recording_error,
            instruments=rows,mapping_issues=list(self.mapping_issues),
            scope='INDEX OPTIONS ONLY · FULL feed five-level book · inferred sampled delta, not exchange aggressor flags',
            limitations='No 20/200-level heatmap; defended size is a proxy, not proof of refill. Futures direction does not determine an executable option premium.')
    def map_contracts(self,now):
        if not self.job_lock.acquire(timeout=5):raise RuntimeError('Broker mapping busy')
        try:
            self.broker._sdk() # Existing token renewal; no credentials returned to HTTP clients.
            indices=[x for x in self.broker.instruments() if x.get('kind')=='index' and ''.join(c for c in x['symbol'].upper() if c.isalnum()) in ('NIFTY','NIFTY50','BANKNIFTY','NIFTYBANK','SENSEX')]
            mapped={}
            self.mapping_issues=[]
            for item in indices:
                contract=self.broker.index_future(item,now)
                if contract and contract.get('tick_size') and contract['segment'] in SEGMENTS.values():
                    k=contract['segment']+':'+str(contract['id']);mapped[k]=dict(contract,underlying=item['symbol'])
                else:self.mapping_issues.append(item['symbol']+': no current index future with a valid tick size')
            if not mapped:raise RuntimeError('No mapped index futures with verified tick sizes')
            return mapped
        finally:self.job_lock.release()
    def record(self,k,p,received):
        try:
            self.root.mkdir(parents=True,exist_ok=True)
            path=self.root/(datetime.fromtimestamp(received,IST).date().isoformat()+'.jsonl')
            # One bounded file per session; never write credentials or websocket URLs.
            if path.exists() and path.stat().st_size>250_000_000:self.recording_error=True;return
            with path.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(instrument=k,received=received,packet=p,tick_size=self.engines[k].tick,stream_epoch=self.stream_epoch))+'\n')
            self.recorded+=1
        except OSError:self.recording_error=True
    def ingest(self,message,received=None):
        received=time.time() if received is None else received
        for p in decode(message):
            k=p['segment']+':'+p['id']
            with self.lock:
                if k not in self.engines:continue
                if self.engines[k].feed(p,received):self.record(k,p,received)
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear()
        def loop():
            while not self.stop_event.is_set():
                now=datetime.now(IST)
                if not is_market_session(now,self.holidays()):
                    with self.lock:self.status='MARKET CLOSED / HOLIDAY CALENDAR REQUIRED'
                    self.stop_event.wait(10);continue
                try:
                    import websocket
                    if not self.broker.configured():raise RuntimeError('Dhan credentials required')
                    contracts=self.map_contracts(now)
                    with self.lock:
                        self.stream_epoch=uuid.uuid4().hex;self.contracts=contracts;self.engines={k:FlowEngine(float(c['tick_size'])) for k,c in contracts.items()};self.status='CONNECTING';self.error=''
                    url='wss://api-feed.dhan.co?'+urlencode(dict(version=2,token=self.broker._token,clientId=self.broker.client_id,authType=2))
                    self.ws=websocket.create_connection(url,timeout=10,enable_multithread=True)
                    self.ws.send(json.dumps(dict(RequestCode=21,InstrumentCount=len(contracts),InstrumentList=[dict(ExchangeSegment=c['segment'],SecurityId=str(c['id'])) for c in contracts.values()])))
                    self.ws.settimeout(1)
                    with self.lock:self.status='CONNECTED — WARMING UP'
                    while not self.stop_event.is_set() and is_market_session(datetime.now(IST),self.holidays()):
                        try:message=self.ws.recv()
                        except websocket.WebSocketTimeoutException:continue
                        if not message:raise ConnectionError('Feed closed')
                        self.ingest(message)
                        with self.lock:self.status='CONNECTED'
                except ImportError:
                    with self.lock:self.status='DEPENDENCY MISSING';self.error='Install websocket-client using UPDATE_INDEX_ORDERFLOW.bat'
                except Exception as exc:
                    # Library exceptions can contain authenticated URLs: never expose them.
                    with self.lock:self.status='DISCONNECTED / RETRYING';self.error=('FEED_FORMAT_OR_TICK_GRID: verify current packet layout and instrument tick size.' if isinstance(exc,ValueError) else 'CONNECTION_OR_MAPPING: check Dhan token, data entitlement, websocket limits, mapped futures and network.')
                finally:
                    if self.ws:
                        try:self.ws.close()
                        except Exception:pass
                        self.ws=None
                    with self.lock:
                        for e in self.engines.values():e.signal=None;e.last_received=None
                self.stop_event.wait(10)
        self.thread=threading.Thread(target=loop,daemon=True,name='IndexOrderFlow');self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.ws:
            try:self.ws.close()
            except Exception:pass
