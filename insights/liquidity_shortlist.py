"""Scheduled broad quote discovery; persistent bounded strategy universes."""
import json,math,os,time
from pathlib import Path
from datetime import datetime
from insights.config import IST,MAX_SYMBOLS

TIMES=(585,600,660,720,780,840,900)
def key(item):return str(item.get('segment',''))+':'+str(item.get('id',''))
def slot(now):
    t=now.astimezone(IST);minute=t.hour*60+t.minute
    due=[x for x in TIMES if x<=minute]
    return f'{t.date()}:{due[-1]}' if due else None

class LiquidityShortlist:
    def __init__(self,broker,root,limit=MAX_SYMBOLS,pause=1.05):
        self.broker=broker;self.path=Path(root)/'liquidity_shortlists.json';self.limit=limit;self.pause=pause
        try:self.state=json.loads(self.path.read_text())
        except (OSError,ValueError):self.state={}
        if not isinstance(self.state,dict) or not isinstance(self.state.get('lists',{}),dict):self.state={}
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.state,default=str,allow_nan=False),encoding='utf-8');os.replace(tmp,self.path)
    def selected(self,tab,now):
        if self.state.get('date')!=now.astimezone(IST).date().isoformat():return []
        return list(self.state.get('lists',{}).get(tab,[]))
    def metadata(self,now):
        s=self.state
        return {k:s.get(k) for k in ('date','attempt_slot','updated_at','status','universe','quoted','missing','error','selected_counts')}
    def refresh(self,now):
        now=now.astimezone(IST);due=slot(now)
        if due is None or due==self.state.get('attempt_slot'):return self.metadata(now)
        if self.state.get('date')!=now.date().isoformat():self.state={'date':now.date().isoformat(),'lists':{}}
        self.state.update(attempt_slot=due,status='REFRESHING',error=None)
        try:
            mapped=self.broker.instruments()
            contracts={key(x):x for x in mapped if x.get('kind')=='stock' and (x.get('future') or x.get('options'))}
            broad=self.broker.longterm_instruments() if hasattr(self.broker,'longterm_instruments') else mapped
            all_items={key(x):dict(x) for x in broad if x.get('kind')=='stock' and x.get('segment') in ('NSE_EQ','BSE_EQ')}
            for k,x in contracts.items():all_items[k]=dict(x)
            ranked=[];quoted=0;requests=0
            for segment in ('NSE_EQ','BSE_EQ'):
                group=[x for x in all_items.values() if x['segment']==segment]
                for offset in range(0,len(group),500):
                    if requests and self.pause:time.sleep(self.pause)
                    batch=group[offset:offset+500];requests+=1
                    quotes=self.broker.market_quotes(batch,now)
                    for item in batch:
                        q=quotes.get(str(item['id']),{})
                        try:
                            price=float(q['last_price']);volume=float(q['volume']);change=float(q.get('change_pct',0))
                            fetched=datetime.fromisoformat(q['fetched_at'])
                            age=(now-fetched).total_seconds()
                            if not all(math.isfinite(x) for x in (price,volume,change)) or not 0<=age<=120 or price<=0 or volume<=0:continue
                        except (KeyError,ValueError,TypeError):continue
                        quoted+=1
                        turnover=price*volume
                        if not math.isfinite(turnover):continue
                        if price<20 or volume<100000 or turnover<10000000:continue
                        row=dict(item,liquidity_turnover=turnover,liquidity_volume=volume,liquidity_change=change)
                        ranked.append(row)
            if all_items and not quoted:raise ValueError('No valid broad liquidity quotes; previous same-day shortlist retained')
            ranked.sort(key=lambda x:(-x['liquidity_turnover'],-x['liquidity_volume'],key(x)))
            cash=ranked[:self.limit];fo=[x for x in ranked if key(x) in contracts][:self.limit]
            self.state.update(lists={'intraday':cash,'fo-stocks':fo,'swing-trades':cash},updated_at=now.isoformat(),
                status='READY' if quoted==len(all_items) else 'PARTIAL QUOTE COVERAGE',universe=len(all_items),quoted=quoted,
                missing=len(all_items)-quoted,selected_counts={'intraday':len(cash),'fo-stocks':len(fo),'swing-trades':len(cash)})
        except Exception as exc:self.state.update(status='REFRESH FAILED — PREVIOUS SAME-DAY LIST ONLY',error=str(exc)[:200])
        self.save();return self.metadata(now)
