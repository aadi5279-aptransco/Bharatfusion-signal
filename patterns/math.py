"""Causal numerical primitives; no dataframe shifts or global mutable settings."""
from __future__ import annotations
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from statistics import mean
from .types import Bar, Pivot
from .config import PatternConfig

def atr_series(bars: tuple[Bar, ...], n: int) -> list[float | None]:
    tr = [max(b.high-b.low, abs(b.high-bars[i-1].close), abs(b.low-bars[i-1].close))
          if i else b.high-b.low for i,b in enumerate(bars)]
    out: list[float | None] = [None]*len(bars)
    if len(tr)>=n:
        value=mean(tr[:n]);out[n-1]=value
        for i in range(n,len(tr)):
            value=(value*(n-1)+tr[i])/n;out[i]=value
    return out

def ema(values: list[float], n: int) -> float:
    value=mean(values[:n])
    for x in values[n:]:value+=(x-value)*2/(n+1)
    return value

def rounded(value: float, tick: float, up: bool) -> float:
    d=Decimal(str(tick))
    return float((Decimal(str(value))/d).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR)*d)

def fit(points: list[tuple[int,float]]) -> tuple[float,float]:
    mx=mean(x for x,y in points);my=mean(y for x,y in points)
    denom=sum((x-mx)**2 for x,y in points)
    slope=sum((x-mx)*(y-my) for x,y in points)/denom if denom else 0.
    return slope,my-slope*mx

def pivots(bars: tuple[Bar,...], cfg: PatternConfig) -> tuple[Pivot,...]:
    """Append-only alternating pivots. Never move an already confirmed extremum.

    Confirmation requires N right bars AND ATR-sized movement from the previous
    opposite pivot. Same-side candidates are ignored, never retroactively replaced.
    """
    atr=atr_series(bars,cfg.atr_period);out=[]
    for i in range(cfg.pivot_left,len(bars)-cfg.pivot_right):
        a=atr[i]
        if a is None or a<=0:continue
        window=bars[i-cfg.pivot_left:i+cfg.pivot_right+1]
        high=all(bars[i].high>x.high for j,x in enumerate(window) if j!=cfg.pivot_left)
        low=all(bars[i].low<x.low for j,x in enumerate(window) if j!=cfg.pivot_left)
        if high==low:continue # Outside-bar ambiguity is not resolved with hindsight.
        kind='HIGH' if high else 'LOW';price=bars[i].high if high else bars[i].low
        if out and (out[-1].kind==kind or abs(price-out[-1].price)<cfg.zigzag_atr*a):continue
        out.append(Pivot(i,price,kind,i+cfg.pivot_right))
    return tuple(out)
