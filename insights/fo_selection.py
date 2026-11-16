"""Rank qualified F&O research plans; never represent rule scores as win rates."""
import math

LIMIT=8
MIN_SCORE=75

def quality(plan,chain,smc,buildup):
    try:
        leg=next(v[plan['direction'].lower()] for k,v in chain['oc'].items() if float(k)==float(plan['strike']))
        bid,ask,volume,oi=(float(leg[k]) for k in ('top_bid_price','top_ask_price','volume','oi'))
        rv=float(smc['rvol']);growth=float(buildup['oi_change_pct'])
        if not all(math.isfinite(v) for v in (bid,ask,volume,oi,rv,growth)):return None
        if not (0<bid<=ask and volume>0 and oi>0 and rv>=1.5 and growth>=1.5):return None
        if not str(plan.get('security_id','')).strip():return None
        spread=100*(ask-bid)/ask
        if spread>2:return None
        score=round(60+min(15,rv*5)+min(15,growth*5)+max(0,10*(1-spread/2)),1)
        if score<MIN_SCORE:return None
        return dict(selection_score=score,selection_score_type='RULE QUALITY / 100 — NOT WIN PROBABILITY',
                    option_spread_pct=round(spread,3),option_volume=volume,option_oi=oi,
                    selection_reasons=['Futures OI + price, 5m breakout and 15m/60m trend gates passed',
                                       f'Cash RVOL {rv:.2f}x; futures OI change {growth:.2f}%; option spread {spread:.2f}%'])
    except (KeyError,TypeError,ValueError,StopIteration):return None


def top_eight(plans):
    """One direction and one contract per underlying; reject conflicting directions."""
    groups={}
    for plan in plans:
        key=''.join(str(plan.get('underlying','')).upper().split())
        score=plan.get('selection_score')
        if not key or not isinstance(score,(int,float)) or not math.isfinite(score) or score<MIN_SCORE:continue
        groups.setdefault(key,[]).append(plan)
    chosen=[]
    for items in groups.values():
        if len({p.get('direction') for p in items})!=1:continue
        chosen.append(sorted(items,key=lambda p:(-p['selection_score'],p.get('option_spread_pct',99),str(p.get('expiry','')),str(p.get('security_id',''))))[0])
    chosen.sort(key=lambda p:(-p['selection_score'],p.get('option_spread_pct',99),p['underlying']))
    return [dict(p,selection_rank=i+1) for i,p in enumerate(chosen[:LIMIT])]
