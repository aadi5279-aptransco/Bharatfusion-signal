"""Auditable positional research and a non-overlapping five-minute worker."""
from __future__ import annotations
import math, threading, time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from insights.config import IST, is_market_session, WATCHLIST, MAX_SYMBOLS
from insights.indicators import clean_bars
from insights.stock_scanner import session_date, StockScanner

SOURCES=[
 {'name':'Uploaded Trading Strategies PDF','url':None,'strategies':'Morning Star; Supertrend + RSI; intraday R1/S1'},
 {'name':'StockCharts Price Channels','url':'https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/price-channels','strategies':'Donchian breakout (adapted)'},
 {'name':'StockCharts Moving Momentum','url':'https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/moving-momentum','strategies':'Moving Momentum (adapted)'}]

def validate(frame):
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError('Timezone-aware OHLCV required')
    f=clean_bars(frame);f.index=f.index.tz_convert(IST)
    if not f.map(math.isfinite).all().all():raise ValueError('Nonfinite candles')
    return f

def wilder(s,n):
    out=pd.Series(float('nan'),index=s.index)
    if len(s)<n:return out
    out.iloc[n-1]=float(s.iloc[:n].mean())
    for i in range(n,len(s)):out.iloc[i]=(out.iloc[i-1]*(n-1)+s.iloc[i])/n
    return out

def features(f):
    f=f.copy();c=f.close
    tr=pd.concat([f.high-f.low,(f.high-c.shift()).abs(),(f.low-c.shift()).abs()],axis=1).max(axis=1)
    f['atr']=wilder(tr,14);atr10=wilder(tr,10)
    diff=c.diff().iloc[1:];g=wilder(diff.clip(lower=0),14);loss=wilder(-diff.clip(upper=0),14)
    rsi=100-100/(1+g/loss);rsi=rsi.mask((loss==0)&(g>0),100).mask((loss==0)&(g==0),50)
    f['rsi']=rsi
    upper=(f.high+f.low)/2+3*atr10;lower=(f.high+f.low)/2-3*atr10
    st=pd.Series(float('nan'),index=f.index);bull=pd.Series(False,index=f.index)
    for i in range(9,len(f)):
        if i==9:st.iloc[i]=upper.iloc[i];continue
        if not (upper.iloc[i]<upper.iloc[i-1] or c.iloc[i-1]>upper.iloc[i-1]):upper.iloc[i]=upper.iloc[i-1]
        if not (lower.iloc[i]>lower.iloc[i-1] or c.iloc[i-1]<lower.iloc[i-1]):lower.iloc[i]=lower.iloc[i-1]
        bull.iloc[i]=bool(c.iloc[i]>upper.iloc[i] if not bull.iloc[i-1] else c.iloc[i]>=lower.iloc[i])
        st.iloc[i]=lower.iloc[i] if bull.iloc[i] else upper.iloc[i]
    f['supertrend']=st;f['bull']=bull
    for n in (20,50,150,200):f['sma'+str(n)]=c.rolling(n).mean()
    f['avgvol']=f.volume.shift(1).rolling(20).mean()
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    f['hist']=macd-macd.ewm(span=9,adjust=False).mean()
    lo=f.low.rolling(14).min();hi=f.high.rolling(14).max()
    f['stoch']=(100*(c-lo)/(hi-lo).replace(0,float('nan'))).rolling(3).mean()
    return f

def setup(item,strategy,bar,entry,sl,reason,exit_rule,side='BUY',timeframe='Daily',t1=None,t2=None):
    entry=round(float(entry),2);sl=round(float(sl),2);sign=1 if side=='BUY' else -1;risk=sign*(entry-sl)
    if not (math.isfinite(risk) and entry>0 and sl>0 and .002<=risk/entry<=.06):return None
    t1=round(float(t1 if t1 is not None else entry+sign*1.5*risk),2)
    t2=round(float(t2 if t2 is not None else entry+sign*2.5*risk),2)
    if not sign*(t2-t1)>0 or not sign*(t1-entry)>0:return None
    return dict(key=f"{item['segment']}:{item['id']}:{strategy}:{bar.isoformat()}",symbol=item.get('ticker') or item['symbol'],
        company=item['symbol'],exchange=item['segment'].split('_')[0],security_id=str(item['id']),strategy=strategy,
        timeframe=timeframe,side=side,entry=entry,sl=sl,t1=t1,t2=t2,risk_pct=round(risk/entry*100,2),
        signal_at=bar.isoformat(),reason=reason,exit_rule=exit_rule,
        target_basis='App extension: T1 1.5R / T2 2.5R' if timeframe=='Daily' else 'PDF: T1 2%; T2 R2/S2, runner rules apply',
        entry_basis='Signal close reference; entry review within 1% on next session' if timeframe=='Daily' else 'Stop trigger beyond breakout candle; review within 1%',
        status='WAITING FOR PRICE',last_price=None,price_at=None)

