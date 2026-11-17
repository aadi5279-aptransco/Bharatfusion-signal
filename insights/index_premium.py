"""ATM premium plans with independent direction, false-move checks and dated quotes."""
import math
import pandas as pd
from insights.config import IST,is_market_session
from insights.atm_recommendation import _strike_rows
from insights.smc_expert import completed,atr
from insights.advanced_smc import trend
from insights.strategies.options import chain_metrics


def positive(v):
    try:
        v=float(v)
        return v if math.isfinite(v) and v>0 else None
    except (TypeError,ValueError):return None


def direction_checks(five,h15,h60,watches,side,now,calendar=None):
    f=completed(five,now,5,minimum=25);m=completed(h15,now,15,minimum=25)
    try:h=completed(h60,now,60,minimum=25)
    except ValueError:
        from insights.premarket_followthrough import prior_session
        if not isinstance(h60,pd.DataFrame) or h60.empty or not isinstance(h60.index,pd.DatetimeIndex) or h60.index.tz is None:raise
        h=h60.copy();h.index=h.index.tz_convert(IST);h=h[h.index+pd.Timedelta(minutes=60)<=now]
        if h.empty or (now.hour,now.minute)>=(10,15) or h.index[-1].date()!=prior_session(now,calendar) or (h.index[-1].hour,h.index[-1].minute)<(14,15):raise
        h=completed(h,h.index[-1]+pd.Timedelta(minutes=60),60,minimum=25)
    expected='UP' if side=='CE' else 'DOWN';block=[];reasons=[]
    ready=[r for r in watches if r.get('state') in ('DIRECTION_READY','STRUCTURE_READY')]
    matching=[r for r in ready if r.get('side')==side]
    if not matching:block.append('No confirmed opening/red-bar/Fibonacci direction for '+side)
    if any(r.get('side') not in (None,side) for r in ready):block.append('Conflicting strategy directions — possible whipsaw')
    if trend(f)!=expected or trend(m)!=expected:block.append('5m and 15m trends do not confirm '+side)
    if trend(h) not in (expected,'MIXED','SIDEWAYS'):block.append('60m trend opposes the entry — reversal risk')
    x=f.iloc[-1];a=atr(f);span=float(x.high-x.low)
    wick=float(x.high-max(x.open,x.close)) if side=='CE' else float(min(x.open,x.close)-x.low)
    if span<=0 or abs(float(x.close-x.open))/span<.2:block.append('Indecision candle — wait for a directional close')
    if span>0 and wick/span>.5:block.append('Large rejection wick — potential false breakout')
    ema=float(f.close.ewm(span=9,adjust=False).mean().iloc[-1])
    if a<=0 or abs(float(x.close)-ema)>2.5*a:block.append('Price overextended from EMA9 — do not chase')
    # A ready red-bar watch already requires two closes; repeat the threshold
    # check here so a supplied watch cannot override a failed/returned breakout.
    for r in matching:
        level=r.get('trigger_ce' if side=='CE' else 'trigger_pe')
        if positive(level):
            closes=f.close.tail(2)
            if not ((closes>float(level)).all() if side=='CE' else (closes<float(level)).all()):
                block.append('Breakout failed to hold for two completed candles')
    reasons.extend(r.get('strategy','Confirmed structure')+': '+r.get('reason','Completed-candle confirmation') for r in matching)
    reasons.append('5m/15m trend agreement; 60m opposition and rejection-wick checks applied')
    if h.index[-1].date()!=now.date():reasons.append('60m context uses the prior completed session until today’s first hourly candle closes')
    return f,block,reasons


def quote_values(quote,now):
    if not isinstance(quote,dict):raise ValueError('ATM market quote unavailable')
    raw=quote.get('last_trade_time')
    if not raw:raise ValueError('ATM last-trade timestamp unavailable')
    try:
        t=pd.to_datetime(raw,dayfirst=True)
        t=t.tz_localize(IST) if t.tzinfo is None else t.tz_convert(IST)
        received=pd.Timestamp(quote.get('fetched_at') or now)
        if received.tzinfo is None or not 0<=(received-pd.Timestamp(now)).total_seconds()<=300:raise ValueError()
        age=(received-t).total_seconds()
        if t.date()!=now.date() or not 0<=age<=120:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('ATM last trade is stale or future dated') from None
    depth=quote.get('depth') or {}
    try:
        bid=positive(depth['buy'][0]['price']);ask=positive(depth['sell'][0]['price'])
        bq=positive(depth['buy'][0]['quantity']);aq=positive(depth['sell'][0]['quantity'])
    except (KeyError,IndexError,TypeError):raise ValueError('ATM two-sided market depth unavailable') from None
    if not all((bid,ask,bq,aq)) or bid>ask or (ask-bid)/ask>.02:raise ValueError('ATM spread exceeds 2% or depth is invalid')
    if not positive(quote.get('volume')):raise ValueError('ATM traded volume unavailable')
    return bid,ask,t.isoformat()


