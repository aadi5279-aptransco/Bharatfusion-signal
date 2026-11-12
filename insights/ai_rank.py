"""Explainable intraday ranking + ATR/structure risk plan.

This is a deterministic AI-ready scoring layer, NOT a trained ML predictor,
probability, guaranteed entry, or minimum achievable stop-loss. No Dhan orders.
Scores only candidates that have ALREADY passed all 11 requested rules.
"""
from __future__ import annotations
import math
import pandas as pd

VERSION='evidence-ranking-v1'
MAX_STOP_PCT=2.0
MIN_STOP_PCT=.30


def assess(candidate, five, fifteen, depth=None):
    """Return a ranked research scenario or None when a safe stop is absent.

    Entry trigger is beyond the latest COMPLETED 5m candle, not an observed
    fill. The stop is outside 3-bar structure and at least 0.8 ATR away;
    an excessive >2% stop causes rejection, never artificial tightening.
    """
    if not isinstance(candidate,dict) or candidate.get('rule_matches')!=11:return None
    if candidate.get('direction') not in ('BUY','SELL'):return None
    if five is None or fifteen is None or len(five)<21 or len(fifteen)<40:return None
    if not isinstance(five.index,pd.DatetimeIndex) or five.index.tz is None:return None
    side=candidate['direction']
    f=five.sort_index()
    h=fifteen.sort_index()
    try:
        close=float(f.close.iloc[-1])
        atr_true=pd.concat([
            f.high-f.low,(f.high-f.close.shift()).abs(),
            (f.low-f.close.shift()).abs()],axis=1).max(axis=1)
        atr=float(atr_true.ewm(alpha=1/14,adjust=False,min_periods=14).mean().iloc[-1])
        if not math.isfinite(atr) or atr<=0:return None
        reference_close=float(candidate['entry'])
        if abs(reference_close-close)>max(.05,.003*close):return None
        sign=1 if side=='BUY' else -1
        # Break the last 5m extreme by a minimum tick-like volatility buffer.
        buffer=max(.05,atr*.08)
        trigger=(float(f.high.iloc[-1])+buffer if side=='BUY'
                 else float(f.low.iloc[-1])-buffer)
        if side=='BUY':
            structure=float(f.low.tail(3).min())-.1*atr
            stop=min(structure,trigger-.8*atr)
        else:
            structure=float(f.high.tail(3).max())+.1*atr
            stop=max(structure,trigger+.8*atr)
        risk=sign*(trigger-stop)
        stop_pct=risk/trigger*100 if trigger>0 else 100
        if not (MIN_STOP_PCT<=stop_pct<=MAX_STOP_PCT):return None
        # Rank setup strength; not a calibrated odds-of-success estimate.
        daily_rvol=float(candidate.get('daily_volume_ratio',0))
        m15_rvol=float(candidate.get('volume_ratio15',0))
        daily_rsi=float(candidate.get('daily_rsi14',50))
        rsi15=float(candidate.get('rsi15',50))
        vol_score=min(25,max(0,(daily_rvol-1.5)*11)) + min(25,max(0,(m15_rvol-2)*11))
        strength_score=min(22,max(0,(daily_rsi-60 if side=='BUY' else 40-daily_rsi)*1.3))
        strength_score+=min(15,max(0,(rsi15-60 if side=='BUY' else 40-rsi15)*.75))
        # Reward a smooth aligned three-candle continuation, without treating
        # it as a new mandatory rule.
        last3=f.close.tail(3).diff().dropna()
        continuation=(last3.gt(0).all() if side=='BUY' else last3.lt(0).all())
        slope_score=7 if continuation else 0
        risk_score=max(0,6-3*stop_pct)
        score=min(100,round(vol_score+strength_score+slope_score+risk_score,1))
        reasons=[
          'All 8 running-daily and 3 completed-15m momentum conditions passed',
          f'Daily running-volume ratio {daily_rvol:.2f}×; 15m volume ratio {m15_rvol:.2f}×',
          f'Daily RSI {daily_rsi:.1f}; 15m RSI {rsi15:.1f}',
          f'Last 3 completed 5m closes {"aligned" if continuation else "mixed"}',
          f'Proposed protective distance {stop_pct:.2f}% (ATR/3-bar structure)',
          'Score is deterministic evidence weighting, not trained AI probability'
        ]
        depth_ratio=None
        if isinstance(depth,dict) and depth.get('verified'):
            try:
                ratio=float(depth.get('bid_ask_ratio'))
                if math.isfinite(ratio) and ratio>0:
                    depth_ratio=round(ratio,2)
                    reasons.append(f'Verified RESTING book bid/ask ratio {depth_ratio:.2f}; not trade delta')
            except (ValueError,TypeError):pass
        # Do not rank on an unverified depth imbalance.
        return dict(candidate,
            entry=round(trigger,2),sl=round(stop,2),
            t1=round(trigger+sign*1.5*risk,2),
            t2=round(trigger+sign*2.5*risk,2),
            rr=1.5,entry_reference_close=round(close,2),
            entry_type='CONDITIONAL 5m EXTREME BREAK — NOT A FILL',
            entry_trigger=round(trigger,2),stop_distance_pct=round(stop_pct,2),
            atr14_5m=round(atr,2),
            ranking_score=score,ai_score=score,ranking_model=VERSION,
            score_type='EXPLAINABLE HEURISTIC — NOT TRAINED ML / NOT PROBABILITY',
            depth_ratio=depth_ratio,
            risk_policy=f'Structure-aware stop; reject setups beyond {MAX_STOP_PCT}% initial distance',
            reasons=list(candidate.get('reasons',[]))+reasons)
    except (ValueError,TypeError,KeyError,IndexError,ZeroDivisionError):
        return None


def top_ten(candidates):
    """Stable rank across BOTH directions. Never fill the ten with failed setups."""
    candidates=[v for v in candidates if v and v.get('ai_score') is not None]
    return sorted(candidates,key=lambda x:(
        -x['ai_score'],x['stop_distance_pct'],
        -(x.get('daily_volume_ratio') or 0),
        x.get('symbol','')) )[:10]
