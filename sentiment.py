"""FinBERT local headline/report sentiment, with scope and freshness controls."""
import hashlib,math
import pandas as pd
from engine import IST

class SentimentService:
 def __init__(self):self.model=None;self.tokenizer=None;self.memo={}
 def load(self):
  if self.model is not None:return
  from transformers import AutoTokenizer,AutoModelForSequenceClassification
  self.tokenizer=AutoTokenizer.from_pretrained('ProsusAI/finbert',revision='0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031')
  self.model=AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert',revision='0bc2ac10dda6929bcb1f77ccc43c7ec5c424f031',use_safetensors=True)
  self.model.eval()
 def score(self,text):
  key=hashlib.sha256(text.encode()).hexdigest()
  if key in self.memo:return self.memo[key]
  self.load();import torch
  # Chunk by model tokens to cover longer earnings text instead of silently discarding the tail.
  tokens=self.tokenizer.encode(text,add_special_tokens=False)[:16000];probs=[]
  with torch.inference_mode():
   for i in range(0,len(tokens),480):
    batch=self.tokenizer.prepare_for_model(tokens[i:i+480],return_tensors='pt',truncation=True,max_length=512)
    batch={k:(v.unsqueeze(0) if v.ndim==1 else v) for k,v in batch.items()}
    logits=self.model(**batch).logits.softmax(-1)[0].tolist();probs.append(logits)
  if not probs:raise ValueError('Empty narrative')
  means=[sum(p[j] for p in probs)/len(probs) for j in range(len(probs[0]))]
  labels={str(v).lower():means[int(k)] for k,v in self.model.config.id2label.items()}
  result=dict(positive=labels['positive'],negative=labels['negative'],neutral=labels['neutral'])
  result['score']=result['positive']-result['negative'];result['truncated']=len(self.tokenizer.encode(text,add_special_tokens=False))>16000
  if len(self.memo)>500:self.memo.clear()
  self.memo[key]=result;return result
 def analyze(self,items,now=None):
  now=pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now);out=[];seen=set()
  for item in items:
   news=item.get('newsObject',{});title=str(news.get('title',''));text=title+'\n'+str(news.get('text',''))
   if not title or title in seen:continue
   seen.add(title)
   stamp=str(item.get('publishDate',''))
   try:
    published=pd.Timestamp(stamp)
    if published.tzinfo is None:published=published.tz_localize(IST)
    age=(now-published).total_seconds()
    if age<0 or age>86400:continue
   except Exception:continue
   try:result=self.score(text)
   except Exception as exc:return dict(status='UNAVAILABLE: '+type(exc).__name__,items=[])
   out.append(dict(title=title,symbol=item.get('smSymbol',''),category=item.get('category',''),published=stamp,
                   precision='day' if len(stamp)==10 else 'timestamp',**result))
  return dict(status='READY' if out else 'NO FRESH NEWS',items=out,fetched_at=now.isoformat())


def risk_overlay(news,symbol,direction='LONG',now=None):
 now=pd.Timestamp.now(tz=IST) if now is None else pd.Timestamp(now)
 if not news or news.get('status')!='READY':return dict(status='NEWS UNKNOWN',factor=.5,score=None)
 try:
  if (now-pd.Timestamp(news['fetched_at'])).total_seconds()>900:return dict(status='NEWS STALE',factor=.5,score=None)
 except Exception:return dict(status='NEWS UNKNOWN',factor=.5,score=None)
 macro={'indian_economy','global_economy','equity_markets','government_policy_and_regulation'}
 relevant=[x for x in news['items'] if x.get('symbol')==symbol or (not x.get('symbol') and str(x.get('category','')).lower().replace('-','_').replace(' ','_') in macro)]
 if not relevant:return dict(status='NO MATCHING NEWS',factor=.5,score=None)
 score=sum(x['score'] for x in relevant)/len(relevant);aligned=score*(1 if direction=='LONG' else -1)
 return dict(status='ADVERSE NEWS' if aligned<-.25 else 'NEWS NEUTRAL/POSITIVE',factor=0. if aligned<-.6 else .5 if aligned<-.25 else 1.,score=score,count=len(relevant))


def suggested_units(capital,risk_pct,entry,stop,factor,kind='stock'):
 if kind!='stock':return None
 values=[capital,risk_pct,entry,stop,factor]
 if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):return None
 if capital<=0 or not 0<risk_pct<=2 or entry<=0 or abs(entry-stop)<=0 or not 0<=factor<=1:return None
 return max(0,min(int(capital*risk_pct/100*factor/abs(entry-stop)),int(capital/entry)))