def daily_setups(frame,item,now,holidays):
    f=validate(frame);f.index=f.index.normalize()
    f=f[(f.index.date<now.date())|((f.index.date==now.date())&((now.hour,now.minute)>=(15,40)))]
    if f.index.has_duplicates or len(f)<30:raise ValueError('Need 30 unique completed daily candles')
    expected=session_date(now,holidays)
    if expected is None:raise ValueError('Verified holiday calendar required')
    if f.index[-1].date()!=expected:raise ValueError('Stale daily candles')
    f=features(f);x=f.iloc[-1];prev=f.iloc[-2];out=[];stamp=f.index[-1];price=float(x.close)
    # Explicit common eligibility gate: liquidity, not a profitability claim.
    if price<20 or x.avgvol<100000 or x.avgvol*price<10000000:return [],f
    a,b,c=f.iloc[-3],f.iloc[-2],x
    body=(f.close-f.open).abs();avgbody=body.iloc[-23:-3].mean()
    down=f.close.iloc[-4]<f.close.iloc[-8] and a.close<f.sma20.iloc[-3]
    morning=(a.close<a.open and a.open-a.close>=avgbody and abs(b.close-b.open)<=(a.open-a.close)*.3
        and max(b.open,b.close)<=a.close+(a.open-a.close)*.25 and c.close>c.open
        and c.close>=(a.open+a.close)/2 and c.close-c.open>=.5*(a.open-a.close) and down)
    if morning:
        out.append(setup(item,'PDF Morning Star',stamp,price,b.low*.999,
            'Downtrend; large red body, small star body ≤30%, strong green close above first-body midpoint.',
            'Exit after 5 trading sessions from entry, or below star-low SL; targets are added planning levels.'))
    if x.rsi>60 and x.bull and x.close>x.supertrend and x.volume>prev.volume:
        out.append(setup(item,'PDF Supertrend + RSI',stamp,price,price*.97,
            f'RSI14 {x.rsi:.1f} >60; Supertrend(10,3) green; volume {x.volume:.0f} > prior {prev.volume:.0f}.',
            'Exit after 5 trading sessions from entry, 3% SL, or daily Supertrend turns red.'))
    if len(f)>=201 and price>f.high.iloc[-21:-1].max() and price>x.sma50>x.sma200 and x.volume>=1.5*x.avgvol:
        out.append(setup(item,'Donchian 20D breakout',stamp,price,price-2*x.atr,
            'Close above PRIOR 20-session high; SMA50 > SMA200; volume ≥1.5× preceding 20-session mean.',
            'Initial 2×ATR14 stop; review exit below prior 10-day low. T1/T2 are app extensions.'))
    if len(f)>=151 and x.sma20>x.sma150 and (f.stoch.iloc[-11:-1]<20).any() and prev['hist']<=0<x['hist']:
        out.append(setup(item,'Moving Momentum',stamp,price,min(f.low.iloc[-10:])*.999,
            'SMA20 > SMA150; slow Stochastic(14,3) <20 in prior 10 sessions; MACD(12,26,9) histogram crosses positive.',
            'Exit at swing-low SL or bearish MACD histogram; targets and 10-session pullback window are app extensions.'))
    return [r for r in out if r],f

def completed_five(frame,now):
    f=validate(frame)
    mins=f.index.hour*60+f.index.minute
    f=f[(mins>=555)&(mins<=925)&((mins-555)%5==0)&(f.index+pd.Timedelta(minutes=5)<=pd.Timestamp(now))]
    if f.empty:raise ValueError('No completed 5-minute candles')
    return f