def assess(broker,item,five,watches,now,calendar):
    base=dict(underlying=item['symbol'],entry=None,sl=None,t1=None,t2=None,strike=None,expiry=None,
              level_basis='OPTION PREMIUM',research_only=True,probability_of_win=None,
              status='WAIT',reasons=[],warnings=[],blockers=[])
    rows=[dict(base,direction=side,reasons=[],warnings=[],blockers=[]) for side in ('CE','PE')]
    try:
        expiries=broker.expiry_list(item)
        expiry=next((str(x) for x in sorted(expiries) if str(x)>=now.date().isoformat()),None)
        if expiry is None:raise ValueError('No current mapped expiry')
        chain=broker.option_chain(item,expiry);spot=positive(chain.get('last_price'))
        strikes=_strike_rows(chain)
        if not spot or not strikes:raise ValueError('ATM underlying/strike data missing')
        strike,legs=min(strikes,key=lambda x:(abs(x[0]-spot),x[0]))
        metrics=chain_metrics(chain)
        h15=broker.history(item,now,minutes=15,lookback_days=12)
        h60=broker.history(item,now,minutes=60,lookback_days=30)
    except Exception as exc:
        for r in rows:r['blockers']=[str(exc)[:180] if isinstance(exc,ValueError) else 'Index chain or higher-timeframe data unavailable']
        return rows
    for r in rows:
        side=r['direction'];leg=legs.get(side.lower()) or {};sid=str(leg.get('security_id') or '')
        r.update(strike=strike,expiry=expiry,symbol=f"{item['symbol']} {strike:g} {side}",security_id=sid,
                 strategy='ATM premium · opening/red-bar/Fib confirmation',signal_at=now.isoformat())
        r['warnings']=['False moves remain possible; confirmation filters cannot guarantee success.',
                       'Premium targets use 1.5R / 2.5R; theta, IV and slippage can change the outcome.']
        if expiry==now.date().isoformat():r['warnings'].append('EXPIRY DAY — accelerated time decay and sharp premium reversals')
        if (positive(leg.get('implied_volatility')) or 0)>=25:r['warnings'].append('Elevated absolute IV — premium can fall if IV contracts')
        try:
            if not is_market_session(now,calendar):raise ValueError('Outside verified market session')
            f,block,reasons=direction_checks(five,h15,h60,watches,side,now,calendar)
            r['blockers'].extend(block);r['reasons']=reasons
            if abs(spot-f.close.iloc[-1])>max(2*atr(f),.005*spot):r['blockers'].append('Chain spot disagrees with completed underlying candles')
            if metrics['pcr']<.85 if side=='CE' else metrics['pcr']>1.15:r['blockers'].append('Option-chain PCR contradicts direction')
            if not sid.isdigit() or not positive(leg.get('oi')):r['blockers'].append('Mapped ATM security ID and positive OI required')
            if r['blockers']:continue
            contract=dict(id=sid,symbol=r['symbol'],segment='BSE_FNO' if item['symbol'].upper()=='SENSEX' else 'NSE_FNO',instrument='OPTIDX',kind='option')
            premium=completed(broker.history(contract,now,minutes=5,lookback_days=8),now,5,minimum=20)
            quotes=broker.market_quotes([contract],now)
            bid,entry,trade_at=quote_values(quotes.get(sid),now)
            a=atr(premium)
            if a<=0 or abs(entry-float(premium.close.iloc[-1]))>2*a:raise ValueError('ATM premium has moved too far from its completed candle — do not chase')
            stop=min(float(premium.low.tail(3).min()),entry-a);risk=entry-stop
            if stop<=0 or not .03<=risk/entry<=.35:raise ValueError('Structural option stop outside 3–35% research risk bounds')
            levels=dict(entry=round(entry,2),sl=round(stop,2),t1=round(entry+1.5*risk,2),t2=round(entry+2.5*risk,2))
            if not 0<levels['sl']<levels['entry']<levels['t1']<levels['t2']:raise ValueError('Rounded premium levels collapse risk distance')
            r.update(**levels,status='PREMIUM RESEARCH SETUP',bid=bid,spread_pct=round(100*(entry-bid)/entry,2),
                     quote_asof=trade_at,premium_candle_asof=premium.index[-1].isoformat(),rr=1.5,
                     quote_freshness='RECENT LAST TRADE; REST DEPTH SNAPSHOT — NOT A FILL',
                     instrument_id=sid,segment=contract['segment'],instrument_type='OPTIDX')
            r['reasons']+=['Entry is the selected ATM contract best ask, not its strike or index level.',
                           'SL uses that option’s ATR14 and latest three-candle low; targets are 1.5R and 2.5R.']
        except Exception as exc:r['blockers'].append(str(exc)[:180] if isinstance(exc,ValueError) else 'ATM premium history or dated quote unavailable')
    return rows
