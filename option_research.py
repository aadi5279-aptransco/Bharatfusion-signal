"""ATM contract validation and explicitly approximate premium scenarios. No orders."""
import math
import pandas as pd
from engine import IST


def choose_atm(chain,contracts,expiry,side,now):
 data=chain.get('data',{});spot=float(data.get('last_price',0));oc=data.get('oc',{})
 if not math.isfinite(spot) or spot<=0 or not oc:raise ValueError('Option-chain spot/strikes missing')
 strikes=sorted(float(k) for k in oc if float(k)>0)
 strike=min(strikes,key=lambda k:(abs(k-spot),k))
 raw=next(v for k,v in oc.items() if float(k)==strike).get(side.lower(),{})
 sid=str(raw.get('security_id',''))
 contract=next((c for c in contracts if c['id']==sid and c['expiry']==expiry and c['side']==side and abs(c['strike']-strike)<.001),None)
 if not contract or contract['lot']<=0:raise ValueError('Chain security ID/expiry/strike/lot does not match instrument master')
 if pd.Timestamp(expiry).date()<=pd.Timestamp(now).date():raise ValueError('Expiry-day stock options excluded')
 return contract,raw,spot


def premium_plan(strategy,contract,chain_leg,quote,now,capital=100000,budget=2000):
 now=pd.Timestamp(now);t=pd.Timestamp(quote.get('last_trade_time'))
 if t.tzinfo is None:t=t.tz_localize(IST)
 if not 0<=(now-t).total_seconds()<=120:raise ValueError('Option last trade is stale')
 buys=quote['depth']['buy'];sells=quote['depth']['sell'];bid=float(buys[0]['price']);ask=float(sells[0]['price'])
 if not all(math.isfinite(x) for x in (bid,ask)) or bid<=0 or ask<bid or (ask-bid)/ask>.05:raise ValueError('Invalid/wide option spread (>5%)')
 if float(quote.get('volume',0))<=0:raise ValueError('No traded option volume')
 delta=float(chain_leg.get('greeks',{}).get('delta',float('nan')));gamma=float(chain_leg.get('greeks',{}).get('gamma',0))
 sign=1 if contract['side']=='CE' else -1
 if not math.isfinite(delta) or not 0<sign*delta<=1 or not math.isfinite(gamma) or gamma<0:raise ValueError('Missing/invalid option Greeks')
 current=float(strategy['underlying_now'])
 def estimate(level):
  move=float(level)-current
  return max(0.,ask+delta*move+.5*gamma*move*move)
 stop=estimate(strategy['underlying_sl']);t1=estimate(strategy['underlying_t1']);t2=estimate(strategy['underlying_t2'])
 if not 0<stop<ask<t1<=t2:raise ValueError('Structure/Greeks do not produce ordered premium scenarios')
 lot=int(contract['lot']);risk=(ask-stop)*lot+(ask-bid)*lot
 # Maximum ONE lot, and reject if structural estimated risk does not fit. Never tighten structure to force entry.
 allowed=lot if risk<=min(float(budget),2000) and ask*lot<=capital else 0
 money_stop=max(0.,ask-2000/lot)
 return dict(atm_strike=contract['strike'],expiry=contract['expiry'],option_id=contract['id'],option_side=contract['side'],lot_size=lot,
             premium_entry=ask,premium_sl_est=stop,premium_t1_est=t1,premium_t2_est=t2,estimated_risk=risk,quantity=allowed,
             money_stop_alert=money_stop,quote_at=t.isoformat(),option_bid=bid,
             option_note='Delta/gamma scenarios only; assume unchanged IV/time and futures-spot basis. Not executable target guarantees. Closing SL and gaps can exceed ₹2,000.')
