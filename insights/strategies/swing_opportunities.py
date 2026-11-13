"""Independent daily + weekly swing opportunity finder.

Watches trend pullbacks and 20-day closing breakouts in a *bounded
sampled universe*. The old strict swing signals are not overwritten.

No repaint: day-of-analysis must have completed, weekly uses last
finished calendar week, breakout levels exclude the signal candle.
Only a verified completed same-day daily close may be "READY".
Entries are CONDITIONAL next-session triggers, not fills.
"""
from __future__ import annotations
import math
from datetime import datetime
import pandas as pd
from insights.config import IST
from insights.strategies.swing import _atr,_rsi

VERSION="swing-opportunities-v1"


def _result(symbol,status,reason,asof=None):
    return dict(symbol=symbol,strategy="Daily + Weekly Swing Finder",
        version=VERSION,status=status,setup="UNAVAILABLE",
        reference_date=asof,score=None,score_type="HEURISTIC RULE SCORE",
        entry=None,stop=None,target=None,target_3r=None,risk_reward=None,
        probability_of_win=None,research_only=True,reasons=[],blockers=[reason],
        checks={},volume_ratio=None,avg_traded_value_lakh=None,
        weekly_trend="UNAVAILABLE",daily_trend="UNAVAILABLE",
        breakout_level=None,ema21=None,ema50=None,ema200=None,
        rsi14=None,atr14=None,readiness="UNAVAILABLE")


