"""Additional PDF-guided 3–15-session swing setup layer, research only.

From the user's Swing Trading Strategies for Indian Stocks PDF:
(1) 20 EMA trend pullback, (2) tight-base 20-day closing breakout,
(3) RSI(2) oversold dip in 200-SMA uptrend, (4) relative strength vs NIFTY,
(5) volatility squeeze release. No live orders or invented backtests.

Entry: conditional next-session trigger above signal high; stop uses 2 ATR;
target 2R. All calculations use completed daily bars only, shifted prior
volume baseline and previous-day rolling highs to prevent look-ahead.
"""
from __future__ import annotations

import math
import pandas as pd
from insights.config import IST

VERSION="swing-pdf-five-setups-v1"
MIN_BARS=220
SETUPS=("20 EMA TREND PULLBACK","TIGHT BASE BREAKOUT",
        "RSI(2) DIP","VOLATILITY SQUEEZE BREAKOUT")


def _bad(symbol, reason):
    return dict(symbol=symbol,status="UNAVAILABLE",version=VERSION,
        asof=None,matched_setups=[],observations=[],entry=None,
        stop=None,target_2r=None,quantity=None,rs_score=None,
        rs_rank_percentile=None,relative_strength="UNAVAILABLE",
        readiness="UNAVAILABLE",blockers=[reason],research_only=True,
        win_probability=None)


def _rsi(s,n):
    difference=s.diff()
    up=difference.clip(lower=0).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    down=(-difference.clip(upper=0)).ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    return (100-100/(1+up/down.replace(0,float("nan")))).where(down>0,100).where(up>0,0)


