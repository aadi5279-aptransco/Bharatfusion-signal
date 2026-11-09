"""User-invoked licensed Dhan historical validation; refuses unavailable setups.

Usage: python -m insights.validate --strategy intraday --symbol RELIANCE --sector NIFTYENERGY

This is a conservative research gate, not proof of future profitability.
"""
from __future__ import annotations
import argparse,json,os
from datetime import datetime
from insights.config import IST
from insights.service import InsightsService,_norm
from insights.backtest import evaluate_trades
from insights.strategies import equity


def validate_intraday(service,symbol,sector_name,now=None):
    now=now or datetime.now(IST)
    stock=service._lookup(symbol)
    nifty=service._lookup('NIFTY') or service._lookup('NIFTY 50')
    sector=next((x for x in service.instruments() if x.get('kind')=='sector' and
        (_norm(x.get('sector',''))==_norm(sector_name) or _norm(x['symbol'])==_norm(sector_name))),None)
    if not stock or not nifty or not sector:raise ValueError('Symbol, NIFTY or sector not in Dhan master')
    # Dhan's v2 intraday API permits up to 90 days in a request; use 75 calendar days.
    f=service.broker.history(stock,now,minutes=5,lookback_days=75)
    n=service.broker.history(nifty,now,minutes=5,lookback_days=75)
    sec=service.broker.history(sector,now,minutes=5,lookback_days=75)
    def snapshot_pct(data,t):
        if t not in data.index:return None
        day=data[data.index.date==t.date()]
        prior=day[day.index<=t]
        if prior.empty:return None
        return (float(prior.close.iloc[-1])/float(prior.open.iloc[0])-1)*100
    def rule(observed):
        stamp=observed.index[-1]
        ir=snapshot_pct(n,stamp);sr=snapshot_pct(sec,stamp)
        if ir is None or sr is None:return None
        return equity.intraday(observed,stock['symbol'],stamp+__import__('pandas').Timedelta(minutes=5),ir,sr)
    report=evaluate_trades(f,rule,equity.INTRADAY_NAME,equity.INTRADAY_VERSION,hold_bars=12,costs_bps=30)
    # Hold-out requirement: only a single 75-day historical window is NOT enough
    # for production validation; leave eligibility off pending true forward walk-forward.
    report['eligible']=0
    report['notes']+='; preliminary in-sample replay; independent walk-forward still REQUIRED'
    service.journal.save_backtest(report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--strategy',choices=['intraday','btst','index-options','fo-stocks'],required=True)
    parser.add_argument('--symbol',default='RELIANCE')
    parser.add_argument('--sector',default='Energy')
    args=parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    service=InsightsService()
    if args.strategy!='intraday':
        print(json.dumps({'strategy':args.strategy,'eligible':False,'reason':'Licensed point-in-time historical delivery, chain OI and/or contract premium records required. No unsupported backtest enabled.'}))
        return
    try:print(json.dumps(validate_intraday(service,args.symbol,args.sector),indent=2))
    except Exception:
        print(json.dumps({'eligible':False,'status':'UNAVAILABLE','reason':'Dhan history, instrument mapping or validation inputs unavailable'}))

if __name__=='__main__':main()
