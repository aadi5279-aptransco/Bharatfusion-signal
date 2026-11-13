"""Independent 14:30 -> 15:05 -> 15:20 BTST closing-strength research.

Uses completed NSE cash five-minute candles, previous *completed*
daily candles and a like-for-like prior-session volume baseline.
The 15:05 reference is NOT the official close or closing-auction result.
All planned entry/SL/T1/T2 levels refer to the cash underlying.
"""
from __future__ import annotations
import math
import pandas as pd

NAME="BTST Closing Strength · 14:30/15:05/15:20"
VERSION="btst-close-strength-v1"


def _no(status, reason):
    return dict(status=status,strategy=NAME,version=VERSION,
                direction="WATCH",entry=None,sl=None,t1=None,t2=None,
                reasons=[],blockers=[reason],checks={},confidence=None,
                probability_of_win=None,research_only=True)


def _num(x):
    try:
        v=float(x)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None


def _matched_volume(five,today,limit=20):
    """Historical cumulative volumes at identical 5m cutoff and bar count.

    Comparing a 15:05 partial trading day against full-day volume is
    misleading. Require >=15 previous complete matched-time sessions.
    """
    if today.empty:return dict(ratio=None,count=0,current=None,baseline=None)
    cutoff=today.index[-1]
    minute=cutoff.hour*60+cutoff.minute
    n=len(today)
    hist=[]
    for d,frame in five[five.index.date<cutoff.date()].groupby(five[five.index.date<cutoff.date()].index.date):
        g=frame[(frame.index.hour*60+frame.index.minute>=555)&
                (frame.index.hour*60+frame.index.minute<=minute)].sort_index()
        if len(g)!=n or g.index[0].hour!=9 or g.index[0].minute!=15:continue
        if not bool((g.index.to_series().diff().dropna()==pd.Timedelta(minutes=5)).all()):continue
        v=_num(g.volume.sum())
        if v is not None and v>0:hist.append((d,v))
    hist.sort(key=lambda x:x[0],reverse=True)
    matched=[x[1] for x in hist[:limit]]
    current=_num(today.volume.sum())
    avg=sum(matched)/len(matched) if matched else None
    ratio=current/avg if current is not None and avg and avg>0 else None
    return dict(ratio=round(ratio,2) if ratio is not None else None,
                count=len(matched),current=int(current) if current is not None else None,
                baseline=round(avg,2) if avg else None,
                historical_cutoff=cutoff.strftime("%H:%M"))


def _finite_history(five,daily,now):
    t=pd.Timestamp(now)
    if t.tzinfo is None:return None,None,"Need timezone-aware analysis timestamp"
    if not isinstance(five,pd.DataFrame) or not isinstance(daily,pd.DataFrame):
        return None,None,"Price history missing"
    for df in (five,daily):
        if not isinstance(df.index,pd.DatetimeIndex) or df.index.tz is None or df.index.has_duplicates:
            return None,None,"Invalid or duplicate timestamp"
        if not {"open","high","low","close","volume"}.issubset(df.columns):
            return None,None,"OHLCV fields incomplete"
    f=five.sort_index().copy()
    d=daily.sort_index().copy()
    f=f[(f.index+pd.Timedelta(minutes=5)<=t)&(f.index<=t)]
    f=f[(f.index.hour*60+f.index.minute>=555)&
        (f.index.hour*60+f.index.minute<=925)&
        ((f.index.hour*60+f.index.minute-555)%5==0)]
    d=d[d.index.date<t.date()]
    try:
        cols=["open","high","low","close","volume"]
        f[cols]=f[cols].astype(float)
        d[cols]=d[cols].astype(float)
    except (ValueError,TypeError):return None,None,"Invalid OHLCV numbers"
    if f[cols].isna().any().any() or d[cols].isna().any().any():
        return None,None,"Missing OHLCV numbers"
    if len(d)<55:return None,None,"Need 55 previous completed daily candles"
    today=f[f.index.date==t.date()]
    if len(today)<12:return None,None,"Need at least 12 completed same-session five-minute candles"
    if (today.index[0].hour,today.index[0].minute)!=(9,15):
        return None,None,"Opening 09:15 five-minute bar is missing"
    if not bool((today.index.to_series().diff().dropna()==pd.Timedelta(minutes=5)).all()):
        return None,None,"Gap in current-session five-minute history"
    if (t-today.index[-1]).total_seconds()/60>20:
        return None,None,"Last completed five-minute bar is stale"
    if not (f[["open","high","low","close"]]>0).all().all():
        return None,None,"Invalid non-positive prices"
    if ((f.high<f[["open","low","close"]].max(axis=1)) |
        (f.low>f[["open","high","close"]].min(axis=1))).any():
        return None,None,"Inconsistent candle highs/lows"
    return (f,today,d),t,None