def _atr(frame,n=14):
    prev=frame.close.shift(1)
    tr=pd.concat((frame.high-frame.low,(frame.high-prev).abs(),
                 (frame.low-prev).abs()),axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()


def relative_strength(frame,benchmark):
    """Relative 63/126-session return vs actual NIFTY, no future rows."""
    if benchmark is None or not isinstance(benchmark,pd.DataFrame):
        return None
    if not isinstance(benchmark.index,pd.DatetimeIndex) or benchmark.index.tz is None:
        return None
    if "close" not in benchmark.columns:return None
    idx=benchmark.sort_index().copy()
    idx=idx[~idx.index.duplicated(keep=False)]
    if len(idx)<140:return None
    # Compare on common trading DATES, not timestamp equality. Do not
    # forward-fill a stale benchmark into a new stock market session.
    stock=frame[["close"]].copy()
    stock.index=pd.Index(stock.index.date)
    idx.index=pd.Index(idx.index.date)
    values=idx["close"].reindex(stock.index)
    if len(values)<126 or values.iloc[[-1,-63,-126]].isna().any():return None
    if any(float(x)<=0 for x in values.iloc[[-1,-63,-126]]):return None
    c=stock.close
    return float(.5*((c.iloc[-1]/c.iloc[-63]-1)-
                        (values.iloc[-1]/values.iloc[-63]-1))+
                 .5*((c.iloc[-1]/c.iloc[-126]-1)-
                        (values.iloc[-1]/values.iloc[-126]-1)))


def evaluate(frame,symbol,asof,benchmark=None):
    t=pd.Timestamp(asof)
    if t.tzinfo is None:return _bad(symbol,"Timezone-aware scan time required")
    t=t.tz_convert(IST)
    if frame is None or not isinstance(frame,pd.DataFrame):
        return _bad(symbol,"Completed daily OHLCV missing")
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None or frame.index.has_duplicates:
        return _bad(symbol,"Timezone-aware, nonduplicate daily index required")
    cols=["open","high","low","close","volume"]
    if not set(cols).issubset(frame.columns):return _bad(symbol,"Daily OHLCV columns missing")
    f=frame.sort_index().copy()
    today_complete=(t.hour,t.minute)>=(15,40)
    f=f[(f.index.date<t.date())|((f.index.date==t.date())&today_complete)]
    if len(f)<MIN_BARS:return _bad(symbol,"Need 220 completed daily candles")
    try:f[cols]=f[cols].astype(float)
    except (TypeError,ValueError):return _bad(symbol,"Non-numeric daily candles")
    if f[cols].isna().any().any() or (f[cols[:4]]<=0).any().any() or (f.volume<0).any():
        return _bad(symbol,"Invalid daily OHLCV")
    if (f.high<f[["open","low","close"]].max(axis=1)).any() or (
        f.low>f[["open","high","close"]].min(axis=1)).any():
        return _bad(symbol,"Inconsistent daily OHLC ranges")
    if today_complete and f.index[-1].date()!=t.date():
        # Keep historical inspection possible but never call it a
        # same-session end-of-day qualification.
        freshness="PRIOR SESSION ONLY"
    else:
        freshness=("COMPLETE TODAY" if f.index[-1].date()==t.date()
                   else "PRIOR SESSION ONLY")
    c=f.close;last=f.iloc[-1];latest=float(last.close)
    ema20=c.ewm(span=20,adjust=False).mean()
    ema50=c.ewm(span=50,adjust=False).mean()
    sma200=c.rolling(200).mean()
    rsi14=_rsi(c,14);rsi2=_rsi(c,2)
    atr=_atr(f)
    vol20=f.volume.rolling(20).mean().shift(1)
    turnover20=(f.close*f.volume).rolling(20).mean().shift(1)
    top_range=max(float(last.high-last.low),0)
    top_close=((latest-float(last.low))/top_range if top_range>0 else 0)
    e20=float(ema20.iloc[-1]);e50=float(ema50.iloc[-1])
    a=float(atr.iloc[-1]);v20=float(vol20.iloc[-1])
    average_turnover=float(turnover20.iloc[-1])
    ratio=float(last.volume)/v20 if v20>0 else None
    liquid=latest>=50 and average_turnover>=50_000_000
    matches=[];checks={}
    long_up=latest>float(sma200.iloc[-1]) and e20>e50
    dipped=(float(last.low)<=e20*1.01 and float(last.low)>=e50*.98)
    bounce=(latest>e20 and latest>float(last.open) and
            latest>float(c.iloc[-2]))
    calm=40<=float(rsi14.iloc[-1])<=60
    checks["pullback"]=bool(long_up and dipped and bounce and calm)
    if checks["pullback"]:matches.append(SETUPS[0])
    # Tightness excludes the signal candle and its breakout range.
    base=(f.high.rolling(15).max()-f.low.rolling(15).min())/f.close
    tight=bool(float(base.iloc[-2])<.12)
    high20=float(f.high.iloc[-21:-1].max())
    breakout=latest>high20 and ratio is not None and ratio>=1.5
    checks["base_breakout"]=bool(tight and breakout and top_close>.7 and latest>e50)
    if checks["base_breakout"]:matches.append(SETUPS[1])
    checks["rsi2_dip"]=bool(latest>float(sma200.iloc[-1]) and
          float(rsi2.iloc[-1])<10 and latest>e50*.97)
    if checks["rsi2_dip"]:matches.append(SETUPS[2])
    ma20=c.rolling(20).mean();sd20=c.rolling(20).std()
    width=4*sd20/ma20.replace(0,float("nan"))
    past_width=width.iloc[-121:-1].dropna()
    squeeze=(len(past_width)>=100 and
             float(width.iloc[-2])<=float(past_width.quantile(.15)))
    release=latest>float(ma20.iloc[-1]+2*sd20.iloc[-1])
    checks["volatility_squeeze"]=bool(squeeze and release and
            ratio is not None and ratio>=1.2 and latest>e50)
    if checks["volatility_squeeze"]:matches.append(SETUPS[3])
    rs=relative_strength(f,benchmark)
    result=dict(symbol=symbol,version=VERSION,
        asof=f.index[-1].date().isoformat(),status="WATCH — NO SETUP",
        matched_setups=matches,observations=checks,
        readiness="WATCH",entry=None,stop=None,target_2r=None,
        probability_of_win=None,win_probability=None,quantity=None,
        rs_score=round(rs*100,2) if rs is not None else None,
        rs_rank_percentile=None,
        relative_strength="AVAILABLE" if rs is not None else "UNAVAILABLE — BENCHMARK DATA MISSING",
        close=round(latest,2),signal_high=round(float(last.high),2),
        prior_high20=round(high20,2),
        ema20=round(e20,2),ema50=round(e50,2),
        rsi14=round(float(rsi14.iloc[-1]),2),rsi2=round(float(rsi2.iloc[-1]),2),
        atr14=round(a,2),volume_ratio=round(ratio,2) if ratio is not None else None,
        average_turnover_cr=round(average_turnover/10_000_000,2),
        freshness=freshness,hold_sessions="2–15 depending on setup",
        exit_rules={"pullback":"2R or completed close below EMA20",
                    "breakout":"Trail below completed daily EMA10",
                    "rsi2":"Close above prior day's high, RSI2>70 or five sessions",
                    "squeeze":"2R or trail below EMA10"},
        blockers=[],research_only=True,
        note="RS ranks use the sampled mapped Dhan universe, NOT the entire NIFTY 500. Corporate events, ASM/GSM, execution gaps and charges unverified.")
    if not matches:
        result["blockers"]=["No PDF-defined confirmed setup"]
        return result
    if not liquid:
        result["status"]="WATCH — PRICE OR TURNOVER BELOW GUIDE FLOOR"
        result["blockers"]=["Need stock price >= ₹50 and prior 20-day average turnover >= ₹5 crore"]
        return result
    if rs is None:
        result["status"]="WATCH — NIFTY RELATIVE STRENGTH UNAVAILABLE"
        result["blockers"]=["Verified aligned NIFTY 63/126-session close series unavailable"]
        return result
    # Next-session conditional trigger. The publication's RSI2 time exit
    # is displayed, but no same-day or next-day fill is assumed.
    entry=round(float(last.high)*1.001/0.05)*.05
    risk=2*a
    stop=round((entry-risk)/.05)*.05
    if not math.isfinite(risk) or risk<=0 or stop<=0 or risk/entry>.15:
        result["status"]="WATCH — ATR STOP UNSUITABLE"
        result["blockers"]=["2× ATR is invalid or >15% of entry"]
        return result
    result.update(entry=round(entry,2),stop=round(stop,2),
        target_2r=round(entry+2*(entry-stop),2),
        risk_pct=round((entry-stop)/entry*100,2),
        status="WATCH — RELATIVE STRENGTH RANK PENDING",
        readiness="WATCH",
        entry_rule="Conditional next-session buy-stop above completed signal-day high; NOT a fill")
    return result


def rank(results,top_fraction=.30):
    """Rank within assessed securities; disclose coverage explicitly."""
    scored=[x for x in results if x.get("rs_score") is not None]
    scored.sort(key=lambda x:(-x["rs_score"],x["symbol"]))
    if not scored:return results
    total=len(scored)
    for place,row in enumerate(scored):
        pct=100*(total-place)/total
        row["rs_rank_percentile"]=round(pct,1)
        if row.get("entry") is None:continue
        if pct>=100*(1-top_fraction):
            row["readiness"]="CONDITIONAL RESEARCH"
            row["status"]="CONDITIONAL NEXT-SESSION SWING RESEARCH — EVENT RISK UNVERIFIED"
        else:
            row["status"]="WATCH — BELOW TOP 30% SAMPLED NIFTY RELATIVE STRENGTH"
            row["blockers"].append("Below sampled-universe top 30% relative strength")
            row["entry"]=row["stop"]=row["target_2r"]=None
    return results
