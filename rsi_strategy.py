"""Completed-period RSI pullback screen plus closed-15m double confirmation."""
import numpy as np
import pandas as pd
from engine import IST,bars,features
from strategy_rules import empty
from discovery_rules import rsi14,completed_periods,levels
NAME='RSI pullback + confirmation'

def confirm_rebound(b,now):
 now=pd.Timestamp(now).tz_convert(IST)
 b=b[b.index+pd.Timedelta(minutes=15)<=now]
 if len(b)<60:return None,'Need 60 completed 15m candles for confirmation'
 stamp=b.index[-1]+pd.Timedelta(minutes=15)
 if stamp.date()!=now.date() or not 0<=(now-stamp).total_seconds()<=600:return None,'Waiting for a fresh completed 15m candle'
 # Three recent contiguous bars are required for a usable local structural low.
 if not b.tail(3).index.equals(pd.date_range(end=b.index[-1],periods=3,freq='15min')):return None,'Recent 15m candles are not contiguous'
 x=features(b).iloc[-1];previous=b.iloc[-2]
 price=bool(x.close>x.open and x.close>x.vwap and x.close>x.ema9>x.ema21 and x.close>previous.high)
 strength=bool(x.rvol>=1.5 and x.adx>=20)
 info=dict(price_confirmation='PASS' if price else 'WAIT',strength_confirmation='PASS' if strength else 'WAIT',volume_ratio=float(x.rvol),adx=float(x.adx),vwap=float(x.vwap),ema9=float(x.ema9),ema21=float(x.ema21),confirmation_at=stamp.isoformat())
 why=[]
 if not price:why.append('Price confirmation: need green 15m close above VWAP / EMA9 > EMA21 / preceding high')
 if not strength:why.append(f'Strength confirmation: RVOL {x.rvol:.2f}x / ADX {x.adx:.1f}; need >=1.5x / >=20')
 return (b,x,info),'; '.join(why)

def scan(d,f,now):
 now=pd.Timestamp(now).tz_convert(IST);out=empty(NAME,'Waiting for daily history')
 if d is None or len(d)<400:return empty(NAME,'Monthly RSI warmup: multi-year daily history required')
 d=d[d.index.normalize()<now.normalize()].sort_index()
 if d.empty:return out
 m,w=completed_periods(d,now)
 if len(m)<30 or len(w)<30:return empty(NAME,'Need 30 completed monthly and weekly candles')
 mr=float(rsi14(m.close).iloc[-1]);wr=float(rsi14(w.close).iloc[-1]);dr=float(rsi14(d.close).iloc[-1])
 out.update(monthly_rsi=mr,weekly_rsi=wr,daily_rsi=dr,rsi_asof=str(d.index[-1].date()),monthly_asof=str(m.index[-1].date()),weekly_asof=str(w.index[-1].date()))
 if not (np.isfinite([mr,wr,dr]).all() and mr>60 and wr>60 and 39<dr<44):
  out['reason']=f'RSI filter: monthly {mr:.2f}, weekly {wr:.2f}, daily {dr:.2f}; need >60 / >60 / strictly 39–44';return out
 out.update(matched=True,strategy_status='WATCHLIST',reason='RSI conditions pass; waiting for double confirmation')
 if now.weekday()>4 or not 570<=now.hour*60+now.minute<915:
  out['reason']='RSI conditions pass; intraday entry window closed (09:30–15:15 IST)';return out
 b=bars(f,15,now);checked,reason=confirm_rebound(b,now)
 if checked is None:out['reason']=reason;return out
 b,x,info=checked;out.update(info)
 if reason:out['reason']=reason;return out
 r=levels(NAME,float(x.close),float(b.low.tail(3).min()),float(x.atr),now,'Both confirmations passed: price rebound + volume/trend strength',b.iloc[:-1].tail(60))
 r.update({k:out[k] for k in ('monthly_rsi','weekly_rsi','daily_rsi','rsi_asof','monthly_asof','weekly_asof')});r.update(info)
 r.update(trigger_at=info['confirmation_at'],valid_until=min(now+pd.Timedelta(minutes=5),now.normalize()+pd.Timedelta(hours=15,minutes=15)).isoformat(),stop_basis='15m closing basis below last three completed 15m lows, with max(₹0.05, 0.1 ATR) buffer',evidence=['Completed monthly RSI >60','Completed weekly RSI >60','Completed daily RSI strictly 39–44','15m green close + prior-high break + VWAP + EMA9/21','15m RVOL >=1.5 and ADX >=20'])
 return r