def evaluate(frame,symbol,asof):
    t=pd.Timestamp(asof)
    if t.tzinfo is None:return _result(symbol,"UNAVAILABLE","Timezone-aware as-of required")
    t=t.tz_convert(IST)
    if not isinstance(frame,pd.DataFrame) or not {"open","high","low","close","volume"}.issubset(frame.columns):
        return _result(symbol,"UNAVAILABLE","Daily OHLCV unavailable")
    index=frame.index
    # pandas may use an object index when aware timestamps have mixed
    # timezone representations. Accept those without guessing naive dates.
    if not isinstance(index,pd.DatetimeIndex):
        if not all(isinstance(x,datetime) and x.tzinfo is not None
                   and x.utcoffset() is not None for x in index):
            return _result(symbol,"UNAVAILABLE","Duplicate or timezone-naive daily timestamps")
        try:index=pd.to_datetime(index,utc=True)
        except (TypeError,ValueError):
            return _result(symbol,"UNAVAILABLE","Invalid daily timestamps")
    if index.tz is None or index.has_duplicates or index.hasnans:
        return _result(symbol,"UNAVAILABLE","Duplicate or timezone-naive daily timestamps")
    # Concatenating differently named timezones can normalize an index to
    # UTC. Session dates and weekly buckets must always use exchange time.
    daily=frame.copy()
    daily.index=index.tz_convert(IST)
    daily=daily.sort_index()
    day_complete=(t.hour,t.minute)>=(15,40)
    daily=daily[(daily.index.date<t.date())|
                ((daily.index.date==t.date())&day_complete)]
    if len(daily)<260:return _result(symbol,"UNAVAILABLE","Need 260 completed daily candles")
    cols=["open","high","low","close","volume"]
    try:daily[cols]=daily[cols].astype(float)
    except (TypeError,ValueError):return _result(symbol,"UNAVAILABLE","Non-numeric daily OHLCV")
    if daily[cols].isna().any().any() or not (daily[cols[:4]]>0).all().all() or (daily.volume<0).any():
        return _result(symbol,"UNAVAILABLE","Invalid daily OHLCV")
    if (daily.high<daily[["open","low","close"]].max(axis=1)).any() or (
        daily.low>daily[["open","high","close"]].min(axis=1)).any():
        return _result(symbol,"UNAVAILABLE","Inconsistent daily OHLC")
    close=daily.close
    c=float(close.iloc[-1])
    ema21=close.ewm(span=21,adjust=False).mean()
    ema50=close.ewm(span=50,adjust=False).mean()
    ema200=close.ewm(span=200,adjust=False).mean()
    e21,e50,e200=map(float,(ema21.iloc[-1],ema50.iloc[-1],ema200.iloc[-1]))
    atr=float(_atr(daily).iloc[-1]);rsi=float(_rsi(close).iloc[-1])
    if not math.isfinite(atr) or atr<=0 or not math.isfinite(rsi):
        return _result(symbol,"UNAVAILABLE","ATR / RSI not computable")
    # Friday closes qualify as completed weekly bars only AFTER 15:40.
    weekly=daily.resample("W-FRI").agg(dict(open="first",high="max",
        low="min",close="last",volume="sum")).dropna()
    week_complete=t.weekday()==4 and day_complete
    weekly=weekly[(weekly.index.date<t.date())|
          ((weekly.index.date==t.date())&week_complete)]
    if len(weekly)<35:
        return _result(symbol,"UNAVAILABLE","Need at least 35 completed weeks")
    wema10=weekly.close.ewm(span=10,adjust=False).mean()
    weekly_ok=(float(weekly.close.iloc[-1])>float(wema10.iloc[-1]) and
               float(wema10.iloc[-1])>float(wema10.iloc[-4]))
    daily_ok=(c>e50>e200 and e21>e50 and
              float(ema50.iloc[-1])>float(ema50.iloc[-7]))
    trend=daily_ok and weekly_ok
    last=daily.iloc[-1]
    prior=daily.iloc[-21:-1]
    high20=float(prior.high.max())
    low20=float(prior.low.min())
    prior_high=float(daily.high.iloc[-2])
    vol20=float(prior.volume.mean())
    ratio=float(last.volume)/vol20 if vol20>0 else None
    turnover=float((prior.close*prior.volume).mean())/100000.
    recent_lows=daily.low.iloc[-8:-1]
    ema21_window=ema21.iloc[-8:-1]
    touched=bool((recent_lows<=ema21_window*1.015).any())
    reclaimed=c>e21 and c>prior_high and float(last.close)>float(last.open)
    breakout=(c>high20 and ratio is not None and ratio>=1.2)
    pullback=(touched and reclaimed and ratio is not None and ratio>=0.85)
    liquid=(c>=50 and turnover>=75)
    momentum=(50<=rsi<=85)
    ready_break=trend and breakout and liquid and momentum
    ready_pull=trend and pullback and liquid and momentum
    near_break=(c>=.97*high20 and c<=high20*1.015)
    near_pull=(daily_ok and abs(c-e21)/c<=.03 and c>e50)
    no_future=(daily.index[-1].date()==t.date() and day_complete)
    checks=dict(
        long_term_ema=c>e50>e200,
        ema21_above_ema50=e21>e50,
        ema50_rising=ema50.iloc[-1]>ema50.iloc[-7],
        completed_weekly_uptrend=weekly_ok,
        closing_breakout_prior_20d=c>high20,
        breakout_volume_1_2x=(ratio is not None and ratio>=1.2),
        touched_ema21_last_week=touched,
        bullish_reclaim_above_yesterday_high=reclaimed,
        turnover_75_lakh_per_day=turnover>=75,
        cash_price_over_50=c>=50,
        rsi_50_to_85=momentum,
        latest_session_complete=no_future)
    if ready_break:setup="20-DAY BREAKOUT"
    elif ready_pull:setup="EMA21 PULLBACK RECLAIM"
    elif near_break:setup="NEAR 20-DAY BREAKOUT"
    elif near_pull:setup="EMA21 PULLBACK WATCH"
    elif daily_ok:setup="UPTREND WAIT"
    else:setup="NO BULLISH SETUP"
    score=round(min(100,
         8+7*sum(bool(v) for k,v in checks.items() if k!="latest_session_complete")+
         (8 if ready_break else 5 if ready_pull else 0)))
    ready=(ready_break or ready_pull) and no_future
    status=("READY — CONDITIONAL SWING RESEARCH" if ready else
           "WATCH — INCOMPLETE OR STALE" if setup!="NO BULLISH SETUP" else
           "NO TRADE — TREND UNCONFIRMED")
    result=_result(symbol,status,"No qualified completed daily setup",
                   daily.index[-1].date().isoformat())
    result.update(setup=setup,readiness="READY" if ready else "WATCH",
        score=score,close=round(c,2),breakout_level=round(high20,2),
        prior_20d_low=round(low20,2),
        previous_day_high=round(prior_high,2),
        ema21=round(e21,2),ema50=round(e50,2),ema200=round(e200,2),
        atr14=round(atr,2),rsi14=round(rsi,1),
        weekly_trend="UP" if weekly_ok else "NOT CONFIRMED",
        daily_trend="UP" if daily_ok else "NOT CONFIRMED",
        volume_ratio=round(ratio,2) if ratio is not None else None,
        avg_traded_value_lakh=round(turnover,1),
        checks={k:bool(v) for k,v in checks.items()},
        blockers=[k for k,v in checks.items() if not bool(v)],
        reasons=([setup] if setup!="NO BULLISH SETUP" else [])+
                (["Completed week confirms uptrend"] if weekly_ok else [])+
                (["Price above 50/200 EMA"] if c>e50>e200 else [])+
                (["20-day close breakout with 1.2x volume"] if breakout else []),
        risk_note="Cash underlying next-session conditional levels. Overnight gap and surveillance/circuit risk unverified.")
    if ready:
        trigger=max(float(last.high),high20)+0.1*atr
        # Below recent support and EMA21, with a volatility floor.
        stop=min(float(daily.low.iloc[-6:].min())-.1*atr,e21-.25*atr)
        risk=trigger-stop
        if trigger>0 and 0.003<=risk/trigger<=.09:
            result.update(entry=round(trigger,2),stop=round(stop,2),
                target=round(trigger+2*risk,2),target_3r=round(trigger+3*risk,2),
                risk_reward=2.0,entry_rule="Trigger only AFTER next-session price crosses this level",
                blockers=[],status="READY — CONDITIONAL SWING RESEARCH")
        else:
            result.update(readiness="WATCH",status="WATCH — STOP DISTANCE UNSUITABLE",
                          blockers=["Stop distance outside 0.3–9% guard"])
    return result

