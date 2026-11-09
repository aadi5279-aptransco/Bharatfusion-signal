"""Local, purged chronological LightGBM/XGBoost research pipeline. No orders."""
from __future__ import annotations
import hashlib,json,math,os,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
from engine import features,IST

VERSION=1
BASE=['ret1','ret3','ret5','ret10','ema_gap','ema_distance','rsi','adx','atr_pct','rvol','vwap_distance','macd','body','range','minute','volatility']
BOOK=['spread_bps','book_imbalance']


def matrix(b,book=None,minutes=3):
 f=features(b);c=f.close;x=pd.DataFrame(index=f.index)
 for n in (1,3,5,10):x[f'ret{n}']=c.pct_change(n)
 x['ema_gap']=(f.ema9-f.ema21)/c;x['ema_distance']=(c-f.ema21)/c
 for k in ('rsi','adx','rvol'):x[k]=f[k]
 x['atr_pct']=f.atr/c;x['vwap_distance']=(c-f.vwap)/c
 fast=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
 x['macd']=(fast-fast.ewm(span=9,adjust=False).mean())/c
 x['body']=(c-f.open)/c;x['range']=(f.high-f.low)/c
 x['minute']=(f.index.hour*60+f.index.minute-555)/375
 x['volatility']=c.pct_change().rolling(20).std()
 for k in BOOK:x[k]=np.nan
 if book is not None and len(book):
  # Receive-time availability, backward-only join. Never fill today's depth into old candles.
  left=pd.DataFrame({'decision':b.index+pd.Timedelta(minutes=minutes)})
  right=book[BOOK].copy().sort_index();right=right[~right.index.duplicated(keep='last')];right['decision']=right.index
  joined=pd.merge_asof(left,right.reset_index(drop=True),on='decision',direction='backward',tolerance=pd.Timedelta(seconds=60))
  for k in BOOK:x[k]=joined[k].to_numpy()
 return x.replace([np.inf,-np.inf],np.nan)


def labels(b,direction='LONG',horizon=10):
 atr=features(b).atr;sign=1 if direction=='LONG' else -1;rows=[]
 for i in range(60,len(b)-horizon):
  end=i+horizon
  if b.index[i].date()!=b.index[end].date() or not np.isfinite(atr.iloc[i]) or atr.iloc[i]<=0:continue
  future=b.iloc[i+1:end+1]
  if not (future.index.to_series().diff().dropna()==b.index[i+1]-b.index[i]).all():continue
  entry=float(future.open.iloc[0]);risk=float(atr.iloc[i]);target=entry+sign*1.5*risk;stop=entry-sign*risk;outcome=0
  for bar in future.itertuples():
   hit_stop=bar.low<=stop if sign==1 else bar.high>=stop
   hit_target=bar.high>=target if sign==1 else bar.low<=target
   if hit_stop:break  # Conservative on ambiguous bars.
   if hit_target:outcome=1;break
  rows.append((b.index[i],outcome,b.index[end]))
 return pd.DataFrame(rows,columns=['timestamp','target','label_end']).set_index('timestamp')


def splits(dataset):
 n=len(dataset);a=int(n*.60);b=int(n*.75);c=int(n*.85)
 if n<800:raise ValueError('Need >=800 labelled bars per symbol/timeframe; collect more history')
 parts=[]
 for start,end,bound in ((0,a,a),(a,b,b),(b,c,c),(c,n,None)):
  part=dataset.iloc[start:end]
  if bound is not None:part=part[part.label_end<dataset.index[bound]]
  if len(part)<60 or part.target.nunique()<2:raise ValueError('Each chronological segment needs >=60 rows and both outcome classes')
  parts.append(part)
 return parts


def model_dir(root,symbol,minutes,direction):
 key=hashlib.sha256(f'{symbol}|{minutes}|{direction}'.encode()).hexdigest()[:20]
 return Path(root)/'ml_models'/key