def evaluate(five,daily,now,symbol,*,nifty_change=None,sector_change=None,
             delivery_pct=None,previous_delivery_pct=None,futures_oi=None,
             context=None):
    """Rank daily preclose strength without requiring optional feeds.

    A WATCH with checks is always returned for valid data, even when
    confirmation fails. Research setups never execute orders.
    """
    analysis,t,why=_finite_history(five,daily,now)
    if why:return dict(_no("UNAVAILABLE",why),symbol=symbol)
    f,today,d=analysis
    phase=("PRELIMINARY" if (t.hour,t.minute)<(15,5) else
           "CONFIRMATION" if (t.hour,t.minute)<(15,20) else "FINAL PRE-CLOSE")
    c=float(today.close.iloc[-1]);o=float(today.open.iloc[0])
    hi=float(today.high.max());lo=float(today.low.min())
    v=_matched_volume(f,today)
    proximity=(hi-c)/hi*100 if hi>0 else 100
    range_pos=(c-lo)/(hi-lo) if hi>lo else 0
    last=today.iloc[-1]
    candle_range=float(last.high-last.low)
    wick=float(last.high-max(last.open,last.close))
    small_upper=(candle_range>0 and wick/candle_range<=.3)
    last_hour=(len(today)>=13 and
               c>float(today.close.iloc[-13]) and
               c>float(today.close.iloc[-7]))
    ema20=float(d.close.ewm(span=20,adjust=False).mean().iloc[-1])
    ema50=float(d.close.ewm(span=50,adjust=False).mean().iloc[-1])
    trend=c>ema20>ema50
    prev_hi=float(d.high.iloc[-1])
    h20=float(d.high.tail(20).max())
    break_prev=c>prev_hi
    break20=c>h20
    price_floor=c>=50
    # Risk is based on *previous completed* daily true range and current
    # observed spot structure. Never use a partial daily closing candle.
    tr=pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),
                  (d.low-d.close.shift()).abs()],axis=1).max(axis=1)
    atr=_num(tr.tail(14).mean())
    stop=min(float(today.low.tail(6).min()),c-(atr if atr else 0))
    risk=c-stop
    risk_ok=(atr is not None and atr>0 and .002<=risk/c<=.04)
    volume_ok=(v["ratio"] is not None and v["count"]>=15 and
               v["ratio"]>=1.5)
    index_edge=(round((c/o-1)*100-float(nifty_change),2)
                if nifty_change is not None else None)
    sector_edge=(round((c/o-1)*100-float(sector_change),2)
                if sector_change is not None else None)
    checks={
       "within_one_percent_high":proximity<=1.,
       "close_top_20_percent_of_range":range_pos>=.8,
       "small_upper_wick_last_5m":small_upper,
       "last_hour_rising":last_hour,
       "break_previous_day_high":break_prev,
       "break_prior_20day_high":break20,
       "above_prior_daily_ema20_ema50":trend,
       "matched_volume_ratio_at_least_1_5":volume_ok,
       "cash_price_at_least_50":price_floor,
       "reasonable_structural_stop":risk_ok,
    }
    mandatory=("within_one_percent_high","close_top_20_percent_of_range",
               "last_hour_rising","above_prior_daily_ema20_ema50",
               "matched_volume_ratio_at_least_1_5",
               "cash_price_at_least_50","reasonable_structural_stop")
    missing=[key for key in mandatory if not checks[key]]
    breakout=break_prev or break20
    if not breakout:missing.append("break_previous_high_or_20day_high")
    if not small_upper:missing.append("upper_wick_not_small")
    matched=round(sum(bool(val) for val in checks.values())/len(checks)*100)
    score=round(min(100,max(0,
       10+6*sum(bool(x) for x in checks.values())+
       (10 if break20 else 5 if break_prev else 0)+
       min(10,max(0,(v["ratio"] or 0)-1)*5))))
    is_final=(t.hour,t.minute)>=(15,5)
    qualified=is_final and not missing
    state=("CONFIRMED RESEARCH — NOT AN ORDER" if qualified else
           "PRELIMINARY WATCH — BEFORE 15:05" if not is_final else
           "WATCH — CONDITIONS INCOMPLETE")
    dp=_num(delivery_pct)
    prevdp=_num(previous_delivery_pct)
    delivery=dict(status=("VERIFIED DATED VALUE" if dp is not None else
                          "UNAVAILABLE — LICENSED NSE DELIVERY NOT PROVIDED"),
                  current_pct=dp,
                  previous_pct=prevdp,
                  rising=(dp>prevdp if dp is not None and prevdp is not None else None))
    oi=futures_oi if isinstance(futures_oi,dict) else dict(
        status="UNAVAILABLE — FUTURES OI NOT VERIFIED",
        classification="UNAVAILABLE")
    context=context if isinstance(context,dict) else {}
    details=dict(strategy=NAME,version=VERSION,symbol=symbol,
        signal_at=today.index[-1].isoformat(),phase=phase,
        status=state,direction="BUY WATCH",backtest_status="NOT BACKTESTED",
        probability_of_win=None,confidence=None,
        research_score=score,score_type="EXPLAINABLE RULE SCORE, NOT WIN RATE",
        checks=checks,blockers=missing,
        reasons=[x for x,val in checks.items() if val] +
                (["Breakout above previous high"] if break_prev else [])+
                (["20-session closing breakout observed intraday"] if break20 else []),
        observed_close=round(c,2),observed_high=round(hi,2),
        observed_low=round(lo,2),proximity_to_high_pct=round(proximity,2),
        close_in_day_range_pct=round(100*range_pos,2),
        last_5m_upper_wick_pct=round(wick/candle_range*100,1) if candle_range>0 else None,
        previous_day_high=round(prev_hi,2),previous_20day_high=round(h20,2),
        daily_ema20=round(ema20,2),daily_ema50=round(ema50,2),
        matched_volume=v,
        day_volume_until_last_candle=v["current"],
        index_relative_strength_pct=index_edge,
        sector_relative_strength_pct=sector_edge,
        delivery=delivery,futures_oi=oi,
        market_context=context,
        event_risk=("FRIDAY / WEEKEND GAP RISK" if t.weekday()==4 else
                    "OVERNIGHT GAP / CORPORATE EVENT RISK"),
        entry=None,sl=None,t1=None,t2=None,
        quote_freshness="LAST COMPLETED CASH 5-MINUTE CANDLE — NOT EXCHANGE FINAL CLOSE",
        research_only=True,
        note="Indicative entry/targets are CASH underlying levels only. "
             "Actual closing auction price, overnight exit and gap SL are unknown.")
    if qualified:
        details.update(direction="BUY",entry=round(c,2),sl=round(stop,2),
             t1=round(c+1.5*risk,2),t2=round(c+2.5*risk,2),rr=1.5)
    return details
