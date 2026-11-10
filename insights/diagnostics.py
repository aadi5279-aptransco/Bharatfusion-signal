"""Read-only scanner readiness checks. No strategy scans or orders."""
from __future__ import annotations
import argparse,json
from datetime import datetime
from pathlib import Path
from insights.config import IST,WATCHLIST,MAX_SYMBOLS,is_market_session,_KNOWN_2026_NSE_CLOSURES

def report(service,now=None,probe=False):
    from insights.service import _holiday_set,_sector_map,_norm
    now=(now or datetime.now(IST)).astimezone(IST)
    day=now.date().isoformat()
    cal=_holiday_set()
    holiday=(now.year==2026 and day in _KNOWN_2026_NSE_CLOSURES)
    dash=service.snapshot('dashboard')
    result=dict(mode='READ_ONLY_PREFLIGHT',checked_at=now.isoformat(),
        calendar_configured=cal is not None,today_listed_as_holiday=(day in cal if cal is not None else None),
        known_exchange_holiday=holiday,market_session_now=is_market_session(now,cal),
        dhan_credentials_present=service.broker.configured(),broker_status=service.health()['status'],
        orders_enabled=False,dashboard_snapshot_asof=dash.get('data_asof'),
        dashboard_not_live=dash.get('not_live',True),
        cached_index_count=len(dash.get('indices',[])),
        cached_sector_count=len(dash.get('sectors',[])),mapped_sector_symbols=len(_sector_map()),
        watchlist_size_setting=len(WATCHLIST) if WATCHLIST else MAX_SYMBOLS,
        modules={k:dict(status=service.snapshot(k).get('status'),
                        last_scan=service.snapshot(k).get('updated_at'),
                        candidates=len(service.snapshot(k).get('signals',[])),
                        scanned=service.snapshot(k).get('scanned'),
                        unavailable_count=service.snapshot(k).get('unavailable_count'))
                 for k in ('intraday','btst','index-options','fo-stocks')},
        probes={},warnings=[],
        disclaimer='Read-only infrastructure check, NOT a backtest or trading signal; historical candles are not live.')
    if cal is None:result['warnings'].append('Holiday calendar missing or invalid; scheduled scans blocked')
    if holiday and cal is not None and day not in cal:
        result['warnings'].append('Exchange holiday missing from user calendar; built-in block active')
    if not service.broker.configured():result['warnings'].append('Dhan credentials not configured')
    if dash.get('not_live',True):result['warnings'].append('Dashboard historical or not loaded; no live signal')
    if not _sector_map():result['warnings'].append('Sector map missing; relative strength confirmation blocked')
    if not probe or not service.broker.configured():return result

    def test(name,fn):
        try:
            result['probes'][name]=dict(status='PASS',**fn())
        except Exception as exc:
            # Never print token-containing raw SDK error or response
            result['probes'][name]=dict(status='UNAVAILABLE',reason=type(exc).__name__,
               note='Check Dhan credentials, entitlement and instrument data locally')

    try:
        items=service.instruments()
    except Exception:
        result['probes']['instrument_master']=dict(status='UNAVAILABLE',reason='INSTRUMENT_MASTER_FAILED')
        return result
    result['probes']['instrument_master']=dict(status='PASS',count=len(items),
       index_count=sum(x.get('kind')=='index' for x in items),
       stock_count=sum(x.get('kind')=='stock' for x in items))

    def candles(item,minutes=5,oi=False):
        if item is None:raise ValueError('Unmapped instrument')
        f=service.broker.history(item,now=now,minutes=minutes,oi=oi)
        if f.empty:raise ValueError('Empty Dhan history')
        if oi and ('oi' not in f.columns or f['oi'].dropna().empty):
            raise ValueError('Missing futures OI')
        return dict(instrument=item['symbol'],completed_candles=len(f),
             last_candle=f.index[-1].isoformat(),
             historical_only=(not is_market_session(now,cal) or f.index[-1].date()!=now.date()),
             enough_for_ema200=len(f)>=201,
             **({'oi_available':True} if oi else {}))
    index=next((x for x in items if x.get('kind')=='index' and _norm(x['symbol']) in ('NIFTY','NIFTY50')),None)
    stock=next((x for x in items if x.get('kind')=='stock' and _norm(x['symbol'])=='RELIANCE'),None)
    if stock is None:stock=next((x for x in items if x.get('kind')=='stock'),None)
    test('nifty_5m',lambda:candles(index))
    test('stock_5m',lambda:candles(stock))
    def chain():
        if index is None:raise ValueError('No NIFTY mapping')
        expiries=service.broker.expiry_list(index)
        future=sorted(x for x in expiries if x>=day)
        if not future:raise ValueError('No current expiry')
        data=service.broker.option_chain(index,future[0])
        oc=data.get('oc',{}) if isinstance(data,dict) else {}
        if not oc:raise ValueError('Empty option chain')
        return dict(underlying=index['symbol'],expiry=future[0],
                    strike_count=len(oc),quote_freshness='NOT_VERIFIED')
    test('index_option_chain',chain)
    future=next((x['future'] for x in items if x.get('kind')=='stock' and x.get('future')),None)
    if future:test('futures_oi_15m',lambda:candles(future,minutes=15,oi=True))
    else:result['probes']['futures_oi_15m']=dict(status='UNAVAILABLE',reason='NO_FUTURES_MAPPED')
    return result

def main():
    parser=argparse.ArgumentParser(description='BharatSignal Dhan read-only preflight')
    parser.add_argument('--probe',action='store_true')
    args=parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=False)
    from insights.service import InsightsService
    print(json.dumps(report(InsightsService(),probe=args.probe),ensure_ascii=False,indent=2,default=str))

if __name__=='__main__':main()
