"""Optional official Kronos integration. Model samples are not calibrated probabilities."""
from __future__ import annotations
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from engine import IST,COLS

class ForecastError(Exception): pass


def prepare(frame,minutes=3,horizon=10,lookback=256):
    if minutes not in (3,5,15,60,240): raise ForecastError('Supported forecast intervals: 3, 5, 15, 60 or 240 minutes')
    if not 1<=horizon<=30: raise ForecastError('Horizon must be 1–30 candles')
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None: raise ForecastError('Timezone-aware closed candles required')
    f=frame.sort_index().tail(lookback).copy()
    if len(f)<60: raise ForecastError('Need at least 60 closed candles for Kronos')
    if f.index.has_duplicates: raise ForecastError('Duplicate candles')
    times=pd.Series(f.index)
    same_day=times.dt.date==times.shift().dt.date
    if (same_day & (times.diff()!=pd.Timedelta(minutes=minutes))).any(): raise ForecastError('Missing intraday candles in Kronos input')
    if not np.isfinite(f[COLS].to_numpy()).all(): raise ForecastError('Invalid input values')
    if (f[['open','high','low','close']]<=0).any().any(): raise ForecastError('Nonpositive prices')
    last=f.index[-1].tz_convert(IST)
    future=pd.date_range(last+pd.Timedelta(minutes=minutes),periods=horizon,freq=f'{minutes}min')
    # Never invent next-day sessions or holiday calendars. Forecast only today's remainder.
    end=last.normalize()+pd.Timedelta(hours=15,minutes=30)
    future=future[future+pd.Timedelta(minutes=minutes)<=end]
    if len(future)==0: raise ForecastError('No complete candles remain in this session')
    # Session times are passed in local wall-clock IST, not shifted to UTC.
    xs=pd.Series(f.index.tz_convert(IST).tz_localize(None))
    ys=pd.Series(future.tz_localize(None))
    data=f[COLS].reset_index(drop=True)
    # Dhan history has no traded turnover. Explicit approximation, not measured amount.
    data['amount']=data[['open','high','low','close']].mean(axis=1)*data.volume
    return data,xs,ys


class Forecaster:
    def __init__(self,predictor=None):
        self.predictor=predictor
        self.model_name='NeoQuasar/Kronos-mini'
    def load(self):
        if self.predictor is not None: return
        vendor=Path(__file__).parent/'vendor'/'Kronos'
        if not (vendor/'model'/'__init__.py').exists(): raise ForecastError('Official Kronos source missing; run INSTALL_KRONOS.bat')
        if str(vendor) not in sys.path: sys.path.insert(0,str(vendor))
        try:
            import torch
            from model import Kronos,KronosTokenizer,KronosPredictor
            torch.set_num_threads(max(1,min(4,torch.get_num_threads())))
            tokenizer=KronosTokenizer.from_pretrained('NeoQuasar/Kronos-Tokenizer-2k',revision='26966d0035065a0cae0ebad7af8ece35bc1fb51c')
            model=Kronos.from_pretrained(self.model_name,revision='f4e68697d9d5aed55cef5c96aabc3376bcad9f81')
            model.eval(); tokenizer.eval()
            self.predictor=KronosPredictor(model,tokenizer,device='cuda:0' if torch.cuda.is_available() else 'cpu',max_context=2048)
        except ImportError: raise ForecastError('Kronos dependencies missing. Run INSTALL_KRONOS.bat first.') from None
        except Exception: raise ForecastError('Could not load official Kronos weights. Check internet/Hugging Face access and available memory.') from None
    def predict(self,frame,minutes=3,horizon=10,paths=3,seed=42):
        if not 1<=paths<=20: raise ForecastError('Use 1–20 sample paths')
        data,xs,ys=prepare(frame,minutes,horizon)
        self.load()
        try:
            import torch
            torch.manual_seed(seed)
            if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
        except ImportError:
            if self.predictor.__class__.__module__.startswith('model'): raise ForecastError('PyTorch unavailable')
        closes=[]
        for _ in range(paths):
            try:
                pred=self.predictor.predict(df=data.copy(),x_timestamp=xs,y_timestamp=ys,pred_len=len(ys),T=1.0,top_p=.9,sample_count=1,verbose=False)
                values=pred['close'].to_numpy(dtype=float)
            except Exception: raise ForecastError('Kronos inference failed; no forecast published') from None
            if len(values)!=len(ys) or not np.isfinite(values).all() or (values<=0).any(): raise ForecastError('Kronos returned invalid prices')
            closes.append(values)
        samples=np.array(closes); median=np.median(samples,axis=0); last=float(data.close.iloc[-1])
        change=(median[-1]/last-1)*100
        result=dict(model=self.model_name,bias='UP' if change>.1 else 'DOWN' if change<-.1 else 'FLAT',
                    change_pct=float(change),last=last,median=median.tolist(),low=samples.min(axis=0).tolist(),high=samples.max(axis=0).tolist(),
                    timestamps=[t.isoformat() for t in ys],asof=frame.index[-1].isoformat(),paths=paths,
                    note='Experimental forecast; sample min/max is NOT a confidence interval. Amount is approximated. No verified NSE performance.')
        from breakout import forecast_targets
        result.update(forecast_targets(result))
        return result

if __name__=='__main__':
    import json
    from engine import demo_frame,bars
    f=demo_frame(); now=f.index[-1].normalize()+pd.Timedelta(hours=14)
    result=Forecaster().predict(bars(f,3,now),horizon=3,paths=1)
    print(json.dumps(result,indent=2))
