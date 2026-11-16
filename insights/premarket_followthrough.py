"""Fixed pre-market watchlist: completed-candle checks at 09:45 and 10:00 IST."""
import json,math,threading,time
from datetime import datetime,timedelta
from pathlib import Path
import pandas as pd
from insights.config import IST,is_market_session
from insights.indicators import add_features,clean_bars,risk_levels
from insights.strategies import opening_redbar,momentum_query,fib_smc,swing,swing_opportunities,swing_guide
from insights.positional import daily_setups,r1_setups
from insights import swing_gann_wave

SLOTS=((9,45),(10,0))
def prior_session(now,holidays):
    day=now-timedelta(days=1)
    for _ in range(15):
        if is_market_session(day.replace(hour=10,minute=0),holidays):return day.date()
        day-=timedelta(days=1)
    raise ValueError('Verified previous session unavailable')
def completed(frame,now,minutes):
    if not isinstance(frame,pd.DataFrame) or not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:raise ValueError('Timezone-aware candles required')
    f=clean_bars(frame);f.index=f.index.tz_convert(IST)
    f=f[(f.index+pd.Timedelta(minutes=minutes)<=pd.Timestamp(now))&(f.index.hour*60+f.index.minute>=555)&(f.index.hour*60+f.index.minute<930)]
    return f

