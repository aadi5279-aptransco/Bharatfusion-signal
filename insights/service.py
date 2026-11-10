"""Background, non-overlapping research scans. HTTP requests read cached snapshots."""
from __future__ import annotations
import json,os,re,threading,time
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from insights.config import IST,ROOT,WATCHLIST,MAX_SYMBOLS,is_market_session
from insights.db import Journal
from insights.brokers.dhan import DhanReadOnly,BrokerUnavailable
from insights.indicators import index_bias
from insights.strategies import equity,options,futures
from insights.scanner_quality import recent_frame,recent_context

DISCLAIMER='Rule-based research, not investment advice. Signals are not guaranteed; trading can cause significant losses. No orders are placed.'


def _norm(symbol):
    return ''.join(ch for ch in symbol.upper() if ch.isalnum())


def _holiday_set():
    p=os.getenv('INSIGHTS_HOLIDAY_FILE','')
    if not p or not Path(p).is_file():return None
    try:
        obj=json.loads(Path(p).read_text('utf-8'))
        if obj.get('year')!=datetime.now(IST).year or not isinstance(obj.get('holidays'),list):return None
        return set(obj['holidays'])
    except (OSError,ValueError,TypeError):return None


def _sector_map():
    p=os.getenv('INSIGHTS_SECTOR_MAP_FILE','')
    try:
        raw=json.loads(Path(p).read_text('utf-8')) if p else {}
        return {_norm(str(k)):_norm(str(v)) for k,v in raw.items()}
    except (OSError,ValueError,TypeError):return {}


