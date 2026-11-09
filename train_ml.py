"""Train research candidates from your own timezone-aware 1-minute CSV."""
import argparse,json,os
from pathlib import Path
import pandas as pd
from engine import clean,bars,IST
from ml_engine import train
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('csv');p.add_argument('--symbol',required=True);p.add_argument('--minutes',type=int,choices=[3,5,15,60,240],default=3);p.add_argument('--direction',choices=['LONG','SHORT'],default='LONG');p.add_argument('--trials',type=int,default=12)
 p.add_argument('--root',default=str(Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))/'BharatSignalFusion'));a=p.parse_args()
 f=pd.read_csv(a.csv);ts=f.pop('timestamp').astype(str)
 if not ts.str.contains(r'(?:Z|[+-]\d\d:\d\d)$').all():p.error('Each timestamp must include timezone')
 f.index=pd.DatetimeIndex(pd.to_datetime(ts,utc=True)).tz_convert(IST);f=clean(f)
 b=bars(f,a.minutes,f.index[-1]+pd.Timedelta(minutes=1));r=train(b,a.root,a.symbol,a.minutes,a.direction,trials=a.trials)
 print(json.dumps(r,indent=2))
