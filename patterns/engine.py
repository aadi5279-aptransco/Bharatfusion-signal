"""Pure as-of pattern evaluation. No network, clock reads, persistence or orders."""
from __future__ import annotations
from datetime import datetime, timedelta
from math import isfinite
from statistics import mean
from zoneinfo import ZoneInfo
from . import candles, charts
from .config import PatternConfig
from .math import atr_series, ema, rounded
from .types import Bar, Context, Pattern, Timeframe

IST=ZoneInfo('Asia/Kolkata')
TIMEFRAMES=('5m','15m','1h','daily','weekly','monthly')


def _aware(t: datetime) -> bool:
    return isinstance(t,datetime) and t.tzinfo is not None and t.utcoffset() is not None


def closed_bars(bars: tuple[Bar,...], timeframe: Timeframe, asof: datetime) -> tuple[Bar,...]:
    if timeframe not in TIMEFRAMES or not _aware(asof):raise ValueError('Supported timeframe and aware asof required')
    # Ignore unavailable future data before evaluating any price/volume features.
    if any(not _aware(b.time) or not _aware(b.closed_at) for b in bars):raise ValueError('Aware bar times required')
    selected=tuple(b for b in bars if b.closed_at<=asof)
    previous=None
    for b in selected:
        if b.closed_at<=b.time or (previous is not None and b.time<previous):
            raise ValueError('Bars must be ordered, unique and non-overlapping')
        previous=b.closed_at
        if not all(isfinite(x) for x in (b.open,b.high,b.low,b.close,b.volume)):
            raise ValueError('Nonfinite OHLCV')
        if min(b.open,b.high,b.low,b.close)<=0 or b.volume<0 or b.high<max(b.open,b.close,b.low) or b.low>min(b.open,b.close,b.high):
            raise ValueError('Invalid OHLCV')
        local=b.time.astimezone(IST);end=b.closed_at.astimezone(IST)
        if timeframe in ('5m','15m','1h'):
            minutes={'5m':5,'15m':15,'1h':60}[timeframe]
            if b.closed_at-b.time!=timedelta(minutes=minutes):raise ValueError('Partial intraday interval')
            startmin=local.hour*60+local.minute
            if local.second or local.microsecond or startmin<555 or (startmin-555)%minutes or end.date()!=local.date() or (end.hour,end.minute)>(15,30):
                raise ValueError('Off-grid or outside regular session; special sessions need explicit separate adapter')
        elif timeframe=='daily':
            if local.date()!=end.date() or (end.hour,end.minute)<(15,30):raise ValueError('Partial daily bar')
        elif timeframe=='weekly':
            # Adapter must supply a fully completed Mon-Sun bucket; no Friday intraday shortcut.
            if end!=local+timedelta(days=7) or local.weekday()!=0 or local.hour or local.minute or local.second or local.microsecond:raise ValueError('Partial weekly bucket')
        elif timeframe=='monthly':
            next_month=local.replace(year=local.year+int(local.month==12),month=1 if local.month==12 else local.month+1,day=1)
            if local.day!=1 or local.hour or local.minute or local.second or local.microsecond or end!=next_month:raise ValueError('Partial monthly bucket')
    return selected


def _eligible(bars: tuple[Bar,...], start: int, end: int, tf: Timeframe, cfg: PatternConfig) -> list[str]:
    reasons=[]
    if any(b.circuit_locked for b in bars[start:end+1]):reasons.append('Circuit-locked bar')
    if any(not b.eligible for b in bars[start:end+1]):reasons.append('Instrument eligibility unverified or blocked')
    if any(b.volume<cfg.min_volume or b.close*b.volume<cfg.min_turnover for b in bars[start:end+1]):reasons.append('Illiquid pattern/confirmation bar')
    if tf in ('5m','15m','1h'):
        day=bars[end].time.astimezone(IST).date()
        first=next(i for i,b in enumerate(bars) if b.time.astimezone(IST).date()==day)
        if end-first<cfg.ignore_opening_bars:reasons.append('Opening-bar caution')
        step=timedelta(minutes={'5m':5,'15m':15,'1h':60}[tf])
        for u,v in zip(bars[start:end+1],bars[start+1:end+1]):
            if u.time.astimezone(IST).date()==v.time.astimezone(IST).date() and v.time-u.time!=step:
                reasons.append('Missing bar inside pattern');break
    return reasons


