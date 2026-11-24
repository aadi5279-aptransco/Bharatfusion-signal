"""Candlestick morphology only. Context/eligibility/confirmation live in engine.py."""
from __future__ import annotations
from dataclasses import dataclass
from .types import Bar
from .config import PatternConfig

CANDLE_NAMES = (
    'Doji','Dragonfly Doji','Gravestone Doji','Hammer','Inverted Hammer',
    'Hanging Man','Shooting Star','Bullish Marubozu','Bearish Marubozu','Spinning Top',
    'Bullish Engulfing','Bearish Engulfing','Piercing','Dark Cloud','Bullish Harami',
    'Bearish Harami','Tweezer Bottom','Tweezer Top','Morning Star','Evening Star',
    'Three White Soldiers','Three Black Crows','Three Inside Up','Three Inside Down')

@dataclass(frozen=True)
class Shape:
    name: str
    sign: int
    start: int
    end: int
    trend: int # Required prior direction; 0 means any non-flat trend.
    gap: bool = False


def body(b: Bar) -> float:return abs(b.close-b.open)
def span(b: Bar) -> float:return b.high-b.low
def bullish(b: Bar) -> bool:return b.close>b.open
def bearish(b: Bar) -> bool:return b.close<b.open

def detect(bars: tuple[Bar,...], end: int, atr: float, cfg: PatternConfig) -> tuple[Shape,...]:
    if end<2 or atr<=0:return ()
    x=bars[end];p=bars[end-1];a=bars[end-2]
    r=span(x);bd=body(x);out=[]
    if not cfg.min_range_atr*atr<=r<=cfg.max_range_atr*atr:return ()
    def add(name,sign,length=1,trend=None,gap=False):
        out.append(Shape(name,sign,end-length+1,end,-sign if trend is None else trend,gap))
    upper=x.high-max(x.open,x.close);lower=min(x.open,x.close)-x.low
    small=bd<=cfg.small_body*r;long=bd>=cfg.long_body*r
    is_doji=bd<=cfg.doji_body*r
    if is_doji:
        if upper<=cfg.short_wick*r and lower>=(1-cfg.small_body)*r:add('Dragonfly Doji',1)
        elif lower<=cfg.short_wick*r and upper>=(1-cfg.small_body)*r:add('Gravestone Doji',-1)
        else:add('Doji',0,trend=0)
    if cfg.doji_body*r<bd<=cfg.small_body*r and upper>bd and lower>bd:
        add('Spinning Top',0,trend=0)
    if not is_doji and small and lower>=cfg.wick_body*bd and upper<=cfg.short_wick*r:
        add('Hammer',1);add('Hanging Man',-1)
    if not is_doji and small and upper>=cfg.wick_body*bd and lower<=cfg.short_wick*r:
        add('Inverted Hammer',1);add('Shooting Star',-1)
    if bd>=cfg.marubozu_body*r:
        sign=1 if bullish(x) else -1
        add('Bullish Marubozu' if sign==1 else 'Bearish Marubozu',sign,trend=sign)
    pb=body(p)
    if pb>cfg.doji_body*span(p) and bd>pb:
        if bearish(p) and bullish(x) and x.open<=p.close and x.close>=p.open:add('Bullish Engulfing',1,2)
        if bullish(p) and bearish(x) and x.open>=p.close and x.close<=p.open:add('Bearish Engulfing',-1,2)
    gapdown=x.open<p.low-cfg.gap_atr*atr;gapup=x.open>p.high+cfg.gap_atr*atr
    if pb>=cfg.long_body*span(p):
        if bearish(p) and bullish(x) and x.open<p.close and p.close+cfg.penetration*pb<x.close<p.open and (gapdown or not cfg.require_gaps):
            add('Piercing',1,2,gap=gapdown)
        if bullish(p) and bearish(x) and x.open>p.close and p.open<x.close<p.close-cfg.penetration*pb and (gapup or not cfg.require_gaps):
            add('Dark Cloud',-1,2,gap=gapup)
        inside=min(x.open,x.close)>min(p.open,p.close) and max(x.open,x.close)<max(p.open,p.close) and bd<=cfg.small_body*pb
        if inside and bearish(p) and bullish(x):add('Bullish Harami',1,2)
        if inside and bullish(p) and bearish(x):add('Bearish Harami',-1,2)
    if abs(x.low-p.low)<=cfg.tweezer_atr*atr and bearish(p) and bullish(x):add('Tweezer Bottom',1,2)
    if abs(x.high-p.high)<=cfg.tweezer_atr*atr and bullish(p) and bearish(x):add('Tweezer Top',-1,2)
    ab=body(a)
    if ab>=cfg.long_body*span(a) and body(p)<=cfg.star_body_ratio*ab:
        down=max(p.open,p.close)<a.close-cfg.gap_atr*atr
        up=min(p.open,p.close)>a.close+cfg.gap_atr*atr
        if bearish(a) and bullish(x) and x.close>a.close+cfg.penetration*ab and long and max(p.open,p.close)<(a.open+a.close)/2 and (down or not cfg.require_gaps):
            add('Morning Star',1,3,gap=down)
        if bullish(a) and bearish(x) and x.close<a.close-cfg.penetration*ab and long and min(p.open,p.close)>(a.open+a.close)/2 and (up or not cfg.require_gaps):
            add('Evening Star',-1,3,gap=up)
    for sign,name in ((1,'Three White Soldiers'),(-1,'Three Black Crows')):
        seq=(a,p,x)
        directed=all(sign*(b.close-b.open)>0 and body(b)>=cfg.long_body*span(b) for b in seq)
        rising=all(sign*(v.close-u.close)>0 and min(u.open,u.close)<=v.open<=max(u.open,u.close) for u,v in zip(seq,seq[1:]))
        clean=all((b.high-b.close if sign==1 else b.close-b.low)<=cfg.small_body*span(b) for b in seq)
        if directed and rising and clean:add(name,sign,3)
    inside=min(p.open,p.close)>min(a.open,a.close) and max(p.open,p.close)<max(a.open,a.close) and body(p)<=cfg.small_body*ab
    if ab>=cfg.long_body*span(a) and inside:
        if bearish(a) and bullish(p) and bullish(x) and x.close>a.open:add('Three Inside Up',1,3)
        if bullish(a) and bearish(p) and bearish(x) and x.close<a.open:add('Three Inside Down',-1,3)
    return tuple(out)
