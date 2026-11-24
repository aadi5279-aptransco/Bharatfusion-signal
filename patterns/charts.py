"""Explicit bounded chart geometry on confirmed pivots and prior closed bars.

These definitions are versioned approximations of discretionary chart labels.
They never use extrema from a window extending beyond the scan clock.
"""
from __future__ import annotations
from dataclasses import dataclass
from statistics import mean
from zoneinfo import ZoneInfo
from .types import Bar, Context, Pivot, Timeframe
from .config import PatternConfig
from .math import fit, pivots

CHART_NAMES = ('Double Top','Double Bottom','Triple Top','Triple Bottom',
 'Head and Shoulders','Inverse Head and Shoulders','Rounding Bottom',
 'Rising Wedge','Falling Wedge','Bull Flag','Bear Flag','Bull Pennant','Bear Pennant',
 'Ascending Triangle','Descending Triangle','Symmetrical Triangle','Rectangle',
 'Cup and Handle','52-week Breakout','All-time High Breakout','Darvas Box','VCP',
 'NR4','NR7','Inside Bar','Opening Range Breakout')

@dataclass(frozen=True)
class Setup:
    name: str
    sign: int
    start: int
    end: int
    trigger: float
    stop: float
    height: float
    lines: tuple[tuple[str,float,float], ...] = ()


