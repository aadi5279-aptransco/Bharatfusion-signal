"""Prior-session, non-predictive 08:00 IST stock watchlist ranking.

Only fully completed exchange DAILY bars, never pre-open quote prices.
The scanner separates previous-day momentum from genuine 20-day closing
breakout/breakdown. Published watchlist means 'watch', NOT BUY/SELL.
"""
from __future__ import annotations
import math
import pandas as pd

VERSION="premarket-watch-v1"

def evaluate(frame,symbol,now):
    if frame is None or not isinstance(frame,pd.DataFrame) or len(frame)<55:
        return None
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None or frame.index.has_duplicates:
        return None
    required={"open","high","low","close","volume"}
    if not required.issubset(frame.columns):return None
    t=pd.Timestamp(now)
    if t.tzinfo is None:return None
    f=frame.sort_index().copy()
    f=f[f.index.date<t.date()] if (t.hour,t.minute)<(15,40) else f[f.index.date<=t.date()]
    if len(f)<55:return None
    try:f[list(required)]=f[list(required)].astype(float)
    except (ValueError,TypeError):return None
    if f[list(required)].isna().any().any() or not (f[["open","high","low","close"]]>0).all().all() or (f.volume<0).any():
        return None
    last=f.iloc[-1];prev=f.iloc[-2];price=float(last.close)
    if prev.close<=0:return None
    daily_change=100*(price/float(prev.close)-1)
    recent=f.iloc[-21:-1]
    if len(recent)<20:return None
    vol20=float(recent.volume.mean())
    rvol=float(last.volume)/vol20 if vol20>0 else None
    high20=float(recent.high.max());low20=float(recent.low.min())
    ema20=float(f.close.ewm(span=20,adjust=False).mean().iloc[-1])
    ema50=float(f.close.ewm(span=50,adjust=False).mean().iloc[-1])
    up=price>high20;down=price<low20
    side="BUY WATCH" if daily_change>0 else "SELL WATCH" if daily_change<0 else "NEUTRAL"
    aligned=(price>ema20>ema50 if daily_change>0 else price<ema20<ema50 if daily_change<0 else False)
    breakout=(up if daily_change>0 else down if daily_change<0 else False)
    # Momentum list is inclusive; qualifying *breakout* is a separate flag.
    strength=min(40,abs(daily_change)*7)
    score=round(strength+(25 if breakout else 0)+(20 if aligned else 0)+
                (15 if rvol is not None and rvol>=1.5 else 0),1)
    return dict(symbol=symbol,direction=side,previous_session=f.index[-1].date().isoformat(),
        close=round(price,2),previous_close=round(float(prev.close),2),
        previous_day_change_pct=round(daily_change,3),
        prior_20_high=round(high20,2),prior_20_low=round(low20,2),
        closing_breakout=bool(up),closing_breakdown=bool(down),
        trend_aligned=bool(aligned),volume_ratio=round(rvol,2) if rvol is not None else None,
        score=score,score_type="HEURISTIC WATCH RANK; NOT A WIN PROBABILITY",
        status="PRE-MARKET WATCH — NOT A TRADE",
        reasons=["Prior-session daily change {:.2f}%".format(daily_change),
                 "Close beyond prior 20-day high" if up else
                 "Close below prior 20-day low" if down else
                 "No confirmed 20-day closing breakout/breakdown",
                 "EMA20/EMA50 direction aligned" if aligned else "Daily trend not fully aligned",
                 "Prior-session volume {:.2f}x 20-day average".format(rvol) if rvol is not None else "Volume reference unavailable"],
        data_source="COMPLETED LICENSED DAILY BARS",research_only=True)


def rank(items,asof,limit=10):
    """Return independent momentum leader and laggard lists, not trade calls."""
    valid=[x for x in items if isinstance(x,dict)]
    gainers=sorted((x for x in valid if x["previous_day_change_pct"]>0),
        key=lambda x:(x["score"],x["previous_day_change_pct"]),reverse=True)[:limit]
    losers=sorted((x for x in valid if x["previous_day_change_pct"]<0),
        key=lambda x:(x["score"],-x["previous_day_change_pct"]),reverse=True)[:limit]
    return dict(gainers=gainers,losers=losers,asof=asof,
        status="PRE-MARKET WATCH ONLY — NOT CONFIRMED LIVE",
        note="Ranks the mapped sampled universe using only the previous completed session, no future or 08:00 market candles. Strict intraday signals remain separate.")
