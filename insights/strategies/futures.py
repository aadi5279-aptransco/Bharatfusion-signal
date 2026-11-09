"""Futures OI build-up strategy, driven by licensed Dhan futures data."""
from __future__ import annotations
import math
from insights.indicators import risk_levels

NAME='Futures OI buildup'
VERSION='1.0'


def buildup(futures,symbol,now):
    if futures is None or len(futures)<21 or 'oi' not in futures:return None
    f=futures.sort_index();current=f.iloc[-1];prev=f.iloc[-2]
    price_change=float(current.close/prev.close-1) if prev.close else 0
    oi_change=float(current.oi/prev.oi-1) if prev.oi else 0
    if not math.isfinite(price_change) or not math.isfinite(oi_change) or oi_change<.015:return None
    if price_change>=.004:side='CE';desc='Futures price up >=0.4% with OI up >=1.5%'
    elif price_change<=-.004:side='PE';desc='Futures price down >=0.4% with OI up >=1.5%'
    else:return None
    # This produces an UNDERLYING plan only. Contract premium plans require
    # separate verified chain and premium-history risk rules.
    return dict(strategy=NAME,version=VERSION,symbol=symbol,direction=side,
       signal_at=str(f.index[-1]),reasons=[desc],price_change_pct=round(price_change*100,2),
       oi_change_pct=round(oi_change*100,2),confidence=60,status='WATCH / OPTION CHAIN NOT VALIDATED')
