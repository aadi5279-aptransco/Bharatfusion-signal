"""Read-only, point-in-time audit of a user-supplied reference stock list."""
import argparse
import json
from pathlib import Path
import pandas as pd


def compare(service, symbols, now):
    from insights.strategies.premarket import evaluate
    from insights.premarket_setups import prepare,fetch_daily
    from insights.premarket_followthrough import prior_session
    from insights.service import _holiday_set
    from insights.brokers.dhan import BrokerUnavailable
    expected=prior_session(now,_holiday_set()).isoformat()
    rows=[]
    for symbol in symbols:
        item=service._lookup(symbol)
        if not item or item.get('kind')!='stock':
            rows.append(dict(symbol=symbol,status='NOT MAPPED'));continue
        try:
            frame=fetch_daily(service.broker,item,now)
            prepare(frame,now)
            row=evaluate(frame,item['symbol'],now)
            if row['previous_session']!=expected:
                rows.append(dict(symbol=symbol,status='STALE',expected=expected,actual=row['previous_session']));continue
            rows.append(dict(requested_symbol=symbol,status='OUR RULES MATCH' if row['setups'] else 'OUR RULES DO NOT MATCH',evidence=row))
        except (BrokerUnavailable,ValueError,TypeError,KeyError):
            rows.append(dict(symbol=symbol,status='DATA UNAVAILABLE',reason='Check licensed history, mapping, entitlement and required 55 daily bars'))
    return dict(asof=now.isoformat(),expected_daily_session=expected,rows=rows,
                limitation='Tests our disclosed rules only. Does not establish Birbull private logic, historical profitability, or current trade eligibility.')


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1]/'.env',override=False)
    from insights.config import IST
    from insights.service import InsightsService
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--date',required=True,help='Watchlist date YYYY-MM-DD; analysis cutoff is 08:00 IST')
    p.add_argument('--symbols',nargs='+',required=True)
    p.add_argument('--output',default='premarket_comparison.json')
    p.add_argument('--refresh-watchlist',action='store_true',help='Also rebuild the complete bounded pre-market watchlist cache for this date. Close the app first.')
    args=p.parse_args()
    now=pd.Timestamp(args.date+' 08:00',tz=IST)
    service=InsightsService()
    result=compare(service,args.symbols,now)
    if args.refresh_watchlist:
        batch=service.scan_premarket(now)
        result['watchlist_refresh']=dict(assessed=batch['assessed'],universe=batch['universe'],coverage_pct=batch['coverage_pct'],audit=batch['audit'])
    Path(args.output).write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
    print('Saved:',args.output)

if __name__=='__main__':main()
