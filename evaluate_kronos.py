"""Chronological, non-overlapping forecast evaluation; not a trading backtest.
CSV: timestamp,open,high,low,close,volume; timestamp must include +05:30 or Z.
"""
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
from engine import bars,clean,IST
from kronos_adapter import Forecaster


def evaluate(f,forecaster,minutes=3,horizon=10,step_limit=30):
    b=bars(clean(f),minutes,f.index.max()+pd.Timedelta(minutes=1))
    if len(b)<300: raise ValueError('Need at least 300 complete bars')
    # Final 30% is a chronological evaluation section; no tuning on this section.
    start=max(256,int(len(b)*.7)); records=[]
    for i in range(start,len(b)-horizon+1,horizon):
        past=b.iloc[:i]; future=b.iloc[i:i+horizon]
        if past.index[-1].date()!=future.index[-1].date(): continue
        expected=pd.date_range(past.index[-1]+pd.Timedelta(minutes=minutes),periods=horizon,freq=f'{minutes}min')
        if not future.index.equals(expected): continue
        prediction=forecaster.predict(past,minutes,horizon,paths=3)
        pred=np.array(prediction['median']); actual=future.close.to_numpy(); last=float(past.close.iloc[-1])
        records.append(dict(asof=past.index[-1].isoformat(),mae=float(np.mean(abs(pred-actual))),
                            persistence_mae=float(np.mean(abs(last-actual))),
                            direction_correct=bool(np.sign(pred[-1]-last)==np.sign(actual[-1]-last)),
                            forecast_change_pct=float((pred[-1]/last-1)*100),actual_change_pct=float((actual[-1]/last-1)*100)))
        if len(records)>=step_limit:break
    if not records:raise ValueError('No valid same-session evaluation windows')
    mae=np.mean([r['mae'] for r in records]); baseline=np.mean([r['persistence_mae'] for r in records])
    return dict(windows=len(records),mean_absolute_price_error=float(mae),persistence_error=float(baseline),
                beats_persistence=bool(mae<baseline),direction_hit_rate=float(np.mean([r['direction_correct'] for r in records])),
                status='RESEARCH ONLY — NO PROFITABILITY VALIDATION',
                limitations='Fixed pretrained checkpoint. Training-data overlap is unknown. No costs, fills, position sizing or P&L simulated. Window count is capped; not proof of edge.',
                windows_detail=records)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('csv'); p.add_argument('--minutes',type=int,choices=[3,5],default=3)
    p.add_argument('--horizon',type=int,default=10); p.add_argument('--windows',type=int,default=30); p.add_argument('--output',default='kronos_evaluation.json'); a=p.parse_args()
    f=pd.read_csv(a.csv)
    raw=f.pop('timestamp').astype(str)
    if not raw.str.contains(r'(Z|[+-]\d\d:\d\d)$',regex=True).all():p.error('Every timestamp must include its timezone; no naive timestamp assumptions')
    f.index=pd.DatetimeIndex(pd.to_datetime(raw,utc=True)).tz_convert(IST)
    report=evaluate(f,Forecaster(),a.minutes,a.horizon,a.windows)
    Path(a.output).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='windows_detail'},indent=2))
