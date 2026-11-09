"""Conservative, no-lookahead candle-by-candle signal outcomes.

Pass *actual* Dhan OHLCV and a pure strategy function. Identical bar containing
both stop and target counts as a stop. All results include transaction costs.
Never treat missing data as a win.
"""
from __future__ import annotations
from datetime import datetime,timezone
import math
import pandas as pd


def evaluate_trades(frame, signal_fn, name, version='1.0', hold_bars=12, costs_bps=20, warmup=220):
    if not isinstance(frame,pd.DataFrame) or len(frame)<=warmup+hold_bars:raise ValueError('Insufficient historical candles')
    if hold_bars<=0 or costs_bps<0:raise ValueError('Invalid backtest parameters')
    f=frame.sort_index()
    trades=[];i=warmup
    while i<len(f)-hold_bars:
        observed=f.iloc[:i+1]  # strategy cannot see the future
        candidate=signal_fn(observed)
        if not candidate:
            i+=1;continue
        direction=candidate['direction'];entry=float(candidate['entry']);stop=float(candidate['sl']);t1=float(candidate['t1'])
        sign=1 if direction in ('BUY','CE','PE') else -1
        risk=sign*(entry-stop)
        if risk<=0 or not math.isfinite(risk):i+=1;continue
        result=None;exit_price=None;exit_bar=None
        for j in range(i+1,min(i+hold_bars+1,len(f))):
            row=f.iloc[j]
            hit_stop=(row.low<=stop if sign==1 else row.high>=stop)
            hit_target=(row.high>=t1 if sign==1 else row.low<=t1)
            if hit_stop:result='SL';exit_price=stop;exit_bar=j;break
            if hit_target:result='T1';exit_price=t1;exit_bar=j;break
        if result is None:
            exit_bar=min(i+hold_bars,len(f)-1);exit_price=float(f.close.iloc[exit_bar]);result='EXPIRED'
        fee=(abs(entry)+abs(exit_price))*costs_bps/10000
        r=(sign*(exit_price-entry)-fee)/risk
        trades.append({'entry_bar':str(f.index[i]),'exit_bar':str(f.index[exit_bar]),'outcome':result,'r':r})
        i=exit_bar+1 # one position at a time
    n=len(trades);wins=sum(x['r']>0 for x in trades);gross_wins=sum(max(0,x['r']) for x in trades);gross_losses=sum(max(0,-x['r']) for x in trades)
    cum=0;peak=0;max_dd=0
    for t in trades:
        cum+=t['r'];peak=max(peak,cum);max_dd=min(max_dd,cum-peak)
    pf=gross_wins/gross_losses if gross_losses else None
    # Gate requires a meaningful sample and observed net profitability after costs.
    eligible=n>=30 and pf is not None and pf>1.2 and cum>0 and max_dd>-12
    return dict(strategy=name,version=version,tested_at=datetime.now(timezone.utc).isoformat(),samples=n,
        win_rate=round(100*wins/n,2) if n else None,
        profit_factor=round(pf,3) if pf is not None else None,
        drawdown_pct=None, # measuring drawdown in R, not misleading capital-percent terms
        avg_r=round(cum/n,3) if n else None,net_r=round(cum,3),
        eligible=int(eligible),notes=f'Max drawdown {max_dd:.2f}R; costs {costs_bps} bps round-trip approximation; unvalidated unless eligible')
