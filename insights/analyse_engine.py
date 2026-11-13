"""Point-in-time stock/index bias and conditional research plan.

Nothing here estimates a historical win probability. Not an order signal.
Order flow is limited to observed resting depth and derivative OI proxies.
"""
from __future__ import annotations
import math
import pandas as pd
from insights import cycle_wave


def _rsi(c):
    delta=c.diff()
    pos=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    neg=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    a=float(pos.iloc[-1]);b=float(neg.iloc[-1])
    if not (math.isfinite(a) and math.isfinite(b)):return None
    if b==0:return 100.0 if a>0 else 50.0
    return 100-100/(1+a/b)


def evaluate(five,fifteen,hourly,now,depth=None,option_metrics=None):
    """Conservative 5/15/60 trend consensus and structure/ATR levels."""
    missing=dict(status="UNAVAILABLE — NEED VERIFIED COMPLETED CASH CANDLES",
                 bias="UNAVAILABLE",win_probability=None,probability_status="NOT CALIBRATED",
                 score=None,entry_plan=None,order_flow=dict(status="UNAVAILABLE"),
                 mtf={},gann_wave={},reasons=[])
    for frame in (five,fifteen,hourly):
        if frame is None or not isinstance(frame,pd.DataFrame) or len(frame)<55:
            return missing
        if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:
            return missing
        if not {"close","high","low","open","volume"}.issubset(frame.columns):
            return missing
    now=pd.Timestamp(now)
    if now.tzinfo is None:return missing
    # All three datasets must have at least one completed recent candle,
    # but the 60m feed can lag an hour while a new candle forms.
    for f,period,lag in ((five,5,20),(fifteen,15,35),(hourly,60,130)):
        ts=f.index[-1]
        if ts.date()!=now.date():return missing
        age=(now-ts).total_seconds()/60
        if not period<=age<=lag:return missing
    info={}
    votes=0
    reasons=[]
    for key,f in (("5m",five),("15m",fifteen),("60m",hourly)):
        c=f.close.astype(float)
        fast=float(c.ewm(span=20,adjust=False).mean().iloc[-1])
        slow=float(c.ewm(span=50,adjust=False).mean().iloc[-1])
        current=float(c.iloc[-1])
        rsi=_rsi(c)
        trend="UP" if current>fast>slow else "DOWN" if current<fast<slow else "MIXED"
        info[key]=dict(trend=trend,close=round(current,2),ema20=round(fast,2),
                       ema50=round(slow,2),rsi14=round(rsi,2) if rsi is not None else None,
                       asof=f.index[-1].isoformat())
        if trend=="UP":votes+=1
        elif trend=="DOWN":votes-=1
    close=float(five.close.iloc[-1])
    tr=pd.concat([five.high-five.low,(five.high-five.close.shift()).abs(),
                  (five.low-five.close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean().iloc[-1])
    if not math.isfinite(atr) or atr<=0:return missing
    prior_high=float(five.high.iloc[-21:-1].max())
    prior_low=float(five.low.iloc[-21:-1].min())
    bullish=(votes==3 and close>prior_high)
    bearish=(votes==-3 and close<prior_low)
    bias=("BULLISH" if bullish else "BEARISH" if bearish else
          "BULLISH WATCH" if votes>=2 else "BEARISH WATCH" if votes<=-2 else "NEUTRAL / NO TRADE")
    evidence=cycle_wave.assess(five,now)
    depth_state="UNVERIFIED — NO EXECUTED TRADE DELTA"
    ratio=None
    if isinstance(depth,dict) and depth.get("verified"):
        try:
            ratio=float(depth["bid_ask_ratio"])
            if not math.isfinite(ratio) or ratio<=0:ratio=None
        except (ValueError,TypeError,KeyError):ratio=None
        if ratio is not None:depth_state="VERIFIED RESTING BOOK DEPTH — NOT AGGRESSOR FLOW"
    flow=dict(status=depth_state,bid_ask_ratio=round(ratio,2) if ratio is not None else None,
              derivative_oi_note="PCR/open interest represent positioning, not executed orders")
    if option_metrics and option_metrics.get("pcr") is not None:
        flow["pcr"]=option_metrics["pcr"]
    score=min(100,round(35+abs(votes)*12+
            (8 if (bullish or bearish) else 0)+
            (4 if ratio is not None and ((bullish and ratio>1) or (bearish and ratio<1)) else 0)))
    plan=None
    if bullish or bearish:
        sign=1 if bullish else -1
        buffer=max(.05,.1*atr)
        trigger=(float(five.high.iloc[-1])+buffer if bullish
                 else float(five.low.iloc[-1])-buffer)
        stop=(min(float(five.low.tail(5).min())-.1*atr,trigger-.9*atr)
              if bullish else max(float(five.high.tail(5).max())+.1*atr,trigger+.9*atr))
        risk=sign*(trigger-stop)
        if .002<=risk/trigger<=.03:
            plan=dict(direction="BUY" if bullish else "SELL",
                      entry=round(trigger,2),sl=round(stop,2),
                      t1=round(trigger+1.5*sign*risk,2),
                      t2=round(trigger+2.5*sign*risk,2),
                      rr=1.5,
                      entry_type="CONDITIONAL CASH/INDEX TRIGGER — NOT A FILL",
                      stop_distance_pct=round(100*risk/trigger,2),
                      note="Underlying price levels, NOT verified option premiums")
        else:reasons.append("Risk too wide/narrow; do not force an entry")
    reasons.extend(["MTF votes: "+str(votes)+" (5m, 15m, 60m)",
                    "20-bar cash high/low breakout required for trade scenario",
                    "Gann and wave data are optional research layers, NOT win probabilities"])
    return dict(status="RESEARCH ONLY — PRICE DATA FRESHNESS VERIFIED",
                bias=bias,win_probability=None,probability_status="UNAVAILABLE — NO CALIBRATED WALK-FORWARD MODEL",
                score=score,score_type="HEURISTIC EVIDENCE SCORE, NOT WIN PROBABILITY",
                entry_plan=plan,order_flow=flow,mtf=info,gann_wave=evidence,
                reasons=reasons,data_asof=five.index[-1].isoformat())