def assess(row,five,now,holidays):
    r=dict(row)
    if five is None or five.empty:return r
    last=five.iloc[-1];stamp=five.index[-1]+pd.Timedelta(minutes=5)
    r.update(last_price=round(float(last.close),2),price_at=stamp.isoformat())
    if not is_market_session(now,holidays):r['status']='CLOSED — REVIEW NEXT SESSION';return r
    if stamp.date()!=now.date() or (pd.Timestamp(now)-stamp).total_seconds()>600:r['status']='STALE PRICE';return r
    signal=pd.Timestamp(r['signal_at'])
    since=five[five.index>=signal+pd.Timedelta(days=1)] if r['timeframe']=='Daily' else five[five.index>=signal+pd.Timedelta(minutes=15)]
    if since.empty:r['status']='WAITING FOR NEXT SESSION' if r['timeframe']=='Daily' else 'WAITING FOR NEXT BAR';return r
    today=five[five.index.date==now.date()]
    expected_index=pd.date_range(pd.Timestamp(now).normalize()+pd.Timedelta(hours=9,minutes=15),today.index[-1],freq='5min')
    if not today.index.equals(expected_index):r['status']='INCOMPLETE PRICE HISTORY';return r
    sign=1 if r['side']=='BUY' else -1
    if (r['side']=='BUY' and since.low.min()<=r['sl']) or (r['side']=='SELL' and since.high.max()>=r['sl']):
        r['status']='INVALIDATED — SL TOUCHED';return r
    if (r['side']=='BUY' and since.high.max()>=r['t2']) or (r['side']=='SELL' and since.low.min()<=r['t2']):
        r['status']='T2 ALREADY TOUCHED';return r
    if (r['side']=='BUY' and since.high.max()>=r['t1']) or (r['side']=='SELL' and since.low.min()<=r['t1']):
        r['status']='T1 ALREADY TOUCHED';return r
    distance=sign*(float(last.close)/r['entry']-1)
    r['status']='READY — REVIEW ENTRY' if 0<=distance<=.01 else 'EXTENDED — DO NOT CHASE' if distance>.01 else 'WAITING FOR ENTRY'
    if r['timeframe']!='Daily' and (now.hour,now.minute)>(14,30):r['status']='ENTRY WINDOW CLOSED'
    return r

def carry_daily(signals,previous,daily,item):
    """Retain PDF watches for five sessions; no claim of real entry/fill."""
    current={r['key']:dict(r) for r in signals}
    for old in previous:
        if old['timeframe']!='Daily' or not old['strategy'].startswith('PDF '):continue
        if old['security_id']!=str(item['id']) or old['exchange']!=item['segment'].split('_')[0]:continue
        signal=pd.Timestamp(old['signal_at']);after=daily[daily.index.date>signal.date()]
        if len(after)>5:continue
        if old['key'] not in current:current[old['key']]=dict(old)
    for r in current.values():
        after=daily[daily.index.date>pd.Timestamp(r['signal_at']).date()]
        r['age_sessions']=len(after)
        r.pop('tracking_status',None)
        if len(after)>=5:r['tracking_status']='FIVE-SESSION WATCH EXPIRED'
        elif not after.empty:
            if after.low.min()<=r['sl']:r['tracking_status']='INVALIDATED — DAILY SL TOUCHED'
            elif after.high.max()>=r['t2']:r['tracking_status']='T2 ALREADY TOUCHED'
            elif after.high.max()>=r['t1']:r['tracking_status']='T1 ALREADY TOUCHED'
            elif r['strategy']=='PDF Supertrend + RSI' and not daily.bull.iloc[-1]:r['tracking_status']='EXIT REVIEW — SUPERTREND RED'
            else:r['tracking_status']='TRACK ONLY — OLDER SIGNAL'
    return list(current.values())