def fit_pair(x,y,p):
 from lightgbm import LGBMClassifier
 from xgboost import XGBClassifier
 l=LGBMClassifier(n_estimators=p['trees'],learning_rate=p['lr'],num_leaves=2**p['depth'],max_depth=p['depth'],min_child_samples=30,reg_lambda=p['reg'],verbosity=-1,n_jobs=2,random_state=42)
 g=XGBClassifier(n_estimators=p['trees'],learning_rate=p['lr'],max_depth=p['depth'],reg_lambda=p['reg'],min_child_weight=5,subsample=.85,colsample_bytree=.85,tree_method='hist',n_jobs=2,random_state=42,eval_metric='logloss')
 with ThreadPoolExecutor(2) as pool:
  jobs=[pool.submit(m.fit,x,y) for m in (l,g)]
  for job in jobs:job.result()
 return l,g


def probabilities(pair,x):
 with ThreadPoolExecutor(2) as pool:
  jobs=[pool.submit(m.predict_proba,x) for m in pair]
  return [j.result()[:,1] for j in jobs]


def logit(p):return np.log(np.clip(p,1e-6,1-1e-6)/(1-np.clip(p,1e-6,1-1e-6)))
def calibrated(p,coef,intercept):return 1/(1+np.exp(-np.clip(logit(p)*coef+intercept,-30,30)))


def train(b,root,symbol,minutes=3,direction='LONG',book=None,trials=12):
 import optuna
 from sklearn.metrics import brier_score_loss,roc_auc_score,log_loss
 from sklearn.linear_model import LogisticRegression
 x=matrix(b,book,minutes);y=labels(b,direction)
 names=BASE+(BOOK if x.iloc[:int(len(x)*.6)][BOOK].notna().all(axis=1).mean()>=.8 else [])
 d=x[names].join(y,how='inner').dropna(subset=['target'])
 parts=splits(d);tr,va,ca,te=parts
 # Two expanding chronological inner folds inside the first 75%; outer test is untouched.
 inner=d.loc[:va.index[-1]]
 def objective(t):
  p=dict(trees=t.suggest_int('trees',60,180,step=60),depth=t.suggest_int('depth',2,5),lr=t.suggest_float('lr',.02,.12,log=True),reg=t.suggest_float('reg',1,12),weight=t.suggest_float('weight',.5,.8))
  losses=[]
  for frac in (.55,.75):
   cut=int(len(inner)*frac);end=min(len(inner),cut+int(len(inner)*.2))
   left=inner.iloc[:cut];left=left[left.label_end<inner.index[cut]];right=inner.iloc[cut:end]
   if left.target.nunique()<2 or right.target.nunique()<2:return 1.
   pair=fit_pair(left[names],left.target,p);lp,xp=probabilities(pair,right[names]);losses.append(brier_score_loss(right.target,p['weight']*lp+(1-p['weight'])*xp))
  return float(np.mean(losses))
 study=optuna.create_study(direction='minimize',sampler=optuna.samplers.TPESampler(seed=42));study.optimize(objective,n_trials=max(1,min(trials,40)))
 p=study.best_params;pair=fit_pair(tr[names],tr.target,p)
 lp,xp=probabilities(pair,ca[names]);raw=p['weight']*lp+(1-p['weight'])*xp
 cal=LogisticRegression(C=.1).fit(logit(raw).reshape(-1,1),ca.target)
 coef=float(cal.coef_[0,0]);intercept=float(cal.intercept_[0])
 lp,xp=probabilities(pair,te[names]);pred=calibrated(p['weight']*lp+(1-p['weight'])*xp,coef,intercept)
 baseline=float(tr.target.mean());brier=float(brier_score_loss(te.target,pred));base_brier=float(brier_score_loss(te.target,np.repeat(baseline,len(te))));auc=float(roc_auc_score(te.target,pred))
 eligible=len(te)>=100 and brier<base_brier and auc>=.55 and coef>0
 report=dict(schema=VERSION,symbol=symbol,minutes=minutes,direction=direction,feature_names=names,parameters=p,coef=coef,intercept=intercept,
   created=pd.Timestamp.now(tz=IST).isoformat(),evaluated_through=te.label_end.max().isoformat(),rows=[len(v) for v in parts],
   test_brier=brier,baseline_brier=base_brier,test_auc=auc,test_log_loss=float(log_loss(te.target,pred)),
   status='STATISTICAL PASS — RESEARCH ONLY' if eligible else 'BLOCKED: did not pass validation',eligible=eligible,
   notes='Untouched final chronological test with purged horizons. No profitability validation. Model probabilities can be miscalibrated under drift.',
   means={k:float(v) for k,v in tr[names].mean().fillna(0).items()},stds={k:float(v) for k,v in tr[names].std().fillna(0).items()})
 dest=model_dir(root,symbol,minutes,direction);dest.mkdir(parents=True,exist_ok=True)
 version=dest/uuid.uuid4().hex;version.mkdir()
 pair[0].booster_.save_model(str(version/'lightgbm.txt'));pair[1].save_model(version/'xgboost.json')
 (version/'report.json').write_text(json.dumps(report,indent=2))
 # Native JSON/text model files only; never unpickle user-provided model objects.
 manifest=dict(version=version.name)
 tmp=dest/'latest.tmp';tmp.write_text(json.dumps(manifest));os.replace(tmp,dest/'latest.json')
 return report