def detect(bars: tuple[Bar,...], timeframe: Timeframe, atr: float,
           cfg: PatternConfig, context: Context) -> tuple[Setup,...]:
    if len(bars)<cfg.volume_period+2 or atr<=0:return ()
    t=len(bars)-1;prior=bars[:-1];out=[];tol=cfg.equal_atr*atr
    pp=pivots(prior,cfg)
    pp=tuple(p for p in pp if t-p.index<=cfg.max_pattern_bars)
    def add(name,sign,start,end,trigger,stop,height,lines=()):
        if height>0 and sign*(trigger-stop)>0:
            out.append(Setup(name,sign,start,end,trigger,stop,height,lines))
    # Keep the last completed formation even if one new opposite pivot appears.
    for offset in (0,1):
        history=pp if offset==0 else pp[:-1]
        for count,label in ((3,'Double'),(5,'Triple')):
            if len(history)<count:continue
            seq=history[-count:];tops=seq[::2];valleys=seq[1::2]
            if seq[-1].index-seq[0].index<cfg.min_pattern_bars:continue
            if max(p.price for p in tops)-min(p.price for p in tops)>tol:continue
            is_top=tops[0].kind=='HIGH';sign=-1 if is_top else 1
            neckline=min(p.price for p in valleys) if is_top else max(p.price for p in valleys)
            extreme=max(p.price for p in tops) if is_top else min(p.price for p in tops)
            height=abs(extreme-neckline)
            if height<cfg.zigzag_atr*atr:continue
            add(label+(' Top' if is_top else ' Bottom'),sign,seq[0].index,seq[-1].confirmed_index,
                neckline,extreme,height)
        if len(history)>=5:
            seq=history[-5:];l,n1,h,n2,r=seq
            is_top=l.kind=='HIGH';sign=-1 if is_top else 1
            neck=fit([(n1.index,n1.price),(n2.index,n2.price)])
            trigger=neck[0]*t+neck[1];head_neck=neck[0]*h.index+neck[1]
            shoulders=abs(l.price-r.price)<=tol
            head=(h.price>max(l.price,r.price)+cfg.zigzag_atr*atr if is_top else h.price<min(l.price,r.price)-cfg.zigzag_atr*atr)
            if shoulders and head and r.index-l.index>=cfg.min_pattern_bars:
                add('Head and Shoulders' if is_top else 'Inverse Head and Shoulders',sign,l.index,r.confirmed_index,
                    trigger,r.price,abs(h.price-head_neck),(('neckline',*neck),))
    # Envelope fits require >=3 independently confirmed touches per boundary.
    recent=pp[-8:];hi=[(p.index,p.price) for p in recent if p.kind=='HIGH'];lo=[(p.index,p.price) for p in recent if p.kind=='LOW']
    if len(hi)>=3 and len(lo)>=3:
        sh,bh=fit(hi);sl,bl=fit(lo);start=min(hi[0][0],lo[0][0]);end=max(p.confirmed_index for p in recent)
        top=sh*t+bh;bottom=sl*t+bl;width=top-bottom
        initial=(sh*start+bh)-(sl*start+bl)
        touch=max([abs(y-(sh*x+bh)) for x,y in hi]+[abs(y-(sl*x+bl)) for x,y in lo])<=tol
        contained=all(b.high<=sh*i+bh+tol and b.low>=sl*i+bl-tol for i,b in enumerate(prior) if i>=start)
        if touch and contained and width>0 and initial>0 and t-start>=cfg.min_pattern_bars:
            flat=cfg.flat_slope_atr*atr;parallel=abs(sh-sl)<=cfg.parallel_slope_atr*atr
            contracting=width<=initial*(1-cfg.min_contraction)
            lines=(('resistance',sh,bh),('support',sl,bl))
            def pair(name):
                add(name,1,start,end,top,bottom,initial,lines)
                add(name,-1,start,end,bottom,top,initial,lines)
            if abs(sh)<=flat and abs(sl)<=flat:pair('Rectangle')
            if contracting:
                if abs(sh)<=flat and sl>flat:add('Ascending Triangle',1,start,end,top,bottom,initial,lines)
                elif abs(sl)<=flat and sh<-flat:add('Descending Triangle',-1,start,end,bottom,top,initial,lines)
                elif sh<-flat and sl>flat:pair('Symmetrical Triangle')
                elif sh>flat and sl>sh:add('Rising Wedge',-1,start,end,bottom,top,initial,lines)
                elif sl<-flat and sh<sl:add('Falling Wedge',1,start,end,top,bottom,initial,lines)
            pole_start=max(0,start-cfg.trend_period)
            pole=bars[start].close-bars[pole_start].close
            if abs(pole)>=cfg.pole_atr*atr and initial<=abs(pole)*cfg.max_flag_retrace:
                sign=1 if pole>0 else -1
                if parallel and sign*(sh+sl)<0:
                    add('Bull Flag' if sign==1 else 'Bear Flag',sign,pole_start,end,
                        top if sign==1 else bottom,bottom if sign==1 else top,abs(pole),lines)
                if contracting and sh<-flat and sl>flat:
                    add('Bull Pennant' if sign==1 else 'Bear Pennant',sign,pole_start,end,
                        top if sign==1 else bottom,bottom if sign==1 else top,abs(pole),lines)
    # Rounded base: rim symmetry, bowl depth, descending then rising third means.
    n=min(cfg.max_pattern_bars,len(prior))
    if n>=cfg.cup_min_bars:
        base=prior[-n:];start=len(prior)-n;q=n//3
        left=mean(b.close for b in base[:q]);middle=mean(b.close for b in base[q:2*q]);right=mean(b.close for b in base[2*q:])
        rim=max(b.high for b in base[:max(2,q//2)]);floor=min(b.low for b in base)
        low_at=min(range(n),key=lambda i:base[i].low)
        smooth=left-middle>=cfg.rounded_depth_atr*atr and right-middle>=cfg.rounded_depth_atr*atr and q<=low_at<2*q
        if smooth and abs(left-right)<=tol*2 and base[-1].close>middle:
            add('Rounding Bottom',1,start,t-1,rim,floor,rim-floor)
        # Cup has a separate short handle after the right rim. Search fixed causal widths.
        hn=max(3,cfg.min_pattern_bars//2)
        cup=base[:-hn];handle=base[-hn:]
        if len(cup)>=cfg.cup_min_bars:
            rim_left=max(b.high for b in cup[:3]);rim_right=max(b.high for b in cup[-3:])
            low=min(b.low for b in cup);depth=min(rim_left,rim_right)-low
            center=min(range(len(cup)),key=lambda i:cup[i].low)
            # Avoid labelling a single V-spike as a rounded cup.
            thirds=[mean(b.close for b in cup[i*len(cup)//3:(i+1)*len(cup)//3]) for i in range(3)]
            handle_low=min(b.low for b in handle);rim=max(rim_left,rim_right)
            if (abs(rim_left-rim_right)<=tol and depth>=cfg.rounded_depth_atr*atr
                and len(cup)//3<=center<2*len(cup)//3 and min(thirds[0],thirds[2])-thirds[1]>=atr
                and 0<rim-handle_low<=cfg.cup_handle_max*depth and max(b.high for b in handle)<=rim+tol):
                add('Cup and Handle',1,start,t-1,rim,handle_low,depth)
    if len(pp)>=7:
        seq=pp[-7:];swings=[abs(seq[i+1].price-seq[i].price) for i in (0,2,4)]
        rising=bars[seq[-1].index].close>bars[seq[0].index].close
        drying=mean(b.volume for b in prior[-5:])<mean(b.volume for b in prior[-cfg.volume_period:])
        if rising and drying and swings[0]>swings[1]>swings[2]>0 and swings[2]<=swings[0]*(1-cfg.min_contraction):
            seg=prior[seq[0].index:];top=max(b.high for b in seg);bottom=min(b.low for b in prior[seq[-2].index:])
            add('VCP',1,seq[0].index,t-1,top,bottom,swings[0])
    # Previous ranges only: the current breakout never defines its own level.
    for n in (4,7):
        if len(prior)>=n:
            segment=prior[-n:];last=segment[-1]
            if all(last.high-last.low<b.high-b.low for b in segment[:-1]):
                add(f'NR{n}',1,t-n,t-1,last.high,last.low,last.high-last.low)
                add(f'NR{n}',-1,t-n,t-1,last.low,last.high,last.high-last.low)
    if len(prior)>=2:
        mother,inside=prior[-2:]
        if inside.high<mother.high and inside.low>mother.low:
            for sign in (1,-1):add('Inside Bar',sign,t-2,t-1,mother.high if sign==1 else mother.low,mother.low if sign==1 else mother.high,mother.high-mother.low)
    n=cfg.darvas_bars
    if len(prior)>=n+cfg.pivot_right:
        box=prior[-n:];top=max(b.high for b in box);bottom=min(b.low for b in box)
        top_at=max(range(n),key=lambda i:box[i].high);bottom_at=min(range(n),key=lambda i:box[i].low)
        if top_at<=n-1-cfg.pivot_right and bottom_at<=n-1-cfg.pivot_right and top-bottom>=atr:
            add('Darvas Box',1,t-n,t-1,top,bottom,top-bottom)
    if timeframe=='daily' and len(prior)>=cfg.high52_bars:
        window=prior[-cfg.high52_bars:];top=max(b.high for b in window);bottom=min(b.low for b in prior[-cfg.range_bars:])
        add('52-week Breakout',1,t-cfg.high52_bars,t-1,top,bottom,top-bottom)
    if context.all_time_history and timeframe=='daily':
        top=max(b.high for b in prior);bottom=min(b.low for b in prior[-cfg.range_bars:])
        add('All-time High Breakout',1,0,t-1,top,bottom,top-bottom)
    if timeframe in ('5m','15m'):
        local=[b.time.astimezone(ZoneInfo('Asia/Kolkata')) for b in bars]
        day=local[-1].date();indices=[i for i,x in enumerate(local) if x.date()==day]
        step=5 if timeframe=='5m' else 15;n=cfg.opening_range_minutes//step
        if n and len(indices)>n:
            first=indices[:n];minutes=[local[i].hour*60+local[i].minute for i in first]
            if minutes==list(range(555,555+cfg.opening_range_minutes,step)):
                box=[bars[i] for i in first];top=max(b.high for b in box);bottom=min(b.low for b in box)
                for sign in (1,-1):add('Opening Range Breakout',sign,first[0],first[-1],top if sign==1 else bottom,bottom if sign==1 else top,top-bottom)
    return tuple(out)