def r1_setups(daily,five,item,now,holidays):
    if five is None or not is_market_session(now,holidays) or not (9,30)<=(now.hour,now.minute)<=(14,30):return []
    prior=daily[daily.index.date<now.date()]
    if prior.empty or prior.index[-1].date()!=session_date(now.replace(hour=9,minute=0),holidays):return []
    # Exactly three contiguous completed 5m candles per 15m bar, session anchored 09:15.
    bars=[];times=[]
    for t,g in five.groupby(pd.Grouper(freq='15min',origin='start_day',offset='9h15min')):
        if len(g)!=3 or list(g.index)!=list(pd.date_range(t,periods=3,freq='5min')):continue
        bars.append([g.open.iloc[0],g.high.max(),g.low.min(),g.close.iloc[-1],g.volume.sum()]);times.append(t)
    if len(bars)<30:return []
    f=features(pd.DataFrame(bars,index=pd.DatetimeIndex(times),columns=['open','high','low','close','volume']))
    x=f.iloc[-1];p=f.iloc[-2];stamp=f.index[-1]
    if stamp.date()!=now.date() or (pd.Timestamp(now)-(stamp+pd.Timedelta(minutes=15))).total_seconds()>900:return []
    if len(f)>1 and f.index[-2].date()==stamp.date() and stamp-f.index[-2]!=pd.Timedelta(minutes=15):return []
    prev=prior.iloc[-1];pivot=(prev.high+prev.low+prev.close)/3;r1=2*pivot-prev.low;s1=2*pivot-prev.high
    r2=pivot+prev.high-prev.low;s2=pivot-prev.high+prev.low
    today=f[f.index.date==now.date()]
    out=[]
    if p.close<=r1<x.close and x.bull and today.open.iloc[0]<=r1 and x.close/prev.close<=1.04:
        entry=x.high*1.001;sl=max(entry*.98,x.low*.999)
        out.append(setup(item,'PDF R1 + Supertrend',stamp,entry,sl,
            f'Completed 15m close crosses R1 {r1:.2f}; Supertrend(10,3) green; no opening gap above R1.',
            'INTRADAY ONLY: 50% at +2%, remaining at cost / red Supertrend / R2; square off by 15:15 IST.',
            timeframe='15m · INTRADAY ONLY',t1=entry*1.02,t2=r2))
    if p.close>=s1>x.close and not x.bull and today.open.iloc[0]>=s1 and x.close/prev.close>=.96:
        entry=x.low*.999;sl=min(entry*1.02,x.high*1.001)
        out.append(setup(item,'PDF S1 + Supertrend',stamp,entry,sl,
            f'Completed 15m close crosses S1 {s1:.2f}; Supertrend(10,3) red; no opening gap below S1.',
            'INTRADAY ONLY: 50% at -2%, remaining at cost / green Supertrend / S2; square off by 15:15 IST.',
            side='SELL',timeframe='15m · INTRADAY ONLY',t1=entry*.98,t2=s2))
    return [r for r in out if r]

