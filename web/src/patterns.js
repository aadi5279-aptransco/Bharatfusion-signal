import React,{useEffect,useRef,useState} from 'react';
const e=React.createElement;
const money=n=>typeof n==='number'&&Number.isFinite(n)?'₹'+n.toLocaleString('en-IN',{maximumFractionDigits:2}):'—';
const date=s=>s?new Date(s).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST':'—';
export default function PatternInspector({tab}){
 const [symbol,setSymbol]=useState('NIFTY'),[tf,setTf]=useState('5m'),[data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const controller=useRef(null);
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{controller.current?.abort();setData(null);setBusy(false);setError('');},[tab]);
 const run=async ev=>{
  ev.preventDefault();controller.current?.abort();const c=new AbortController();controller.current=c;
  setBusy(true);setError('');setData(null);
  try{const r=await fetch('/api/v1/market-insights/patterns/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,timeframe:tf}),signal:c.signal});const d=await r.json();if(!r.ok)throw Error(d.error||'Pattern source unavailable');if(!c.signal.aborted)setData(d);}
  catch(ex){if(ex.name!=='AbortError')setError(ex.message);}
  finally{if(!c.signal.aborted)setBusy(false);}
 };
 return e('details',{className:'section pattern-inspector'},e('summary',null,'Shared pattern engine · inspect a stock or index'),
  e('p',{className:'small muted'},'Same deterministic definitions in every tab. Confirmed geometry is not a trade fill; entry levels require verified instrument eligibility.'),
  e('form',{onSubmit:run,className:'pattern-controls'},e('label',null,'Symbol ',e('input',{value:symbol,maxLength:64,onChange:ev=>setSymbol(ev.target.value),required:true})),
   e('label',null,'Timeframe ',e('select',{value:tf,onChange:ev=>setTf(ev.target.value)},['5m','15m','1h','daily','weekly','monthly'].map(x=>e('option',{key:x,value:x},x)))),
   e('button',{type:'submit',disabled:busy},busy?'Checking closed candles…':'Check patterns')),
  error?e('p',{role:'alert',className:'notice warning'},error):null,
  data?e('div',{'aria-live':'polite'},e('p',null,data.symbol||symbol,' · ',data.status,' · ',date(data.asof)),
   data.reason?e('p',{className:'notice warning'},data.reason):null,
   !(data.patterns||[]).length?e('p',{className:'empty'},'No qualifying pattern evidence in the available completed bars.'):null,
   e('div',{className:'signal-grid'},(data.patterns||[]).map((p,i)=>e('article',{className:'signal',key:p.pattern+p.direction+i},
    e('h3',null,p.pattern,' · ',p.direction),e('p',null,p.entry_ready?'Confirmed · entry research':p.geometry_confirmed?'Geometry confirmed · eligibility pending':'Forming / confirmation pending'),
    e('p',{className:'small muted'},'Rule score ',p.score,'/100 · ',p.timeframe,' · Known at ',date(p.available_at)),
    e('p',null,'Entry ',money(p.entry),' · Stop ',money(p.stop),' · Measured target ',money(p.target)),
    e('ul',null,p.context.map((x,j)=>e('li',{key:j},x))),
    e('p',{className:'small muted'},p.invalidation),
    e('details',null,e('summary',null,'Geometry levels'),e('pre',null,JSON.stringify({levels:p.levels,trendlines:p.trendlines},null,2)))
   )))) :null);
}
