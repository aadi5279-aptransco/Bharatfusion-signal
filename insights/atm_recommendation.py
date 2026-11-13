"""Read-only ATM CE/PE option assessment for the Analyse tab.

Never fabricates strikes or option prices. ATM means the listed strike
nearest to an observed underlying reference; expiry and identifiers are
taken from the Dhan chain. Premium entry/stop/targets are illustrative
scenarios derived from a valid two-sided quote, not executable orders or
calibrated win probabilities. A quote's receipt time is not a verified
exchange last-trade timestamp.
"""
from __future__ import annotations
import math
from datetime import datetime
import pandas as pd
from insights.config import IST, is_market_session
from insights.strategies import opening_redbar

VERSION="analyse-atm-v1"


def _positive(value):
    try:
        number=float(value)
        return number if math.isfinite(number) and number>0 else None
    except (TypeError,ValueError):return None


def _strike_rows(chain):
    if not isinstance(chain,dict) or not isinstance(chain.get("oc"),dict):
        return []
    result=[]
    for key,legs in chain["oc"].items():
        value=_positive(key)
        if value is None or not isinstance(legs,dict):continue
        result.append((value,legs))
    return sorted(result,key=lambda x:x[0])


def _direction(bias,five,now):
    """Qualified 5/15/60 breakout first; otherwise an unambiguous opening watch."""
    if bias=="BULLISH":return "CE","FULL_MTF_BULLISH"
    if bias=="BEARISH":return "PE","FULL_MTF_BEARISH"
    watches=[]
    if five is not None:
        try:watches=opening_redbar.evaluate(five,now)
        except (ValueError,TypeError,KeyError,IndexError):watches=[]
    ready={r.get("side") for r in watches if r.get("state")=="DIRECTION_READY"}
    if len(ready)==1:
        return next(iter(ready)),"TWO_COMPLETED_5M_CLOSES"
    if len(ready)>1:
        return None,"CONFLICTING_OPENING_SETUPS"
    return None,"NO_VERIFIED_DIRECTION"


def evaluate(chain,expiry,underlying,now,calendar,bias="UNAVAILABLE",
             five=None,requested_side=None):
    """Return strike details even when no directional trade scenario qualifies."""
    t=pd.Timestamp(now)
    empty=dict(status="UNAVAILABLE",direction=None,signal_source=None,
        underlying=underlying,expiry=expiry,atm_strike=None,atm_distance_pct=None,
        contract=None,entry=None,sl=None,t1=None,t2=None,rr=None,
        bid=None,ask=None,spread_pct=None,quote_freshness="NOT VERIFIED",
        research_only=True,probability_of_win=None,
        reason="Option chain unavailable or underlying spot missing",
        warning="No broker orders. Premium scenarios must be validated against live quotes.",
        version=VERSION)
    if t.tzinfo is None:return empty
    t=t.tz_convert(IST)
    rows=_strike_rows(chain)
    if not rows:return dict(empty,reason="No listed strikes in option chain")
    spot=_positive(chain.get("last_price")) if isinstance(chain,dict) else None
    # Use only an authentic current-session completed spot close if chain
    # omits its underlying last_price. Never fabricate a quote.
    if spot is None and five is not None and len(five)>0:
        last=five.index[-1]
        if last.date()==t.date() and 5<=(t-last).total_seconds()/60<=20:
            spot=_positive(five.close.iloc[-1])
    if spot is None:return dict(empty,reason="No positive underlying spot from verified-source history/chain")
    strike,legs=min(rows,key=lambda x:(abs(x[0]-spot),x[0]))
    base=dict(empty,atm_strike=strike,spot=round(spot,2),
              atm_distance_pct=round(100*abs(strike-spot)/spot,2),
              assessment_at=t.isoformat())
    inferred,source=_direction(bias,five,t)
    if requested_side in ("CE","PE"):
        # Explicit CE/PE search is allowed, but cannot masquerade as
        # a model-recommended trade when the independent bias disagrees.
        side=requested_side
        source=source if inferred==side else "USER_SELECTED_SIDE_NOT_CONFIRMED"
    else:side=inferred
    base.update(direction=side,signal_source=source)
    if side not in ("CE","PE"):
        return dict(base,status="WATCH — NO CLEAR CE/PE BIAS",
                    reason="No aligned completed-candle bullish/bearish direction. ATM strike shown for research only")
    leg=legs.get(side.lower())
    if not isinstance(leg,dict) or not leg:
        return dict(base,status="WATCH — NO LISTED ATM LEG",
                    reason="ATM "+side+" option contract missing from chain")
    sid=str(leg.get("security_id") or "").strip()
    contract=dict(underlying=underlying,expiry=str(expiry),strike=strike,
                  side=side,security_id=sid or None,
                  symbol=f"{underlying} {strike:g} {side}")
    base["contract"]=contract
    if not sid:
        return dict(base,status="WATCH — SECURITY ID UNAVAILABLE",
                    reason="Dhan chain has no mapped contract security ID")
    ask=_positive(leg.get("top_ask_price"))
    bid=_positive(leg.get("top_bid_price"))
    volume=_positive(leg.get("volume"))
    if ask is None or bid is None or bid>ask:
        return dict(base,status="WATCH — INVALID BID/ASK",
                    reason="A valid bid and ask are required for premium scenarios")
    spread=(ask-bid)/ask
    base.update(bid=round(bid,2),ask=round(ask,2),
                spread_pct=round(100*spread,2))
    if spread>.05 or volume is None:
        return dict(base,status="WATCH — WIDE SPREAD / ILLIQUID",
                    reason="Spread exceeds 5% or traded contract volume is unavailable")
    if source=="USER_SELECTED_SIDE_NOT_CONFIRMED":
        return dict(base,status="WATCH — MANUAL CE/PE UNCONFIRMED",
                    reason="Selected side contradicts or lacks independent spot confirmation")
    # The expiry may be displayed after close, but cannot be a live
    # recommendation. We label every scenario as hypothetical even during
    # market hours because Dhan chain leg quote timestamps are unverified.
    risk=round(max(.2*ask,ask-bid),2)
    if risk<=0 or ask-risk<=0:
        return dict(base,status="WATCH — INVALID PREMIUM STOP",
                    reason="Cannot derive a positive illustrative premium stop")
    levels=dict(entry=round(ask,2),sl=round(ask-risk,2),
                t1=round(ask+1.5*risk,2),
                t2=round(ask+2.5*risk,2),rr=1.5)
    session=is_market_session(t,calendar)
    status=("HYPOTHETICAL ATM PREMIUM SCENARIO — QUOTE AGE UNVERIFIED"
            if session else
            "HISTORICAL ATM PREMIUM SCENARIO — MARKET CLOSED")
    return dict(base,**levels,status=status,
        reason="Underlying "+source+"; listed ATM "+side+
               " with two-sided bid/ask; illustrative premium risk 20% of ask",
        note="Price levels are based on Dhan chain best ask, NOT verified fresh executable quotes. Do not use as order prices.",
        warning="Option buyer risk includes theta, IV, slippage and brokerage; no win probability established")