class PositionalScanner:
    def __init__(self,broker,root,holidays,job_lock,limit=None,watchlist=None):
        self.broker=broker;self.holidays=holidays;self.job_lock=job_lock
        self.limit=max(1,min(200,limit or MAX_SYMBOLS));self.watchlist=WATCHLIST if watchlist is None else watchlist
        self.store=StockScanner(broker,Path(root)/'positional',holidays,job_lock)
        self._lock=threading.RLock();self._stop=threading.Event();self._thread=None;self._worker=None
        self._state={'status':'WAITING FOR START'};self._last_slot=None;self._daily={};self._deadline=0
    def snapshot(self,now=None):
        now=now or datetime.now(IST);saved=self.store._read('positional',{'rows':[],'coverage':{}})
        with self._lock:state=dict(self._state)
        saved.update(refresh=state,sources=SOURCES,interval_seconds=300,universe_limit=self.limit,
            note='Daily signals use completed sessions; five-minute prices only review entry readiness. Targets are scenarios, not fills. Backend must remain running.')
        stamp=saved.get('updated_at');age=(now-datetime.fromisoformat(stamp)).total_seconds() if stamp else None
        saved['age_seconds']=age;saved['stale']=age is None or age>600 or state.get('status')=='FAILED'
        for r in saved['rows']:
            if saved['stale']:r['status']='STALE SCAN — DO NOT USE'
            elif not is_market_session(now,self.holidays()) and r['status'].startswith(('READY','WAITING','EXTENDED')):r['status']='CLOSED — REVIEW NEXT SESSION'
            elif r['timeframe']!='Daily' and (now.hour,now.minute)>(14,30) and r['status'].startswith('READY'):r['status']='ENTRY WINDOW CLOSED'
        return saved
    def _call(self,fn):
        while not self._stop.is_set() and time.monotonic()<self._deadline:
            if self.job_lock.acquire(timeout=.2):
                try:return fn()
                finally:self.job_lock.release()
        raise TimeoutError('Scan cancelled or 240-second budget exhausted; remaining stocks retry next cycle')
    def request(self,now=None):
        now=now or datetime.now(IST);slot=int(now.timestamp())//300
        with self._lock:
            if self._worker and self._worker.is_alive():return {'status':'BUSY'}
            if slot==self._last_slot:return {'status':'WAITING FOR NEXT FIVE-MINUTE CYCLE'}
            self._last_slot=slot;self._state={'status':'RUNNING','started_at':now.isoformat(),'completed':0}
            self._worker=threading.Thread(target=self._run,args=(now,),daemon=True,name='PositionalScan');self._worker.start()
        return {'status':'STARTED'}
    def _run(self,now):
        self._deadline=time.monotonic()+240
        rows=[];errors=[];done=0;eligible=0
        previous=self.store._read('positional',{'rows':[]})['rows']
        try:
            holidays=self.holidays()
            if holidays is None:raise ValueError('Configure verified holiday calendar before positional scans')
            if not self.broker.configured():raise ValueError('Configure Dhan credentials and active data access')
            items=self._call(self.broker.instruments)
            items=[x for x in items if x.get('kind')=='stock' and x.get('segment') in ('NSE_EQ','BSE_EQ')]
            if self.watchlist:
                wanted={str(x).upper() for x in self.watchlist}
                items=[x for x in items if wanted.intersection({str(x.get(k,'')).upper() for k in ('symbol','ticker','id')})]
            items=list({x['segment']+':'+str(x['id']):x for x in items}.values());available=len(items);items=items[:self.limit]
            expected=session_date(now,holidays);consecutive=0
            for item in items:
                key=item['segment']+':'+str(item['id'])
                try:
                    cache=self._daily.get(key)
                    if cache and cache[0]==expected:signals,d=cache[1],cache[2]
                    else:
                        d=self._call(lambda:self.broker.daily(item,now,days=550))
                        signals,d=daily_setups(d,item,now,holidays);self._daily[key]=(expected,signals,d)
                    eligible+=1;five=None
                    if is_market_session(now,holidays):
                        try:five=completed_five(self._call(lambda:self.broker.history(item,now,minutes=5,lookback_days=10)),now)
                        except (ValueError,RuntimeError,OSError) as exc:errors.append({'symbol':item['symbol'],'error':'5m price unavailable: '+str(exc)[:140]})
                    candidates=carry_daily(signals,previous,d,item)+r1_setups(d,five,item,now,holidays)
                    for r in candidates:
                        result=assess(r,five,now,holidays)
                        if r.get('tracking_status') and result['status'] in ('READY — REVIEW ENTRY','WAITING FOR ENTRY','EXTENDED — DO NOT CHASE','WAITING FOR PRICE','CLOSED — REVIEW NEXT SESSION'):
                            result['status']=r['tracking_status']
                        rows.append(result)
                    consecutive=0
                except TimeoutError:raise
                except Exception as exc:
                    errors.append({'symbol':item['symbol'],'error':str(exc)[:180]});consecutive+=1
                done+=1
                with self._lock:self._state.update(completed=done,total=len(items),current_symbol=item['symbol'])
                if consecutive>=3:break
                if self._stop.wait(.2):break
            coverage=dict(mapped=available,selected=len(items),scanned=done,eligible=eligible,errors=errors,
                omitted=max(0,available-len(items)),universe='Existing mapped cash-stock universe / INSIGHTS_WATCHLIST')
            # Publish only this cycle's evaluated rows, never mix old ready rows with new prices.
            self.store._write('positional',dict(rows=rows,coverage=coverage,updated_at=datetime.now(IST).isoformat(),analysis_at=now.isoformat()))
            with self._lock:self._state.update(status='COMPLETE' if done==len(items) and not errors else 'PARTIAL — CHECK COVERAGE',coverage=coverage)
        except Exception as exc:
            # Cached signals remain inspectable, but are explicitly invalidated on a failed refresh.
            with self._lock:self._state.update(status='FAILED',error=str(exc)[:200])
    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear()
        def loop():
            while not self._stop.is_set():
                self.request();self._stop.wait(10)
        self._thread=threading.Thread(target=loop,daemon=True,name='PositionalScheduler');self._thread.start()
    def stop(self):self._stop.set()