def _context(bars: tuple[Bar,...], start: int, end: int, a: float, cfg: PatternConfig, ctx: Context) -> tuple[int,list[str]]:
    prior=bars[:start];levels=list(ctx.levels)
    if len(prior)<cfg.trend_period:return 0,[]
    change=prior[-1].close-prior[-cfg.trend_period].close
    trend=1 if change>cfg.trend_atr*a else -1 if change<-cfg.trend_atr*a else 0
    recent=prior[-cfg.range_bars:]
    levels.extend((('prior support',min(b.low for b in recent)),('prior resistance',max(b.high for b in recent))))
    levels.append(('key EMA',ema([b.close for b in prior],min(20,len(prior)))))
    day=bars[start].time.astimezone(IST).date()
    previous=[b for b in prior if b.time.astimezone(IST).date()<day]
    if previous:
        pd=previous[-1].time.astimezone(IST).date();previous=[b for b in previous if b.time.astimezone(IST).date()==pd]
        levels.extend((('previous-day high',max(b.high for b in previous)),('previous-day low',min(b.low for b in previous))))
    today=[b for b in prior if b.time.astimezone(IST).date()==day]
    volume=sum(b.volume for b in today)
    if volume>0:levels.append(('prior session VWAP',sum((b.high+b.low+b.close)/3*b.volume for b in today)/volume))
    low=min(b.low for b in bars[start:end+1]);high=max(b.high for b in bars[start:end+1])
    near=[name for name,value in levels if low-cfg.location_atr*a<=value<=high+cfg.location_atr*a]
    return trend,near


def _plan(sign: int, trigger: float, stop: float, height: float, ctx: Context) -> tuple[float|None,float|None,float|None]:
    if not sign:return None,None,None
    entry=rounded(trigger,ctx.tick_size,sign==1)
    sl=rounded(stop,ctx.tick_size,sign==-1)
    target=rounded(trigger+sign*height,ctx.tick_size,sign==-1)
    if min(entry,sl,target)<=0 or sign*(entry-sl)<=0 or sign*(target-entry)<=0:return None,None,None
    return entry,sl,target