class InsightsService:
    def __init__(self,broker=None,root=None):
        self.broker=broker or DhanReadOnly();self.root=Path(root or ROOT)
        self.journal=Journal(self.root/'insights.sqlite')
        self._lock=threading.RLock();self._job_lock=threading.Lock()
        self._instruments=[];self._last_error='';self._timestamps={};self._snapshots={
          'dashboard':{'indices':[],'sectors':[],'status':'WAITING FOR DATA'},
          'intraday':{'signals':[],'status':'WAITING FOR 10:15 IST SCAN'},
          'btst':{'signals':[],'status':'WAITING FOR 15:00 IST SCAN'},
          'index-options':{'signals':[],'status':'WAITING FOR OPTION CHAIN'},
          'fo-stocks':{'signals':[],'status':'WAITING FOR FUTURES OI'}}
        self._done=set();self._thread=None;self._stop=threading.Event()
        self._manual_requested_at=0.0
        self._manual_thread=None
        self._manual_refresh=dict(status='IDLE')

    def instruments(self):
        with self._lock:
            if self._instruments:return list(self._instruments)
        if not self.broker.configured():raise BrokerUnavailable('Dhan credentials not configured')
        items=self.broker.instruments()
        with self._lock:self._instruments=list(items)
        return items

    def _lookup(self,name):
        target=_norm(name)
        return next((x for x in self.instruments() if _norm(x['symbol'])==target or _norm(x.get('ticker',''))==target),None)

    def _stock_list(self):
        all_items=[x for x in self.instruments() if x.get('kind')=='stock']
        if WATCHLIST:
            selected={_norm(n) for n in WATCHLIST}
            all_items=[x for x in all_items if _norm(x['symbol']) in selected or _norm(x.get('ticker','')) in selected]
        else:
            # The default universe must include mapped-sector stocks first.
            # Do not pretend an alphabetical first-30 sample covers all F&O.
            mapped=_sector_map()
            all_items.sort(key=lambda x:(
                _norm(x['symbol']) not in mapped and _norm(x.get('ticker','')) not in mapped,
                _norm(x['symbol'])
            ))
        return all_items[:MAX_SYMBOLS]

    def _update(self,name,payload,now):
        with self._lock:
            payload=dict(payload);payload['updated_at']=now.isoformat();payload['disclaimer']=DISCLAIMER
            self._snapshots[name]=payload;self._timestamps[name]=now.isoformat()

    def snapshot(self,name):
        with self._lock:return dict(self._snapshots.get(name,{'status':'UNKNOWN TAB'}))

    def health(self):
        with self._lock:return dict(status=('CONNECTED' if getattr(self.broker,'_last_ok',None) and time.monotonic()-self.broker._last_ok<600 else 'CONFIGURED — UNVERIFIED') if self.broker.configured() else 'NEEDS_DHAN_CONFIGURATION',
          source='DHAN',read_only=True,orders_enabled=False,updated_at=dict(self._timestamps),last_error=self._last_error,
          holiday_calendar='CONFIGURED' if _holiday_set() is not None else 'NOT CONFIGURED — scans blocked',
          manual_refresh=dict(self._manual_refresh),disclaimer=DISCLAIMER)

    def dashboard(self,now):
        """Snapshot the most recent *completed* Dhan session, not assumed live prices."""
        now=now.astimezone(IST)
        items=[i for i in self.instruments() if i.get('kind') in ('index','sector')]
        indices=[];sectors=[]
        for item in items:
            try:
                f=self.broker.history(item,now,minutes=5)
                # Defence in depth: never score a candle which hasn't finished yet.
                f=f[f.index+pd.Timedelta(minutes=5)<=pd.Timestamp(now)]
                if f.empty:continue
                last=f.index[-1]
                session=f[f.index.date==last.date()]
                if session.empty:continue
                change=round((float(session.close.iloc[-1])/float(session.open.iloc[0])-1)*100,2)
                metadata=dict(session_change=change,session_date=last.date().isoformat(),
                              asof=last.isoformat())
                if item['kind']=='index':
                    result=index_bias(f,item['symbol']);result.update(metadata)
                    indices.append(result)
                    if _norm(item['symbol']) in ('BANKNIFTY','NIFTYBANK'):
                        sectors.append(dict(symbol=item['symbol'],sector='Bank',**metadata))
                else:
                    sectors.append(dict(symbol=item['symbol'],sector=item.get('sector',item['symbol']),**metadata))
            except (BrokerUnavailable,ValueError,KeyError):continue
        nifty=next((x for x in indices if _norm(x['symbol']) in ('NIFTY','NIFTY50')),None)
        if nifty:
            for sector in sectors:
                # Never compare returns from two different trading sessions.
                if sector['session_date']==nifty['session_date']:
                    sector['relative_strength']=round(sector['session_change']-nifty['session_change'],2)
        sectors.sort(key=lambda x:x.get('relative_strength',x['session_change']),reverse=True)
        reference=nifty or (max(indices,key=lambda x:x['asof']) if indices else None)
        candle_at=pd.Timestamp(reference['asof']) if reference else None
        age_minutes=(pd.Timestamp(now)-candle_at).total_seconds()/60 if candle_at is not None else None
        not_live=(candle_at is None or candle_at.date()!=now.date()
                  or not is_market_session(now,_holiday_set()) or age_minutes>15)
        status=('HISTORICAL SNAPSHOT — NOT LIVE' if not_live else 'READY — SESSION DATA') if indices else 'NO VERIFIED INDEX DATA'
        payload=dict(indices=indices,sectors=sectors,status=status,
                     coverage=dict(indices=len(indices),sectors=len(sectors)),
                     session_date=reference['session_date'] if reference else None,
                     data_asof=reference['asof'] if reference else None,
                     data_age_minutes=round(age_minutes,1) if age_minutes is not None else None,
                     not_live=not_live,source='DHAN COMPLETED CANDLES',
                     vix='UNAVAILABLE',fii_dii='UNAVAILABLE')
        self._update('dashboard',payload,now)
        return payload

    def request_dashboard_refresh(self,now=None):
        """Local read-only refresh; serialized with scheduled scans and rate limited."""
        if not self.broker.configured():
            return dict(status='UNAVAILABLE',error='Configure Dhan credentials first')
        now=now or datetime.now(IST)
        tick=time.monotonic()
        with self._lock:
            if self._manual_refresh.get('status')=='RUNNING':
                return dict(status='BUSY',error='A manual refresh is already running')
            if tick-self._manual_requested_at<45:
                return dict(status='RATE_LIMITED',error='Please allow 45 seconds between refresh requests')
            if not self._job_lock.acquire(blocking=False):
                return dict(status='BUSY',error='Scheduled scan is running; retry when it finishes')
            self._manual_requested_at=tick
            requested_at=now.isoformat()
            self._manual_refresh=dict(status='RUNNING',requested_at=requested_at)

        def work():
            state='SUCCEEDED';message='Completed Dhan market-data snapshot'
            try:
                result=self.dashboard(now)
                if not result['indices']:
                    state='NO_DATA'
                    message='No verified completed index candles available from Dhan'
            except (BrokerUnavailable,ValueError,KeyError) as exc:
                state='FAILED';message=str(exc)[:160]
            except Exception:
                state='FAILED';message='Unexpected market-data refresh error; see server logs'
            finally:
                with self._lock:
                    self._manual_refresh=dict(status=state,requested_at=requested_at,
                                              completed_at=datetime.now(IST).isoformat(),
                                              message=message)
                    if state in ('FAILED','NO_DATA'):
                        self._last_error='manual dashboard: '+message
                    elif self._last_error.startswith('manual dashboard:'):
                        self._last_error=''
                self._job_lock.release()
        self._manual_thread=threading.Thread(target=work,daemon=True,name='ManualDashboardRefresh')
        self._manual_thread.start()
        return dict(status='STARTED',requested_at=requested_at,
                    note='Fetching completed Dhan candles; no orders will be placed')

    def _context(self):
        snap=self.snapshot('dashboard');indices=snap.get('indices',[])
        nifty=next((x for x in indices if _norm(x['symbol']) in ('NIFTY','NIFTY50')),None)
        sec={_norm(x['sector']):x for x in snap.get('sectors',[])}
        return nifty,sec

    def scan_intraday(self,now):
        """Live-session candidates only; no historical or incomplete-bar signals."""
        now=now.astimezone(IST)
        nifty,sectors=self._context()
        mapping=_sector_map()
        stocks=self._stock_list()
        candidates=[]
        stats=dict(scanned=len(stocks),data_assessed=0,unavailable_count=0,
                   stale_data=0,missing_sector=0,rules_not_met=0)
        context_ok=recent_context(nifty,now)
        if not context_ok:
            data=dict(signals=[],status='NO VERIFIED CURRENT-SESSION NIFTY CONTEXT',
                      **stats,note='No scan until NIFTY candles are fresh and completed.')
            self._update('intraday',data,now)
            return data
        for item in stocks:
            sector_name=mapping.get(_norm(item['symbol']),mapping.get(_norm(item.get('ticker','')),''))
            sec=sectors.get(sector_name)
            if not sec or not recent_context(sec,now):
                stats['missing_sector']+=1
                continue
            try:
                bars=self.broker.history(item,now,minutes=5)
                if not recent_frame(bars,now,5,20):
                    stats['stale_data']+=1
                    continue
                if len(bars)<201:
                    stats['unavailable_count']+=1
                    continue
                stats['data_assessed']+=1
                signal=equity.intraday(bars,item['symbol'],now,nifty['session_change'],sec['session_change'])
                if signal is None:
                    stats['rules_not_met']+=1
                    continue
                signal.update(backtest_status='UNVALIDATED',instrument_id=item['id'],
                              segment=item['segment'],instrument_type=item['instrument'],
                              data_asof=bars.index[-1].isoformat(),
                              quote_freshness='CURRENT COMPLETED CASH CANDLE')
                self.journal.record(signal)
                candidates.append(signal)
            except (BrokerUnavailable,ValueError,KeyError,TypeError):
                stats['unavailable_count']+=1
        candidates.sort(key=lambda x:x['confidence'],reverse=True)
        status=('RESEARCH ONLY — BACKTEST VALIDATION REQUIRED' if candidates
                else 'NO QUALIFYING RULE-BASED CANDIDATES' if stats['data_assessed']
                else 'SCANNED — SECTOR HISTORY MISSING/STALE' if stats['missing_sector']
                else 'SCANNED — STOCK CANDLES MISSING/STALE')
        data=dict(signals=candidates[:10],status=status,**stats,
                  qualified=len(candidates),
                  note='Cash-side research candidates only; no execution and no guarantee.')
        self._update('intraday',data,now)
        return data

    def scan_btst(self,now):
        _,sectors=self._context();mapping=_sector_map();picks=[];skipped=0
        path=os.getenv('INSIGHTS_LICENSED_DELIVERY_FILE','')
        try:delivery=json.loads(Path(path).read_text('utf-8')) if path else {}
        except (OSError,ValueError,TypeError):delivery={}
        current=delivery.get('date')==now.date().isoformat()
        for item in self._stock_list():
            sec=sectors.get(mapping.get(_norm(item['symbol']),mapping.get(_norm(item.get('ticker','')),'')))
            vals=(delivery.get('values') or {})
            dp=vals.get(item['symbol'],vals.get(item.get('ticker',''))) if current else None
            if not sec or dp is None:skipped+=1;continue
            try:
                f=self.broker.history(item,now,minutes=5,lookback_days=50)
                daily=self.broker.daily(item,now,days=80)
                # Historical intraday data is required to compare matching 15:00 volume.
                complete={}
                for day,g in f.groupby(f.index.normalize()):
                    matched=g[(g.index.hour*60+g.index.minute>=555)&(g.index.hour*60+g.index.minute<900)]
                    if len(matched)==69 and matched.index[0]==day+pd.Timedelta(hours=9,minutes=15) and matched.index[-1]==day+pd.Timedelta(hours=14,minutes=55):
                        complete[day.date()]=float(matched.volume.sum())
                daily['volume_1500']=[complete.get(d.date(),float('nan')) for d in daily.index]
                if daily.volume_1500.tail(20).isna().any():skipped+=1;continue
                signal=equity.btst(daily,f,item['symbol'],now,delivery_pct=dp,sector_return=sec['session_change'])
                if signal:
                    signal.update(backtest_status='UNVALIDATED',instrument_id=item['id'],segment=item['segment'],instrument_type=item['instrument'])
                    self.journal.record(signal);picks.append(signal)
            except (BrokerUnavailable,ValueError,KeyError):skipped+=1
        picks.sort(key=lambda x:x['confidence'],reverse=True)
        status='RESEARCH ONLY — BACKTEST VALIDATION REQUIRED' if picks else 'NO QUALIFIED BTST: requires Dhan matched-time history + licensed dated delivery data'
        data=dict(signals=picks[:10],status=status,scanned=len(self._stock_list()),blocked=skipped)
        self._update('btst',data,now)
        return data

    def analyse(self,symbol,now=None,expiry=None):
        now=now or datetime.now(IST)
        if len(symbol)>64 or not symbol.strip():raise ValueError('Invalid symbol')
        match=re.fullmatch(r'(.+?)\s+(\d+(?:\.\d+)?)\s+(CE|PE)',symbol.strip(),re.I)
        underlying=match.group(1) if match else symbol.strip()
        requested_strike=float(match.group(2)) if match else None
        requested_side=match.group(3).upper() if match else None
        item=self._lookup(underlying)
        if not item:raise ValueError('Symbol not found in Dhan instrument master')
        expiries=self.broker.expiry_list(item)
        valid=[x for x in sorted(expiries) if x>=now.date().isoformat()]
        if expiry is not None and expiry not in valid:raise ValueError('Expiry is not available')
        if not valid:raise ValueError('No current expiry')
        selected=expiry or valid[0];chain=self.broker.option_chain(item,selected)
        m=options.chain_metrics(chain)
        bias='Uptrend' if m['pcr']>=1.2 else 'Downtrend' if m['pcr']<=.8 else 'Sideways'
        plan=None;note='PCR is a positioning proxy, not proof of direction.'
        if bias!='Sideways' or requested_side:
            try:plan=options.option_plan(chain,item['symbol'],bias,selected,now,side_override=requested_side,requested_strike=requested_strike)
            except ValueError as exc:note=str(exc)
        candles=[]
        try:
            f=self.broker.history(item,now,minutes=5)
            candles=[dict(time=int(t.timestamp()),open=float(r.open),high=float(r.high),low=float(r.low),close=float(r.close)) for t,r in f.tail(120).iterrows()]
        except (BrokerUnavailable,ValueError):pass
        return dict(symbol=item['symbol'],expiry=selected,expiries=valid[:15],spot=chain.get('last_price'),candles=candles,
             bias=bias,metrics=m,plan=plan,status='RESEARCH ONLY — CONTRACT QUOTE FRESHNESS NOT VERIFIED',note=note,disclaimer=DISCLAIMER)

    def scan_index_options(self,now):
        d=self.snapshot('dashboard');indices=d.get('indices',[]);signals=[]
        for idx in indices:
            if _norm(idx['symbol']) not in ('NIFTY','NIFTY50','BANKNIFTY','NIFTYBANK','SENSEX') or idx['bias'] not in ('Uptrend','Downtrend') or not recent_context(idx,now):
                continue
            try:
                item=self._lookup(idx['symbol']);exps=self.broker.expiry_list(item)
                expiry=next((x for x in sorted(exps) if x>=now.date().isoformat()),None)
                if not expiry:continue
                p=options.option_plan(self.broker.option_chain(item,expiry),idx['symbol'],idx['bias'],expiry,now)
                if p:
                    p.update(backtest_status='UNVALIDATED',
                             status='HYPOTHETICAL — OPTION QUOTE AGE NOT VERIFIED',
                             instrument_id=p['security_id'],
                             segment='NSE_FNO' if _norm(idx['symbol'])!='SENSEX' else 'BSE_FNO',
                             instrument_type='OPTIDX',quote_freshness='NOT VERIFIED',
                             research_only=True)
                    signals.append(p)
                    # Never journal a hypothetical premium price as an observed signal.
            except (ValueError,BrokerUnavailable,KeyError):continue
        self._update('index-options',dict(signals=signals,status='RESEARCH ONLY — PREMIUM BACKTEST NEEDED' if signals else 'SCAN COMPLETE — NO QUALIFIED INDEX OPTION CONTRACTS',
              scanned=len(indices),qualified=len(signals),note='Requires supported expiry/option chain and verified option premium; no trades placed'),now)
        return signals

    def scan_fo(self,now):
        signals=[];unavailable=0
        for item in self._stock_list()[:10]:
            future=item.get('future')
            if not future:unavailable+=1;continue
            try:
                f=self.broker.history(future,now,minutes=15,lookback_days=8,oi=True)
                if not recent_frame(f,now,15,35):
                    unavailable+=1
                    continue
                s=futures.buildup(f,item['symbol'],now)
                if not s:continue
                exps=self.broker.expiry_list(item)
                expiry=next((x for x in sorted(exps) if x>now.date().isoformat()),None)
                if not expiry:continue
                chain=self.broker.option_chain(item,expiry)
                plan=options.option_plan(chain,item['symbol'],'Uptrend' if s['direction']=='CE' else 'Downtrend',expiry,now,side_override=s['direction'])
                if not plan:continue
                plan.update(strategy=futures.NAME,version=futures.VERSION,
                   reasons=s['reasons']+plan['reasons'],backtest_status='UNVALIDATED',
                   status='HYPOTHETICAL — OPTION QUOTE AGE NOT VERIFIED',
                   instrument_id=plan['security_id'],segment='NSE_FNO',
                   instrument_type='OPTSTK',quote_freshness='NOT VERIFIED',research_only=True)
                # No journal record: option entry premiums are not timestamp-verified.
                signals.append(plan)
            except (BrokerUnavailable,ValueError,KeyError):unavailable+=1
        self._update('fo-stocks',dict(signals=signals,status='RESEARCH ONLY — option premium backtest required' if signals else 'SCAN COMPLETE — NO QUALIFIED FUTURES/OI SETUPS',
              scanned=len(self._stock_list()[:10]),unavailable_count=unavailable,qualified=len(signals),note='Futures OI and valid option chain are mandatory; no invented premium'),now)
        return signals

    def reconcile_outcomes(self,now):
        # Observe completed 5m Dhan bars; both target and stop in one bar -> stop.
        # This is PAPER outcome observation, never broker fill confirmation.
        updated=0
        for record in self.journal.pending(limit=20):
            try:
                timestamp=pd.Timestamp(record['signal_at']).tz_convert(IST)
                if timestamp>=pd.Timestamp(now):continue
                item=dict(id=record['instrument_id'],segment=record['segment'],instrument=record['instrument_type'])
                if not all(item.values()):continue
                f=self.broker.history(item,now,minutes=5,lookback_days=min(75,max(6,(now.date()-timestamp.date()).days+2)))
                after=f[f.index>timestamp]
                if after.empty:continue
                entry=float(record['entry']);stop=float(record['sl']);target=float(record['t1']);sign=1 if record['direction'] in ('BUY','CE','PE') else -1
                # At most first 75 completed five-minute bars (intraday time exit).
                for ix,row in after.iloc[:75].iterrows():
                    stop_hit=(row.low<=stop if sign==1 else row.high>=stop)
                    target_hit=(row.high>=target if sign==1 else row.low<=target)
                    if stop_hit or target_hit:
                        outcome='SL' if stop_hit else 'T1';exit_price=stop if stop_hit else target
                        if self.journal.outcome(record['id'],outcome,str(ix),exit_price):updated+=1
                        break
                else:
                    if len(after)>=75:
                        last=after.iloc[74]
                        if self.journal.outcome(record['id'],'EXPIRED',str(after.index[74]),float(last.close)):updated+=1
            except (BrokerUnavailable,ValueError,TypeError,KeyError):continue
        return updated

    def run_due(self,now=None):
        now=now or datetime.now(IST)
        calendar=_holiday_set()
        if not is_market_session(now,calendar):return dict(status='BLOCKED — holiday calendar missing, weekend or outside trading hours')
        if not self._job_lock.acquire(blocking=False):return dict(status='SCAN ALREADY RUNNING')
        completed=[]
        try:
            day=now.date().isoformat()
            jobs=[('dashboard',(9,20),self.dashboard),('intraday',(10,15),self.scan_intraday),
                  ('btst',(15,0),self.scan_btst),('index-options',(10,0),self.scan_index_options),('fo-stocks',(10,0),self.scan_fo)]
            for name,clock,job in jobs:
                key=(day,name)
                if (now.hour,now.minute)<clock or key in self._done:continue
                try:job(now);completed.append(name)
                except (BrokerUnavailable,ValueError,KeyError) as exc:
                    with self._lock:self._last_error=f'{name}: {str(exc)[:160]}'
                if name in completed:self._done.add(key)
            # Refresh dashboard every five minutes without overlapping jobs.
            minute=now.hour*60+now.minute
            key=(day,'dashboard-refresh',minute//5)
            if minute%5==0 and key not in self._done:
                if 'dashboard' not in completed:
                    try:self.dashboard(now);completed.append('dashboard-refresh')
                    except (BrokerUnavailable,ValueError,KeyError) as exc:
                        with self._lock:self._last_error=f'dashboard: {str(exc)[:160]}'
                self._done.add(key)
            outcome_key=(day,'outcomes',minute//5)
            if minute%5==0 and outcome_key not in self._done:
                try:self.reconcile_outcomes(now)
                except (BrokerUnavailable,ValueError):pass
                self._done.add(outcome_key)
            return dict(status='OK',completed=completed)
        finally:self._job_lock.release()

    def start(self):
        if self._thread:return
        def loop():
            while not self._stop.is_set():
                try:self.run_due()
                except Exception:
                    with self._lock:self._last_error='Unexpected scan error (no orders sent)'
                self._stop.wait(20)
        self._thread=threading.Thread(target=loop,daemon=True,name='MarketInsightsScheduler');self._thread.start()

    def stop(self):self._stop.set()