class ModelService:
 def __init__(self,root):self.root=root;self.loaded={}
 def predict(self,b,symbol,minutes=3,direction='LONG',book=None):
  dest=model_dir(self.root,symbol,minutes,direction)
  if not (dest/'latest.json').exists():return dict(status='NOT TRAINED',pass_gate=False)
  try:
   version=json.loads((dest/'latest.json').read_text())['version']
   if not version.isalnum():raise ValueError('Invalid model version')
   folder=dest/version;report=json.loads((folder/'report.json').read_text())
   if not report['eligible']:return dict(status='VALIDATION FAILED',pass_gate=False,report=report)
   if b.index[-1]<=pd.Timestamp(report['evaluated_through']):return dict(status='PRE-VALIDATION DATA',pass_gate=False)
   if (pd.Timestamp.now(tz=IST)-pd.Timestamp(report['created'])).total_seconds()>7*86400:return dict(status='RETRAIN DUE',pass_gate=False)
   if report.get('schema')!=VERSION or report['symbol']!=symbol or report['minutes']!=minutes or report['direction']!=direction:raise ValueError('Model metadata mismatch')
   key=str(folder)
   if key not in self.loaded:
    import lightgbm as lgb
    from xgboost import XGBClassifier
    l=lgb.Booster(model_file=str(folder/'lightgbm.txt'));g=XGBClassifier();g.load_model(folder/'xgboost.json');self.loaded[key]=(l,g)
   l,g=self.loaded[key];names=report['feature_names'];x=matrix(b,book,minutes)[names].tail(1)
   outliers=[k for k in names if report['stds'][k]>1e-9 and pd.notna(x[k].iloc[0]) and abs(float(x[k].iloc[0])-report['means'][k])/report['stds'][k]>5]
   if len(outliers)>=3:return dict(status='DRIFT / RETRAIN DUE',pass_gate=False,outliers=outliers)
   if any(k in names for k in BOOK) and x[BOOK].isna().any().any():return dict(status='BOOK DATA MISSING',pass_gate=False)
   with ThreadPoolExecutor(2) as pool:
    a=pool.submit(l.predict,x);z=pool.submit(g.predict_proba,x);lp=float(a.result()[0]);xp=float(z.result()[0,1])
   prob=float(calibrated(np.array([report['parameters']['weight']*lp+(1-report['parameters']['weight'])*xp]),report['coef'],report['intercept'])[0])
   values=l.predict(x,pred_contrib=True)[0];order=np.argsort(abs(values[:-1]))[::-1][:5]
   why=[dict(feature=names[i],contribution=float(values[i]),value=None if pd.isna(x.iloc[0,i]) else float(x.iloc[0,i])) for i in order]
   passed=prob>=.65 and lp>=.5 and xp>=.5 and abs(lp-xp)<=.2
   return dict(status='AGREE' if passed else 'WAIT / DISAGREE',pass_gate=passed,probability=prob,lightgbm=lp,xgboost=xp,
               shap=why,shap_base=float(values[-1]),shap_sum=float(values.sum()),shap_units='LightGBM raw log-odds; not causal reasons',book_enabled=all(k in names for k in BOOK),report=report)
  except ImportError:return dict(status='INSTALL ML PACKAGES',pass_gate=False)
  except Exception as exc:return dict(status='MODEL ERROR: '+type(exc).__name__,pass_gate=False)
