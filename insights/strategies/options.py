"""Deterministic option-chain diagnostics and buy-premium scenario levels."""
from __future__ import annotations
import math
from datetime import date

NAME='OI confirmed index option'
VERSION='1.0'

def _number(x,default=0):
    try:
        v=float(x)
        return v if math.isfinite(v) else default
    except (ValueError,TypeError):return default


def chain_metrics(chain):
    oc=chain.get('oc',{})
    if not isinstance(oc,dict) or not oc:raise ValueError('Empty option chain')
    strikes=[]
    for k,legs in oc.items():
        try: strike=float(k)
        except (TypeError,ValueError):continue
        if not math.isfinite(strike) or strike<=0 or not isinstance(legs,dict):continue
        ce=legs.get('ce') or {};pe=legs.get('pe') or {}
        strikes.append(dict(strike=strike,ce_oi=_number(ce.get('oi')),pe_oi=_number(pe.get('oi')),
            ce_change=_number(ce.get('oi'))-_number(ce.get('previous_oi')),
            pe_change=_number(pe.get('oi'))-_number(pe.get('previous_oi')),
            ce_iv=_number(ce.get('implied_volatility'),None),pe_iv=_number(pe.get('implied_volatility'),None),
            ce=ce,pe=pe))
    if not strikes:raise ValueError('No valid strike data')
    strikes.sort(key=lambda x:x['strike'])
    call=sum(s['ce_oi'] for s in strikes);put=sum(s['pe_oi'] for s in strikes)
    if call<=0:raise ValueError('No call open interest')
    # Simplified open-interest-based expiration payoff, NOT a forecast.
    pain=min(strikes,key=lambda x:sum(s['ce_oi']*max(0,x['strike']-s['strike']) + s['pe_oi']*max(0,s['strike']-x['strike']) for s in strikes))['strike']
    support=max(strikes,key=lambda x:x['pe_oi'])['strike']
    resistance=max(strikes,key=lambda x:x['ce_oi'])['strike']
    return dict(pcr=round(put/call,3),max_pain=pain,oi_support=support,oi_resistance=resistance,
        call_oi=call,put_oi=put,call_change=sum(s['ce_change'] for s in strikes),put_change=sum(s['pe_change'] for s in strikes),
        iv_percentile=None,iv_percentile_note='IV percentile requires licensed historical IV snapshots; not inferred from one chain',
        strikes=[{k:v for k,v in s.items() if k not in ('ce','pe')} for s in strikes])


def option_plan(chain,symbol,bias,expiry,now,side_override=None,requested_strike=None):
    m=chain_metrics(chain);spot=_number(chain.get('last_price'))
    if spot<=0:raise ValueError('Missing underlying spot')
    side=side_override or ('CE' if bias=='Uptrend' else 'PE' if bias=='Downtrend' else None)
    if side not in ('CE','PE'):return None
    if side=='CE' and m['pcr']<0.85:return None
    if side=='PE' and m['pcr']>1.15:return None
    oc=chain['oc']
    if requested_strike is not None:
        s=next((x for x in m['strikes'] if abs(x['strike']-float(requested_strike))<.001),None)
        if s is None:raise ValueError('Requested strike does not exist in this expiry')
    else:s=min(m['strikes'],key=lambda x:abs(x['strike']-spot))
    leg=next((v[side.lower()] for k,v in oc.items() if k.replace('.','',1).isdigit() and float(k)==s['strike'] and isinstance(v.get(side.lower()),dict)),None)
    if not leg:raise ValueError('No mapped ATM option leg')
    ask=_number(leg.get('top_ask_price'));bid=_number(leg.get('top_bid_price'))
    if ask<=0 or bid<=0 or bid>ask or (ask-bid)/ask>.05 or _number(leg.get('volume'))<=0:raise ValueError('Option quote missing, illiquid, or spread >5%')
    # Scenario levels are premium-based BUY positions: both CE and PE rise when trade succeeds.
    # These levels are hypothetical until data freshness and backtesting are verified.
    risk=max(ask*.20,ask-bid)
    expiry_day=str(expiry)==str(now.date())
    iv=_number(leg.get('implied_volatility'))
    warnings=[]
    if expiry_day:warnings.append('Expiry-day theta decay can be extreme')
    if iv>=25:warnings.append('Elevated absolute IV; historical percentile unavailable')
    warnings.append('Option-chain quote age is unverified; research only')
    reasons=[f'{bias} index trend',f'PCR {m["pcr"]:.2f}',f'ATM strike {s["strike"]:g}',
        f'Best-ask premium {ask:.2f} with <=5% bid/ask spread']
    return dict(strategy=NAME,version=VERSION,symbol=f'{symbol} {s["strike"]:g} {side}',
       underlying=symbol,direction=side,strike=s['strike'],expiry=str(expiry),
       signal_at=now.isoformat(),entry=round(ask,2),sl=round(ask-risk,2),t1=round(ask+1.5*risk,2),
       t2=round(ask+2.5*risk,2),rr=1.5,confidence=65 if not warnings else 55,
       warnings=warnings,reasons=reasons,security_id=str(leg.get('security_id','')),iv=iv)
