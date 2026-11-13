"""Read-only, cash-first Analyse view and batched gainers/losers choices."""
from __future__ import annotations
import re
import pandas as pd
from datetime import datetime
from insights.config import IST, is_market_session
from insights.brokers.dhan import BrokerUnavailable
from insights import analyse_engine
from insights.strategies import options


def choices(service, now, calendar):
    now=now.astimezone(IST)
    all_items=service.instruments()
    stocks=[x for x in all_items if x.get('kind')=='stock']
    indices=[dict(symbol=x['symbol'],kind='index') for x in all_items if x.get('kind')=='index']
    quotes={}
    if hasattr(service.broker,'market_quotes'):
        try:quotes=service.broker.market_quotes(stocks[:500],now)
        except (BrokerUnavailable,ValueError,KeyError,TypeError):quotes={}
    rows=[]
    for item in stocks:
        info=quotes.get(str(item.get('id')))
        if info is None:continue
        rows.append(dict(symbol=item['symbol'],change_pct=info['change_pct'],
            last_price=info.get('last_price'),volume=info.get('volume'),
            baseline_type=info.get('baseline_type','SESSION_OPEN'),
            fetched_at=info.get('fetched_at')))
    return dict(status='QUOTE MOVERS — NOT TRADE SIGNALS' if rows
                else 'MOVERS UNAVAILABLE; INDEX LIST STILL ACCESSIBLE',
        gainers=sorted((x for x in rows if x['change_pct']>0),
                       key=lambda x:-x['change_pct'])[:15],
        losers=sorted((x for x in rows if x['change_pct']<0),
                      key=lambda x:x['change_pct'])[:15],
        indices=indices,coverage=len(rows),universe=len(stocks),
        asof=now.isoformat(),stale=not is_market_session(now,calendar),
        note='Only Dhan-mapped instruments. Previous-close percentage change when supplied; otherwise a labelled session-open change. Not a complete NSE/BSE ranking.')


def analyse(service,symbol,now,expiry,calendar,normalize):
    now=now.astimezone(IST)
    if not symbol or len(symbol)>64 or not symbol.strip():
        raise ValueError('Invalid symbol')
    match=re.fullmatch(r'(.+?)\s+(\d+(?:\.\d+)?)\s+(CE|PE)',symbol.strip(),re.I)
    underlying=match.group(1) if match else symbol.strip()
    strike=float(match.group(2)) if match else None
    requested_side=match.group(3).upper() if match else None
    item=service._lookup(underlying)
    if item is None:raise ValueError('Symbol not found in Dhan instrument master')
    frames={};candles=[];history_errors=[]
    for period,days in ((5,10),(15,15),(60,40)):
        try:
            f=service.broker.history(item,now,minutes=period,lookback_days=days)
            frames[period]=f
            if period==5:
                candles=[dict(time=int(t.timestamp()),open=float(row.open),
                    high=float(row.high),low=float(row.low),close=float(row.close))
                    for t,row in f.tail(120).iterrows()]
        except (BrokerUnavailable,ValueError,KeyError,TypeError,IndexError):
            history_errors.append(str(period)+'m')
    depth=None
    if is_market_session(now,calendar) and hasattr(service.broker,'depth_snapshots'):
        try:depth=service.broker.depth_snapshots([item],now).get(str(item['id']))
        except (BrokerUnavailable,ValueError,KeyError,TypeError):depth=None
    selected=None;expiries=[];chain=None;metrics=None;plan=None
    chain_status='UNAVAILABLE — NO VERIFIED DERIVATIVE DATA'
    note='Cash/index analysis works without an option chain.'
    try:
        expiries=[x for x in sorted(service.broker.expiry_list(item))
                  if x>=now.date().isoformat()]
        if expiry and expiry not in expiries:raise ValueError('Expiry is not available')
        selected=expiry or (expiries[0] if expiries else None)
        if selected:
            chain=service.broker.option_chain(item,selected)
            metrics=options.chain_metrics(chain)
            chain_status='AVAILABLE — CONTRACT QUOTE AGE NOT VERIFIED'
        else:chain_status='NO FUTURE EXPIRY'
    except ValueError as exc:
        if expiry or requested_side:raise
        chain_status='UNAVAILABLE — '+str(exc)[:90]
    except (BrokerUnavailable,KeyError,TypeError):
        chain_status='UNAVAILABLE — OPTIONAL CHAIN FAILED'
    evidence=analyse_engine.evaluate(frames.get(5),frames.get(15),frames.get(60),
                   now,depth=depth,option_metrics=metrics)
    bias=evidence['bias']
    if chain and (bias in ('BULLISH','BEARISH') or requested_side):
        direction=('Uptrend' if bias=='BULLISH' else
                   'Downtrend' if bias=='BEARISH' else 'Sideways')
        try:
            plan=options.option_plan(chain,item['symbol'],direction,selected,now,
                        side_override=requested_side,requested_strike=strike)
        except ValueError as exc:note=str(exc)
    five=frames.get(5)
    return dict(symbol=item['symbol'],asset_type=item.get('kind'),
       expiry=selected,expiries=expiries[:15],metrics=metrics,plan=plan,
       spot=chain.get('last_price') if chain else (
           float(five.close.iloc[-1]) if five is not None else None),
       candles=candles,
       price_asof=five.index[-1].isoformat() if five is not None else None,
       chain_status=chain_status,analysis=evidence,
       market_depth=evidence.get('order_flow',{}),mtf=evidence.get('mtf',{}),
       gann_wave=evidence.get('gann_wave',{}),
       entry_plan=evidence.get('entry_plan'),
       bias=bias,probability_of_win=None,
       probability_status='UNAVAILABLE — NO CALIBRATED WALK-FORWARD MODEL',
       status=evidence['status'],history_errors=history_errors,
       note=note)