def scan(bars: tuple[Bar,...], timeframe: Timeframe, asof: datetime,
         config: PatternConfig | None=None, context: Context | None=None) -> tuple[Pattern,...]:
    cfg=config or PatternConfig();ctx=context or Context()
    if not _aware(asof):raise ValueError('Aware asof required')
    if not isfinite(ctx.tick_size) or ctx.tick_size<=0:raise ValueError('Positive verified tick required')
    if ctx.known_at is not None and (not _aware(ctx.known_at) or ctx.known_at>asof):raise ValueError('Future context')
    if ctx.levels and ctx.known_at is None:raise ValueError('External levels need known_at')
    if any(not isfinite(v) or v<=0 for _,v in ctx.levels):raise ValueError('Invalid context level')
    b=closed_bars(tuple(bars),timeframe,asof)
    if len(b)<max(cfg.volume_period+3,cfg.atr_period+3,cfg.trend_period+3):return ()
    atr=atr_series(b,cfg.atr_period);t=len(b)-1;a=atr[t-1]
    if a is None or a<=0:return ()
    out=[]
    ends=(t-1,t) if cfg.require_confirmation else (t,)
    for end in ends:
        base_atr=atr[end-1]
        if base_atr is None or base_atr<=0:continue
        for shape in candles.detect(b,end,base_atr,cfg):
            trend,near=_context(b,shape.start,end,base_atr,cfg,ctx)
            if not trend or (shape.trend and trend!=shape.trend) or not near:continue
            sign=shape.sign
            hi=max(x.high for x in b[shape.start:end+1]);lo=min(x.low for x in b[shape.start:end+1])
            blockers=_eligible(b,shape.start,t,timeframe,cfg)
            if not sign and end<t:
                sign=1 if b[t].close>hi else -1 if b[t].close<lo else 0
            level=hi if sign==1 else lo
            next_close=end<t and (b[t].close>hi if sign==1 else b[t].close<lo if sign==-1 else False)
            if cfg.require_confirmation and not next_close:blockers.append('Await next-bar close beyond pattern')
            baseline=mean(x.volume for x in b[max(0,t-cfg.volume_period):t])
            if cfg.require_volume and (baseline<=0 or b[t].volume<cfg.volume_multiple*baseline):blockers.append('Volume confirmation missing')
            if not sign:blockers.append('Neutral shape has no directional entry')
            trigger=max(level,b[t].close)+cfg.breakout_atr*a if sign==1 else min(level,b[t].close)-cfg.breakout_atr*a
            stop=(lo-cfg.stop_atr*a if sign==1 else hi+cfg.stop_atr*a)
            entry,sl,target=_plan(sign,trigger,stop,abs(trigger-stop)*cfg.candle_reward_risk,ctx)
            if entry is None:blockers.append('Invalid rounded risk plan')
            confirmed=not blockers
            evidence=(f'Prior trend: {"UP" if trend>0 else "DOWN"}', 'Location: '+', '.join(near),
                      'Opening gaps: '+('present' if shape.gap else 'not required' if not cfg.require_gaps else 'strict'),
                      'Entry is a next-bar conditional reference, not a fill',*blockers)
            out.append(Pattern(shape.name,'BUY' if sign==1 else 'SELL' if sign==-1 else 'NEUTRAL',
                80. if confirmed else 40.,t,b[t].time,confirmed,evidence,
                entry if confirmed else None,sl if confirmed else None,target if confirmed else None,
                f'Invalid below {lo:g}' if sign==1 else f'Invalid above {hi:g}',b[shape.start].time,b[end].time,
                (('pattern_high',hi),('pattern_low',lo)),(),timeframe,b[t].closed_at))
    for setup in charts.detect(b,timeframe,a,cfg,ctx):
        sign=setup.sign;trigger=setup.trigger+sign*cfg.breakout_atr*a
        blockers=_eligible(b,setup.start,t,timeframe,cfg)
        # A breakout must first occur now, not be retrospectively assigned to an earlier bar.
        boundary=next((line for line in setup.lines if line[0]==('resistance' if sign==1 else 'support')),None)
        if boundary is None:boundary=next((line for line in setup.lines if line[0]=='neckline'),None)
        previous_trigger=trigger-(boundary[1] if boundary else 0)
        crossed=sign*(b[t].close-trigger)>0 and sign*(b[t-1].close-previous_trigger)<=0
        if not crossed:blockers.append('Await first closed breakout')
        baseline=mean(x.volume for x in b[t-cfg.volume_period:t])
        if baseline<=0 or b[t].volume<cfg.breakout_volume*baseline:blockers.append('Breakout volume expansion missing')
        invalid=sign*(b[t].close-setup.stop)<=0
        if invalid:continue
        proposed=b[t].close+sign*cfg.breakout_atr*a
        remaining=sign*(setup.trigger+sign*setup.height-proposed)
        entry,sl,target=_plan(sign,proposed,setup.stop-sign*cfg.stop_atr*a,remaining,ctx)
        if entry is None:blockers.append('Invalid rounded risk plan')
        confirmed=not blockers
        evidence=('Confirmed pivots / prior closed range only','Measured-move target; not a fill or forecast',*blockers)
        out.append(Pattern(setup.name,'BUY' if sign==1 else 'SELL',85. if confirmed else 45.,t,b[t].time,
            confirmed,evidence,entry if confirmed else None,sl if confirmed else None,target if confirmed else None,
            f'Invalid through structural boundary {setup.stop:g}',b[setup.start].time,b[setup.end].time,
            (('breakout',trigger),('pattern_stop',setup.stop),('measured_height',setup.height)),setup.lines,timeframe,b[t].closed_at))
    # A confirmation takes precedence over the same shape's new forming instance.
    unique={}
    for row in sorted(out,key=lambda p:(not p.confirmed,-p.score,p.pattern,p.direction,p.start)):
        unique.setdefault((row.pattern,row.direction),row)
    return tuple(unique.values())