def assess(five,daily,fifteen,item,now,holidays):
    symbol=item['symbol'];checks=[];plans=[];context=[]
    f=completed(five,now,5);f15=completed(fifteen,now,15)
    d=clean_bars(daily)
    if not isinstance(d.index,pd.DatetimeIndex) or d.index.tz is None:raise ValueError('Dated daily history required')
    d=d[d.index.date<now.date()]
    if d.empty or d.index[-1].date()!=prior_session(now,holidays):raise ValueError('Previous-session daily history missing')
    today=f[f.index.date==now.date()]
    required=pd.date_range(now.replace(hour=9,minute=15,second=0,microsecond=0),now-timedelta(minutes=5),freq='5min')
    if len(today)!=len(required) or not today.index.equals(required):raise ValueError('Missing or stale completed opening-session candles')
    x=add_features(f).iloc[-1];last=float(x.close);volume=float(today.volume.sum());turnover=float((today.close*today.volume).sum())
    rvol=float(x.rvol);adx=float(x.adx);vwap=float(x.vwap);rsi=momentum_query._rsi(f.close)
    liquid=volume>=100000 and turnover>=10000000 and last>=20
    usable=all(math.isfinite(v) for v in (rvol,adx,vwap,float(x.atr)))
    vital=usable and liquid and rvol>=1.5 and adx>=20
    metrics=dict(rsi=round(rsi,2) if rsi is not None else None,atr=round(float(x.atr),2),gap_pct=round(100*(float(today.open.iloc[0])/float(d.close.iloc[-1])-1),2),close=round(last,2),session_volume=volume,turnover_cr=round(turnover/1e7,3),rvol=round(rvol,2) if math.isfinite(rvol) else None,adx=round(adx,2) if math.isfinite(adx) else None,vwap=round(vwap,2) if math.isfinite(vwap) else None,
                 ema20=round(float(x.ema20),2),ema50=round(float(x.ema50),2),previous_high=float(d.high.iloc[-1]) if len(d) else None,previous_low=float(d.low.iloc[-1]) if len(d) else None)
    def record(name,status,reason):checks.append(dict(strategy=name,status=status,reason=str(reason)))
    def accept(plan):
        side=plan['direction'];aligned=last>vwap and last>x.ema20>x.ema50 if side=='BUY' else last<vwap and last<x.ema20<x.ema50
        if not vital or not aligned or rsi is None or not (rsi>=55 if side=='BUY' else rsi<=45):
            record(plan['strategy'],'FILTERED','Requires ≥1 lakh session volume, ₹1 crore turnover proxy, price ≥₹20, RVOL ≥1.5, ADX ≥20 aligned VWAP/EMA20/EMA50 and RSI ≥55 BUY / ≤45 SELL');return
        entry,sl,t1,t2=(float(plan[k]) for k in ('entry','sl','t1','t2'));sign=1 if side=='BUY' else -1
        if not all(math.isfinite(v) and v>0 for v in (entry,sl,t1,t2)) or not (0<sign*(entry-sl)/entry<=.06 and sign*(t1-entry)>0 and sign*(t2-t1)>0):
            record(plan['strategy'],'FILTERED','Invalid target ordering or stop distance');return
        plan.update(symbol=symbol,status='CONFIRMED CLOSED-CANDLE RESEARCH',signal_at=f.index[-1].isoformat(),level_basis='CASH STOCK PRICES — NOT OPTION PREMIUMS')
        plan['reasons']=list(plan.get('reasons',[]))+['Session liquidity, RVOL, ADX, VWAP, EMA and RSI alignment passed']
        plans.append(plan);record(plan['strategy'],'MATCH','; '.join(plan['reasons']))
    for r in opening_redbar.evaluate(f,now):
        if r.get('state')=='DIRECTION_READY':
            accept(dict(strategy=r['strategy'],direction='BUY' if r['side']=='CE' else 'SELL',entry=r['spot_entry'],sl=r['spot_sl'],t1=r['spot_t1'],t2=r['spot_t2'],reasons=[r['reason']]))
        else:record(r['strategy'],r['state'],r['reason'])
    for side in ('BUY','SELL'):
        try:
            p=momentum_query.candidate(f,d,f15,symbol,now,side)
            if p:accept(p)
            else:record('Daily + 15m Momentum '+side,'NO MATCH','Not all existing daily/15m rules passed; daily candle remains provisional')
        except (ValueError,KeyError,IndexError):record('Daily + 15m Momentum '+side,'DATA UNAVAILABLE','Insufficient indicator history')
    r=fib_smc.evaluate(f,now,'0945')
    record('09:45 Fib + SMC',r.get('state','UNAVAILABLE'),r.get('reason','No confirmation'))
    if r.get('state')=='STRUCTURE_READY':
        record('Fib + OI','UNVERIFIED','Stock-only monitor has no derivative OI confirmation; no OI-backed entry inferred')
    first=today.iloc[:3];last_two=today.close.tail(2)
    for side,level in [('BUY',float(first.high.max())),('SELL',float(first.low.min()))]:
        broken=(last_two>level).all() if side=='BUY' else (last_two<level).all()
        if len(today)>=6 and broken:
            stop=min(float(today.low.tail(3).min()),last-float(x.atr)) if side=='BUY' else max(float(today.high.tail(3).max()),last+float(x.atr))
            try:accept(dict(strategy='Opening 15m range + vital confirmations',direction=side,reasons=['Two completed 5m closes beyond opening 15m '+('high' if side=='BUY' else 'low')],**risk_levels(last,x.atr,side,stop)))
            except ValueError:record('Opening 15m range '+side,'FILTERED','Risk distance unsuitable')
        else:record('Opening 15m range '+side,'NO MATCH','Waiting for two completed closes beyond range')
    # Existing longer-term strategies remain context; do not relabel their horizons as intraday trades.
    for name,fn in [('Daily swing',lambda:swing.scan(d,symbol,now)),('Swing opportunities',lambda:swing_opportunities.evaluate(d,symbol,now)),('Swing guide',lambda:swing_guide.evaluate(d,symbol,now)),('Positional daily templates',lambda:daily_setups(d,item,now,holidays)[0]),('R1/S1 Supertrend',lambda:r1_setups(d,f,item,now,holidays)),('Gann / wave context',lambda:swing_gann_wave.assess(d,now))]:
        try:
            result=fn();status=(str(len(result))+' matches' if isinstance(result,list) else str(result.get('status',result.get('alignment','Reviewed'))))
            context.append(dict(strategy=name,status=status,reason='Longer-term/conditional context only; review original tab for its timeframe and guards'))
        except Exception:context.append(dict(strategy=name,status='DATA UNAVAILABLE',reason='Required history or indicator inputs unavailable'))
    for name,why in [('Legacy opening-range VWAP','Existing strategy starts at 10:15 and needs index/sector comparison'),('BTST / closing strength','Only valid in the afternoon closing window'),('12:45 Fib','Reference period has not formed'),('Options / futures OI','Derivative contract, premium and OI inputs required; not cash-stock levels'),('Multibagger / QGLP','Requires dated fundamentals, surveillance and appropriate long-term eligibility'),('EMA9 trendline PDF','Requires adjusted-data confirmation and its separate positional scanner context'),('Executed order flow','Live pilot remains Index Options only; candle volume is not trade delta')]:context.append(dict(strategy=name,status='NOT APPLICABLE / NOT DUE',reason=why))
    sides={p['direction'] for p in plans}
    if len(sides)>1:
        plans=[];record('Cross-strategy agreement','CONFLICT','Opposite confirmed directions; no current entry promoted')
    return dict(symbol=symbol,metrics=metrics,checks=checks,context=context,signals=plans,status='BREAKOUT' if plans and plans[0]['direction']=='BUY' else 'BREAKDOWN' if plans else 'NO CONFIRMED ENTRY')

