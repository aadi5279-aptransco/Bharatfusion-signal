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
from insights import advanced_smc
from insights.strategies import swing,multibagger,momentum_query
from insights import ai_rank

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
          'intraday':{'signals':[],'buy_signals':[],'sell_signals':[],'status':'WAITING FOR 09:45 SHORTLIST'},
          'btst':{'signals':[],'status':'WAITING FOR 15:00 IST SCAN'},
          'index-options':{'signals':[],'status':'WAITING FOR OPTION CHAIN'},
          'fo-stocks':{'signals':[],'status':'WAITING FOR FUTURES OI'},
          'swing-trades':{'signals':[],'status':'WAITING FOR COMPLETED DAILY SCAN'},
          'multibagger':{'candidates':[],'status':'WAITING FOR COMPLETED DAILY SCAN'}}
        self._done=set();self._thread=None;self._stop=threading.Event()
        self._shortlist_date=None
        self._shortlist_finalized=False
        self._shortlist=[]
        self._shortlist_up=[]
        self._shortlist_down=[]
        self._preview_buy=[]
        self._preview_sell=[]
        self._discovery_mode='NOT RUN'
        self._breadth_quotes=0
        self._discovery_scanned=0
        self._discovery_data_assessed=0
        self._discovery_stale=0
        self._discovery_errors=0
        self._discovery_missing_structure=0
        self._intraday_daily_cache={}
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

    def discover_shortlist(self,now,final=False):
        """One 09:45 preview and 10:00 final broad screen; no repeated universe scans."""
        now=now.astimezone(IST)
        date=now.date().isoformat()
        if self._shortlist_date!=date:
            self._shortlist_date=date
            self._shortlist_finalized=False
            self._shortlist=[]
            self._shortlist_up=[]
            self._shortlist_down=[]
            self._preview_buy=[]
            self._preview_sell=[]
        if self._shortlist_finalized:
            return dict(status='ALREADY FINALIZED',shortlist_size=len(self._shortlist))
        universe=self._stock_list()
        mode='CONFIGURED_UNIVERSE_FALLBACK'
        breadth_count=0
        if hasattr(self.broker,'market_quotes') and not WATCHLIST:
            all_stocks=[x for x in self.instruments() if x.get('kind')=='stock']
            try:quotes=self.broker.market_quotes(all_stocks[:500],now)
            except (BrokerUnavailable,ValueError,TypeError):quotes={}
            if quotes:
                breadth_count=len(quotes)
                valid=[x for x in all_stocks if str(x.get('id')) in quotes]
                gainers=sorted(valid,key=lambda x:quotes[str(x['id'])]['change_pct'],reverse=True)
                losers=sorted(valid,key=lambda x:quotes[str(x['id'])]['change_pct'])
                picks={}
                each=max(1,MAX_SYMBOLS//2)
                for x in gainers[:each]+losers[:each]:
                    picks[str(x['id'])]=x
                # Reserve part of the deep-analysis universe for symbols
                # with a verified sector mapping. Otherwise the strongest
                # quote movers may all be ineligible for relative-strength gates.
                mapped=_sector_map()
                mapped_stocks=[x for x in valid if
                    _norm(x['symbol']) in mapped or _norm(x.get('ticker','')) in mapped]
                reserve=max(1,min(len(mapped_stocks),MAX_SYMBOLS//3))
                for x in mapped_stocks[:reserve]:
                    picks[str(x['id'])]=x
                ranked=list(picks.values())
                # If we exceeded the deep cap, keep the mapped reserve and the
                # strongest movers rather than blindly trimming a dict.
                if len(ranked)>MAX_SYMBOLS:
                    ranked= mapped_stocks[:reserve]+[
                        x for x in ranked if x not in mapped_stocks[:reserve]][:MAX_SYMBOLS-reserve]
                universe=ranked[:MAX_SYMBOLS]
                mode='BATCHED_DHAN_QUOTE_PRESELECTION'
        ranked_up=[];ranked_down=[];available=0
        stale=0;missing_structure=0;errors=0
        for item in universe:
            try:
                candles=self.broker.history(item,now,minutes=5)
                if not recent_frame(candles,now,5,20):
                    stale+=1
                    continue
                score=advanced_smc.rank_early(candles,now)
                if score is None:
                    missing_structure+=1
                    continue
                available+=1
                # Discovery is a *watchlist* rather than a signal: favor
                # directional strength even before the breakout itself.
                # Strict >=2x RVOL/BOS/MTF are reserved for subsequent signals.
                change=score.get('session_change_pct',0)
                score['session_change_pct']=change
                if change>0 or score['up_breakout']:
                    ranked_up.append((score['up_score']+max(0,change)*8,
                                      score['rvol'],item,score))
                if change<0 or score['down_breakdown']:
                    ranked_down.append((score['down_score']+max(0,-change)*8,
                                        score['rvol'],item,score))
            except (BrokerUnavailable,ValueError,KeyError,TypeError):
                errors+=1
        ranked_up.sort(key=lambda x:(x[0],x[1]),reverse=True)
        ranked_down.sort(key=lambda x:(x[0],x[1]),reverse=True)
        self._shortlist_up=[x[2] for x in ranked_up[:8]]
        self._shortlist_down=[x[2] for x in ranked_down[:8]]
        chosen={str(x['id']):x for x in self._shortlist_up+self._shortlist_down}
        self._shortlist=list(chosen.values())
        self._discovery_scanned=len(universe)
        self._discovery_data_assessed=available
        self._discovery_stale=stale
        self._discovery_errors=errors
        self._discovery_missing_structure=missing_structure
        self._discovery_mode=mode
        self._breadth_quotes=breadth_count
        self._shortlist_finalized=bool(final)
        preview=lambda rows,side:[dict(symbol=x[2]['symbol'],rvol=x[3]['rvol'],
             ranking_score=round(x[0],1),direction=side,data_asof=x[3]['data_asof'],
             session_change_pct=x[3]['session_change_pct'],
             confirmed_break=bool(x[3]['up_breakout'] if side=='BUY' else x[3]['down_breakdown']),
             status='EARLY WATCH — NOT A TRADE') for x in rows[:8]]
        self._preview_buy=preview(ranked_up,'BUY')
        self._preview_sell=preview(ranked_down,'SELL')
        data=dict(status='FINAL SHORTLIST LOCKED — AWAITING 5m/15m/60m CONFIRMATION'
                   if final else '09:45 PRELIMINARY WATCHLIST — NOT TRADE SIGNALS',
                  signals=[],buy_signals=[],sell_signals=[],
                  preview_buy=list(self._preview_buy),
                  preview_sell=list(self._preview_sell),
                  scanned=len(universe),data_assessed=available,
                  discovery_mode=mode,breadth_quotes=breadth_count,
                  stale_data=stale,missing_structure=missing_structure,
                  unavailable_count=errors,
                  shortlist_size=len(self._shortlist),shortlist_finalized=bool(final),
                  shortlist_symbols=[x['symbol'] for x in self._shortlist],
                  note='Discovery ranks directional watch candidates, not confirmed breakouts. '+ 
                       'Dhan missing/stale bars are reported separately. No executable calls at 09:45. '+ 
                       'Later scans monitor only locked symbols.')
        self._update('intraday',data,now)
        return data

    def scan_intraday(self,now):
        """Exact cash daily + 15m momentum screen; monitor only 10:00 shortlist.

        No SMC/BOS/NIFTY/sector gate is silently added to the user's 11
        specified query conditions. Missing/old data fails closed.
        """
        now=now.astimezone(IST)
        date=now.date().isoformat()
        if self._shortlist_date!=date or not self._shortlist_finalized:
            data=dict(status='WAITING FOR FINAL 10:00 SHORTLIST',
                      signals=[],buy_signals=[],sell_signals=[],
                      preview_buy=list(self._preview_buy) if self._shortlist_date==date else [],
                      preview_sell=list(self._preview_sell) if self._shortlist_date==date else [],
                      scanned=0,shortlisted=0,shortlist_size=0,shortlist_finalized=False,
                      data_assessed=0,unavailable_count=0,stale_data=0,
                      missing_sector=0,rules_not_met=0,qualified_buy=0,qualified_sell=0,
                      note='Monitoring does not repeat the full-universe discovery.')
            self._update('intraday',data,now)
            return data
        selected=list(self._shortlist)
        stats=dict(scanned=len(selected),universe_scanned_at_discovery=self._discovery_scanned,
                   discovery_data_assessed=self._discovery_data_assessed,
                   discovery_stale=self._discovery_stale,
                   discovery_errors=self._discovery_errors,
                   discovery_missing_structure=self._discovery_missing_structure,
                   shortlisted=len(selected),data_assessed=0,unavailable_count=0,
                   stale_data=0,missing_sector=0,rules_not_met=0,
                   missing_daily=0,missing_15m=0,daily_rules_failed=0,
                   fifteen_rules_failed=0)
        buy=[];sell=[];risk_rejected=0
        # Dhan's prior daily bars are immutable during the session. Cache
        # once by symbol/day; never refetch all 100 days every 5 minutes.
        self._intraday_daily_cache={
           k:v for k,v in self._intraday_daily_cache.items() if k[0]==date
        }
        depths={}
        if hasattr(self.broker,'depth_snapshots'):
            try:depths=self.broker.depth_snapshots(selected,now)
            except (BrokerUnavailable,ValueError,TypeError):depths={}
        for item in selected:
            try:
                five=self.broker.history(item,now,minutes=5,lookback_days=8)
                if not recent_frame(five,now,5,20):
                    stats['stale_data']+=1
                    continue
                stats['data_assessed']+=1
                key=(date,str(item['segment']),str(item['id']))
                prior_daily=self._intraday_daily_cache.get(key)
                if prior_daily is None:
                    prior_daily=self.broker.daily(item,now,days=100)
                    if prior_daily is not None and len(prior_daily)>=20:
                        self._intraday_daily_cache[key]=prior_daily
                if prior_daily is None or len(prior_daily)<20:
                    stats['missing_daily']+=1
                    continue
                # Cheap daily gate before requesting costly HTF history.
                passes=[]
                for side in ('BUY','SELL'):
                    match=momentum_query.daily_gate(five,prior_daily,now,side)
                    if match and match['pass_all']:
                        passes.append(side)
                if not passes:
                    stats['daily_rules_failed']+=1
                    stats['rules_not_met']+=1
                    continue
                fifteen=self.broker.history(item,now,minutes=15,lookback_days=12)
                if not recent_frame(fifteen,now,15,35):
                    stats['missing_15m']+=1
                    continue
                qualified=False
                for side in passes:
                    m15=momentum_query.fifteen_gate(fifteen,now,side)
                    if not m15 or not m15['pass_all']:
                        stats['fifteen_rules_failed']+=1
                        continue
                    raw=depths.get(str(item['id'])) if isinstance(depths,dict) else None
                    flow=('RESTING BID/ASK DEPTH PROXY — NOT EXECUTED DELTA'
                          if raw and raw.get('verified') else
                          'NOT VERIFIED — candle volume is not aggressor order flow')
                    result=momentum_query.candidate(
                        five,prior_daily,fifteen,item['symbol'],now,side,flow)
                    if not result:continue
                    result=ai_rank.assess(result,five,fifteen,raw)
                    if not result:
                        risk_rejected+=1
                        continue
                    result.update(instrument_id=item['id'],segment=item['segment'],
                                  instrument_type=item['instrument'],
                                  quote_freshness='COMPLETED 5m+15m INPUTS; PROVISIONAL DAILY',
                                  data_asof=five.index[-1].isoformat(),
                                  backtest_status='UNVALIDATED')
                    self.journal.record(result)
                    (buy if side=='BUY' else sell).append(result)
                    qualified=True
                if not qualified:stats['rules_not_met']+=1
            except (BrokerUnavailable,ValueError,KeyError,TypeError,IndexError):
                stats['unavailable_count']+=1
        buy=ai_rank.top_ten(buy)
        sell=ai_rank.top_ten(sell)
        top10=ai_rank.top_ten(buy+sell)
        status=('NO ELIGIBLE SHORTLIST — SEE DISCOVERY DIAGNOSTICS'
                if not selected else 'DAILY + 15m MOMENTUM QUERY SCAN COMPLETE — RESEARCH ONLY')
        data=dict(status=status,signals=buy+sell,
                  ai_top10=top10,ai_top10_count=len(top10),
                  buy_signals=buy,sell_signals=sell,
                  ranking_model=ai_rank.VERSION,
                  ranking_label='Explainable AI-ready heuristic; not a trained predictive model',
                  risk_rejected=risk_rejected,
                  preview_buy=list(self._preview_buy),preview_sell=list(self._preview_sell),
                  shortlist_symbols=[x['symbol'] for x in selected],
                  discovery_mode=self._discovery_mode,breadth_quotes=self._breadth_quotes,
                  qualified_buy=len(buy),qualified_sell=len(sell),**stats,
                  shortlist_finalized=True,
                  daily_candle_status='PROVISIONAL current-session OHLCV built from completed 5m candles',
                  query_rules='8 DAILY + 3 COMPLETED 15m MUST ALL PASS',
                  note='Top 10 are ranked across BUY and SELL using explainable evidence weights; not an AI win probability. All 11 momentum rules must pass first. Entry is a conditional 5m breakout/breakdown trigger; stop uses ATR and 3-bar structure, rejecting excessive risk. Running daily RSI and volume are provisional; no broker fills.')
        self._update('intraday',data,now)
        return data

    def scan_btst(self,now):
        _,sectors=self._context();mapping=_sector_map();picks=[];skipped=0
        if self._shortlist_date!=now.date().isoformat() or not self._shortlist_finalized:
            data=dict(signals=[],status='BTST WAITING FOR LOCKED 10:00 SHORTLIST',
                      scanned=0,blocked=0)
            self._update('btst',data,now)
            return data
        stocks=list(self._shortlist)
        depth_snapshots={}
        if hasattr(self.broker,'depth_snapshots'):
            try:depth_snapshots=self.broker.depth_snapshots(stocks,now)
            except (BrokerUnavailable,ValueError,TypeError):pass
        path=os.getenv('INSIGHTS_LICENSED_DELIVERY_FILE','')
        try:delivery=json.loads(Path(path).read_text('utf-8')) if path else {}
        except (OSError,ValueError,TypeError):delivery={}
        current=delivery.get('date')==now.date().isoformat()
        for item in stocks:
            sec=sectors.get(mapping.get(_norm(item['symbol']),mapping.get(_norm(item.get('ticker','')),'')))
            vals=(delivery.get('values') or {})
            dp=vals.get(item['symbol'],vals.get(item.get('ticker',''))) if current else None
            if not sec or not recent_context(sec,now) or dp is None:
                skipped+=1
                continue
            try:
                f=self.broker.history(item,now,minutes=5,lookback_days=50)
                if not recent_frame(f,now,5,20):
                    skipped+=1
                    continue
                daily=self.broker.daily(item,now,days=120)
                h15=self.broker.history(item,now,minutes=15,lookback_days=12)
                h60=self.broker.history(item,now,minutes=60,lookback_days=30)
                if not recent_frame(h15,now,15,35) or not advanced_smc.btst_confirm(h15,h60,daily,now):
                    skipped+=1
                    continue
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
                    depth=depth_snapshots.get(str(item['id'])) if depth_snapshots else None
                    ratio=depth.get('bid_ask_ratio') if depth and depth.get('verified') else None
                    if ratio is not None and ratio<.83:
                        skipped+=1  # resting depth contradicts a long-side BTST scenario
                        continue
                    signal.update(backtest_status='UNVALIDATED',instrument_id=item['id'],
                        segment=item['segment'],instrument_type=item['instrument'],
                        mtf={'15m':'UP','60m':'UP','Daily':'UP','Weekly':'UP'},
                        order_flow_proxy='Resting five-level bid/ask depth — NOT executed trade delta'
                            if ratio is not None else 'UNAVAILABLE; dated delivery + matched-time volume only',
                        order_flow_ratio=ratio,quote_freshness='COMPLETED CASH CANDLES')
                    self.journal.record(signal);picks.append(signal)
            except (BrokerUnavailable,ValueError,KeyError):skipped+=1
        picks.sort(key=lambda x:x['confidence'],reverse=True)
        status='RESEARCH ONLY — BACKTEST VALIDATION REQUIRED' if picks else 'NO QUALIFIED BTST: requires Dhan matched-time history + licensed dated delivery data'
        data=dict(signals=picks[:10],status=status,scanned=len(stocks),blocked=skipped,
                  shortlisted=len(stocks),mtf='15m+60m+Daily+completed Weekly',
                  order_flow_proxy='Relative volume/delivery; no true transaction delta')
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
        candles=[];mtf={};price_asof=None
        try:
            f=self.broker.history(item,now,minutes=5)
            price_asof=f.index[-1].isoformat()
            mtf['5m']=advanced_smc.trend(f)
            candles=[dict(time=int(t.timestamp()),open=float(r.open),high=float(r.high),low=float(r.low),close=float(r.close)) for t,r in f.tail(120).iterrows()]
            for interval,days,key in ((15,12,'15m'),(60,30,'60m')):
                h=self.broker.history(item,now,minutes=interval,lookback_days=days)
                mtf[key]=advanced_smc.trend(h)
        except (BrokerUnavailable,ValueError,KeyError):pass
        market_depth={'status':'UNAVAILABLE — RESTING DEPTH NOT VERIFIED'}
        if is_market_session(now,_holiday_set()) and hasattr(self.broker,'depth_snapshots'):
            try:
                ds=self.broker.depth_snapshots([item],now).get(str(item['id']))
                if ds and ds.get('verified'):
                    market_depth={'status':'VERIFIED RESTING BOOK SNAPSHOT — NOT EXECUTED DELTA',
                                  'bid_ask_ratio':ds['bid_ask_ratio'],
                                  'last_trade_time':ds.get('last_trade_time')}
            except (BrokerUnavailable,ValueError,KeyError,TypeError):pass
        return dict(symbol=item['symbol'],expiry=selected,expiries=valid[:15],spot=chain.get('last_price'),candles=candles,
             price_asof=price_asof,mtf=mtf,market_depth=market_depth,
             order_flow_proxy='OPTION OI CHANGES AND RESTING BOOK DEPTH; NOT TAPE DELTA',
             bias=bias,metrics=m,plan=plan,status='RESEARCH ONLY — CONTRACT QUOTE FRESHNESS NOT VERIFIED',note=note,disclaimer=DISCLAIMER)

    def scan_index_options(self,now):
        d=self.snapshot('dashboard');indices=d.get('indices',[]);signals=[]
        for idx in indices:
            if _norm(idx['symbol']) not in ('NIFTY','NIFTY50','BANKNIFTY','NIFTYBANK','SENSEX') or idx['bias'] not in ('Uptrend','Downtrend') or not recent_context(idx,now):
                continue
            try:
                item=self._lookup(idx['symbol'])
                if item is None:continue
                five=self.broker.history(item,now,minutes=5,lookback_days=8)
                if not recent_frame(five,now,5,20):continue
                smc=advanced_smc.structure(five,now)
                if not smc.get('available'):continue
                # Cash indices may have zero/unavailable reported volume.
                # Never use zero index volume as proof of weak flow.
                # Option-chain OI/PCR supplies a separate positioning proxy.
                if smc['rvol']>0 and smc['rvol']<1.5:continue
                if idx['bias']=='Uptrend' and not smc['up_breakout']:continue
                if idx['bias']=='Downtrend' and not smc['down_breakdown']:continue
                h15=self.broker.history(item,now,minutes=15,lookback_days=12)
                h60=self.broker.history(item,now,minutes=60,lookback_days=30)
                expected='UP' if idx['bias']=='Uptrend' else 'DOWN'
                if advanced_smc.trend(h15)!=expected or advanced_smc.trend(h60)!=expected:continue
                exps=self.broker.expiry_list(item)
                expiry=next((x for x in sorted(exps) if x>=now.date().isoformat()),None)
                if not expiry:continue
                p=options.option_plan(self.broker.option_chain(item,expiry),idx['symbol'],idx['bias'],expiry,now)
                if p:
                    p.update(backtest_status='UNVALIDATED',
                             status='HYPOTHETICAL — OPTION QUOTE AGE NOT VERIFIED',
                             instrument_id=p['security_id'],
                             segment='NSE_FNO' if _norm(idx['symbol'])!='SENSEX' else 'BSE_FNO',
                             instrument_type='OPTIDX',quote_freshness='NOT VERIFIED',
                             research_only=True,mtf={'5m':idx['bias'],'15m':expected,'60m':expected},
                             order_flow_proxy='OPTION CHAIN OI / PCR — POSITIONING ONLY',
                             smc=dict(bos_up=smc['bos_up'],bos_down=smc['bos_down'],
                                 choch_up=smc['choch_up'],choch_down=smc['choch_down'],
                                 fvg_up=smc['fvg_up'],fvg_down=smc['fvg_down'],
                                 rvol=smc['rvol']),data_asof=idx.get('asof'))
                    signals.append(p)
                    # Never journal a hypothetical premium price as an observed signal.
            except (ValueError,BrokerUnavailable,KeyError):continue
        phase='PRELIMINARY 09:45' if (now.hour,now.minute)<(10,0) else 'FINAL 10:00'
        self._update('index-options',dict(signals=signals,
              status=phase+' — RESEARCH ONLY (OPTION QUOTES UNVERIFIED)' if signals else phase+' — NO QUALIFIED INDEX OPTION SETUPS',
              phase=phase,scanned=len(indices),qualified=len(signals),mtf='5m+15m+60m',
              note='Rechecked every 5 minutes. Index direction requires 5m/15m/60m; index volume may be unavailable. Option OI/PCR are positioning proxies; premium age unverified; no trades placed'),now)
        return signals

    def scan_fo(self,now):
        signals=[];unavailable=0
        selected=(list(self._shortlist) if self._shortlist_date==now.date().isoformat()
                  else [])
        for item in selected[:10]:
            future=item.get('future')
            if not future:unavailable+=1;continue
            try:
                f=self.broker.history(future,now,minutes=15,lookback_days=8,oi=True)
                if not recent_frame(f,now,15,35):
                    unavailable+=1
                    continue
                s=futures.buildup(f,item['symbol'],now)
                if not s:continue
                five=self.broker.history(item,now,minutes=5,lookback_days=8)
                if not recent_frame(five,now,5,20):continue
                smc=advanced_smc.structure(five,now)
                if not smc.get('available') or smc['rvol']<1.5:continue
                if s['direction']=='CE' and not smc['up_breakout']:continue
                if s['direction']=='PE' and not smc['down_breakdown']:continue
                h15=self.broker.history(item,now,minutes=15,lookback_days=12)
                h60=self.broker.history(item,now,minutes=60,lookback_days=30)
                expected='UP' if s['direction']=='CE' else 'DOWN'
                if advanced_smc.trend(h15)!=expected or advanced_smc.trend(h60)!=expected:continue
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
                   instrument_type='OPTSTK',quote_freshness='NOT VERIFIED',
                   research_only=True,mtf={'5m':s['direction'],'15m':expected,'60m':expected},
                   smc=dict(bos_up=smc['bos_up'],bos_down=smc['bos_down'],
                            choch_up=smc['choch_up'],choch_down=smc['choch_down'],
                            fvg_up=smc['fvg_up'],fvg_down=smc['fvg_down'],rvol=smc['rvol']),
                   order_flow_proxy='FUTURES OI BUILDUP + CHAIN OI; NOT TRADE DELTA')
                # No journal record: option entry premiums are not timestamp-verified.
                signals.append(plan)
            except (BrokerUnavailable,ValueError,KeyError):unavailable+=1
        phase='PRELIMINARY 09:45' if (now.hour,now.minute)<(10,0) else 'FINAL 10:00'
        self._update('fo-stocks',dict(signals=signals,
              status=phase+' — RESEARCH ONLY (PREMIUM FRESHNESS UNKNOWN)' if signals else phase+' — NO QUALIFIED FUTURES/OI SETUPS',
              phase=phase,scanned=len(selected[:10]),shortlisted=len(selected),
              unavailable_count=unavailable,qualified=len(signals),mtf='15m+60m+Futures OI',
              note='Rechecked every 5 minutes against locked stock shortlist. Futures OI and valid option chain mandatory; option premium is hypothetical'),now)
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

    @staticmethod
    def _dated_research_bundle(environment_name):
        """Read only explicitly configured attributable local datasets."""
        name=os.getenv(environment_name,'')
        if not name:return None
        try:
            with Path(name).open(encoding='utf-8') as stream:
                source=json.load(stream)
            return source if isinstance(source,dict) else None
        except (OSError,ValueError,TypeError):
            return None

    def scan_longterm(self,now):
        """Daily off-hours research scan, never a 5-minute intraday job.

        Separate from the 10:00 locked shortlist. Includes configured F&O
        universe, and if a watchlist is provided, respects its explicit limit.
        """
        now=now.astimezone(IST)
        all_stocks=(self.broker.longterm_instruments()
                    if hasattr(self.broker,'longterm_instruments')
                    else [x for x in self.instruments() if x.get('kind')=='stock'])
        if WATCHLIST:
            selected={_norm(v) for v in WATCHLIST}
            all_stocks=[x for x in all_stocks if
                _norm(x['symbol']) in selected or _norm(x.get('ticker','')) in selected]
        # Separate limit from intraday's 30-stock deep analysis cap.
        # The available master may be only the F&O subset. Do not claim
        # comprehensive NSE/BSE coverage unless master supports that.
        try:maximum=max(1,min(500,int(os.getenv('INSIGHTS_LONGTERM_MAX_SYMBOLS','80'))))
        except (ValueError,TypeError):maximum=80
        fundamentals=self._dated_research_bundle('INSIGHTS_FUNDAMENTALS_FILE')
        funding_names=({_norm(k) for k in (fundamentals.get('symbols') or {})}
                       if isinstance(fundamentals,dict) else set())
        priority=lambda item:(
            _norm(item['symbol']) not in funding_names,
            _norm(item['symbol']),str(item['id']))
        nse=sorted((x for x in all_stocks if x.get('segment')=='NSE_EQ'),key=priority)
        bse=sorted((x for x in all_stocks if x.get('segment')=='BSE_EQ'),key=priority)
        if nse and bse and not WATCHLIST:
            nse_quota=max(1,round(maximum*.7))
            bse_quota=maximum-nse_quota
            selected=nse[:nse_quota]+bse[:bse_quota]
            extra=[x for x in nse[nse_quota:]+bse[bse_quota:] if x not in selected]
            universe=(selected+extra)[:maximum]
        else:
            universe=sorted(all_stocks,key=priority)[:maximum]
        surveillance=self._dated_research_bundle('INSIGHTS_SURVEILLANCE_FILE')
        # NIFTY 500 relative strength ranks must be independently sourced.
        rank_source=self._dated_research_bundle('INSIGHTS_RS_RANK_FILE')
        rank_rows=rank_source.get('ranks',{}) if isinstance(rank_source,dict) and str(rank_source.get('source','')).strip() else {}
        rank_date=rank_source.get('asof') if isinstance(rank_source,dict) else None
        if rank_date:
            try:
                age=(now.date()-datetime.strptime(rank_date,'%Y-%m-%d').date()).days
                if age<0 or age>45:rank_rows={}
            except (ValueError,TypeError):rank_rows={}
        swing_rows=[];multi_rows=[]
        failures=0;insufficient=0
        for item in universe:
            try:
                # At least 20 fully completed months for EMA20 and 300
                # completed sessions for 200-day/52w templates.
                daily=self.broker.daily(item,now,days=1300)
                if daily is None or len(daily)<260:
                    insufficient+=1
                    continue
                swing_rows.extend(swing.scan(daily,item['symbol'],now))
                rank=rank_rows.get(item['symbol']) if isinstance(rank_rows,dict) else None
                result=multibagger.evaluate(
                    daily,item['symbol'],daily.index[-1].date().isoformat(),
                    fundamentals=fundamentals,surveillance=surveillance,rs_rank=rank)
                if result is not None:multi_rows.append(result)
            except (BrokerUnavailable,ValueError,KeyError,TypeError,IndexError):
                failures+=1
        swing_rows.sort(key=lambda row:(
            -row['risk_reward'],-row['trend_strength'],
            -(row['volume_ratio'] if row['volume_ratio'] is not None else 0),
            row['symbol']))
        multi_rows.sort(key=lambda row:(-row['score'],-row['verified_count'],row['symbol']))
        meta=dict(universe=len(universe),available_instrument_master=len(all_stocks),
                  limited_universe=len(all_stocks)>len(universe),
                  missing_or_short_history=insufficient,
                  unavailable_count=failures,asof=now.isoformat(),
                  note='Completed daily candles only; no live orders or fill assumptions.')
        self._update('swing-trades',dict(
            signals=swing_rows[:100],
            status='DAILY SWING RESEARCH COMPLETE',
            **meta),now)
        self._update('multibagger',dict(
            candidates=multi_rows[:100],
            status='COMPLETED-CANDLE MULTIBAGGER RESEARCH; NOT A RETURN FORECAST',
            fundamentals_source='LOCAL DATED ATTRIBUTABLE FILE' if fundamentals else 'UNVERIFIED',
            surveillance_source='LOCAL DATED ATTRIBUTABLE FILE' if surveillance else 'UNVERIFIED',
            rs_rank_source='LOCAL DATED REFERENCE' if rank_rows else 'UNVERIFIED',
            available_eligibility=sum(row['eligible'] for row in multi_rows),
            **meta),now)
        return dict(swing_count=len(swing_rows),multibagger_count=len(multi_rows),
                    unavailable_count=failures,insufficient_history=insufficient)

    def run_due(self,now=None):
        now=now or datetime.now(IST)
        calendar=_holiday_set()
        local=now.astimezone(IST)
        # Reuse the central exchange-session/holiday guard, including the
        # built-in known closures. The off-hours window alone must never
        # bypass an exchange holiday excluded from a user-provided calendar.
        regular_session=is_market_session(local.replace(hour=15,minute=20,second=0,microsecond=0),calendar)
        after_close=(regular_session
                     and (15,40)<=(local.hour,local.minute)<=(18,0))
        if not is_market_session(now,calendar) and not after_close:
            return dict(status='BLOCKED — holiday calendar missing, weekend or outside trading hours')
        if not self._job_lock.acquire(blocking=False):
            return dict(status='SCAN ALREADY RUNNING')
        if after_close:
            try:
                key=(local.date().isoformat(),'longterm-daily')
                if key in self._done:return dict(status='DAILY LONGTERM ALREADY COMPLETE')
                result=self.scan_longterm(local)
                self._done.add(key)
                return dict(status='DAILY LONGTERM COMPLETE',**result)
            except (BrokerUnavailable,ValueError,KeyError,TypeError) as exc:
                with self._lock:self._last_error='longterm: '+str(exc)[:160]
                return dict(status='DAILY LONGTERM UNAVAILABLE')
            finally:
                self._job_lock.release()
        completed=[]
        try:
            date=now.date().isoformat()
            # Broad stock discovery is ONLY at ~09:45 and ~10:00. Subsequent
            # monitoring only uses the locked shortlist.
            jobs=[
                ('dashboard',(9,20),self.dashboard),
                ('shortlist-preview',(9,45),lambda stamp:self.discover_shortlist(stamp,final=False)),
                ('index-options-preview',(9,45),self.scan_index_options),
                ('fo-stocks-preview',(9,45),self.scan_fo),
                ('shortlist-final',(10,0),lambda stamp:self.discover_shortlist(stamp,final=True)),
                ('index-options',(10,0),self.scan_index_options),
                ('fo-stocks',(10,0),self.scan_fo),
                ('intraday',(10,5),self.scan_intraday),
                ('btst',(15,0),self.scan_btst)
            ]
            for name,clock,job in jobs:
                key=(date,name)
                if (now.hour,now.minute)<clock or key in self._done:
                    continue
                # A late startup must not replay a fictitious 09:45 preview
                # and then repeat the full scan at 10:00.
                if name.endswith('-preview') and (now.hour,now.minute)>=(10,0):
                    self._done.add(key)
                    continue
                try:
                    job(now)
                    completed.append(name)
                    self._done.add(key)
                except (BrokerUnavailable,ValueError,KeyError,TypeError) as exc:
                    with self._lock:
                        self._last_error=f'{name}: {str(exc)[:160]}'
            minute=now.hour*60+now.minute
            if minute%5==0:
                key=(date,'dashboard-refresh',minute//5)
                if key not in self._done:
                    if 'dashboard' not in completed:
                        try:
                            self.dashboard(now)
                            completed.append('dashboard-refresh')
                        except (BrokerUnavailable,ValueError,KeyError,TypeError) as exc:
                            with self._lock:self._last_error=f'dashboard: {str(exc)[:160]}'
                    self._done.add(key)
                # MTF intraday scoring only revisits symbols selected at 10:00.
                key=(date,'shortlist-monitor',minute//5)
                if minute>=10*60+5 and key not in self._done:
                    if 'intraday' not in completed:
                        try:
                            self.scan_intraday(now)
                            completed.append('shortlist-monitor')
                        except (BrokerUnavailable,ValueError,KeyError,TypeError) as exc:
                            with self._lock:self._last_error=f'intraday: {str(exc)[:160]}'
                    self._done.add(key)
                # Re-evaluate option setups on every completed five-minute
                # clock boundary after final discovery. No full stock-universe
                # sweep; index list is fixed and F&O uses the locked shortlist.
                # The common job lock serializes Dhan chain requests.
                if minute>=10*60+5:
                    for name,job in (
                        ('index-options-monitor',self.scan_index_options),
                        ('fo-stocks-monitor',self.scan_fo),
                    ):
                        key=(date,name,minute//5)
                        if key in self._done:
                            continue
                        try:
                            job(now)
                            completed.append(name)
                        except (BrokerUnavailable,ValueError,KeyError,TypeError) as exc:
                            with self._lock:
                                self._last_error=f'{name}: {str(exc)[:160]}'
                        else:
                            self._done.add(key)
                key=(date,'outcomes',minute//5)
                if key not in self._done:
                    try:self.reconcile_outcomes(now)
                    except (BrokerUnavailable,ValueError,KeyError,TypeError):pass
                    self._done.add(key)
            return dict(status='OK',completed=completed,
                        shortlist_count=len(self._shortlist),
                        shortlist_finalized=self._shortlist_finalized)
        finally:
            self._job_lock.release()

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