class PremarketFollowthrough:
    def __init__(self,service,holidays):
        self.service=service;self.holidays=holidays;self.path=service.root/'premarket_followthrough.json';self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None;self.daily={};self.error=''
        try:
            self.state=json.loads(self.path.read_text())
            if not isinstance(self.state,dict) or not isinstance(self.state.get('passes'),dict) or not isinstance(self.state.get('symbols'),list):raise ValueError('Invalid saved monitor')
        except (OSError,ValueError):self.state=dict(session=None,symbols=[],passes={})
        self.state['passes']={k:v for k,v in self.state.get('passes',{}).items() if v.get('status')=='COMPLETE'}
    def save(self):
        try:
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.state,allow_nan=False));temp.replace(self.path)
        except (OSError,ValueError,TypeError):self.error='Could not persist morning assessment'
    def call(self,fn):
        if not self.service._job_lock.acquire(timeout=2):raise ValueError('Dhan scanner busy; data unavailable for this pass')
        try:return fn()
        finally:self.service._job_lock.release()
    def freeze(self,now):
        if self.state.get('session')==now.date().isoformat():return bool(self.state.get('symbols'))
        p=self.service.snapshot('pre-market');prior=prior_session(now,self.holidays())
        rows=p.get('gainers',[])+p.get('losers',[])
        if p.get('mixed_data_dates') or p.get('previous_session')!=prior.isoformat() or not rows:self.error='Waiting for verified previous-session pre-market list';return False
        self.state=dict(session=now.date().isoformat(),symbols=list(dict.fromkeys(r['symbol'] for r in rows)),passes={},frozen_at=now.isoformat());self.daily={};self.error='';self.save();return True
    def run_due(self,now):
        now=now.astimezone(IST)
        if not is_market_session(now,self.holidays()) or (now.hour,now.minute)>=(10,15):return
        with self.lock:
            if not self.freeze(now):return
        # Cache daily history once after 09:15, on the frozen symbols only.
        if (now.hour,now.minute)<(9,45):
            for symbol in list(self.state['symbols']):
                if self.stop_event.is_set():return
                if symbol in self.daily:continue
                try:
                    item=self.call(lambda:self.service._lookup(symbol))
                    if item:self.daily[symbol]=self.call(lambda:self.service.broker.daily(item,now,days=1300))
                except Exception:continue
            return
        clock='10:00' if (now.hour,now.minute)>=(10,0) else '09:45'
        with self.lock:
            cutoff=now.replace(hour=int(clock[:2]),minute=int(clock[3:]),second=0,microsecond=0)
            result=self.state['passes'].get(clock)
            if result:
                pending=[r['symbol'] for r in result['rows'] if r.get('status')=='DATA UNAVAILABLE']
                if not pending or result.get('attempts',1)>=3 or (now-cutoff).total_seconds()>480:return
                result['status']='RUNNING';result['attempts']=result.get('attempts',1)+1
            else:
                pending=list(self.state['symbols'])
                result=dict(status='RUNNING',cutoff=cutoff.isoformat(),started_at=now.isoformat(),rows=[],signals=[],attempts=1)
                self.state['passes'][clock]=result
        for symbol in pending:
            if self.stop_event.is_set():break
            try:
                item=self.call(lambda:self.service._lookup(symbol))
                if not item:raise ValueError('Instrument mapping unavailable')
                daily=self.daily.get(symbol)
                if daily is None:daily=self.call(lambda:self.service.broker.daily(item,cutoff,days=1300));self.daily[symbol]=daily
                five=self.call(lambda:self.service.broker.history(item,cutoff,minutes=5,lookback_days=20))
                fifteen=self.call(lambda:self.service.broker.history(item,cutoff,minutes=15,lookback_days=30))
                row=assess(five,daily,fifteen,item,cutoff,self.holidays())
            except Exception as exc:row=dict(symbol=symbol,status='DATA UNAVAILABLE',reason=str(exc)[:120] if isinstance(exc,ValueError) else 'Source or strategy inputs unavailable',checks=[],context=[],signals=[])
            with self.lock:
                result['rows']=[r for r in result['rows'] if r['symbol']!=symbol]+[row]
                result['signals']=[p for r in result['rows'] for p in r['signals']]
        with self.lock:
            result['status']='COMPLETE';result['updated_at']=datetime.now(IST).isoformat();self.save()
    def snapshot(self,now=None):
        now=now or datetime.now(IST)
        with self.lock:state=json.loads(json.dumps(self.state));state['error']=self.error
        for result in state.get('passes',{}).values():
            cutoff=datetime.fromisoformat(result['cutoff']);result['historical']=(now-cutoff).total_seconds()>600 or cutoff.date()!=now.date() or not is_market_session(now,self.holidays())
        latest=state.get('passes',{}).get('10:00') or state.get('passes',{}).get('09:45') or {}
        state.update(signals=latest.get('signals',[]) if not latest.get('historical',True) and latest.get('status')=='COMPLETE' else [],updated_at=latest.get('updated_at'),stale=latest.get('historical',True))
        return state
    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear()
        def loop():
            while not self.stop_event.is_set():
                try:self.run_due(datetime.now(IST))
                except Exception:self.error='Morning monitor unavailable; other scans continue'
                self.stop_event.wait(15)
        self.thread=threading.Thread(target=loop,daemon=True,name='PremarketFollowthrough');self.thread.start()
    def stop(self):self.stop_event.set()
