import React,{useEffect,useState,useRef} from 'react';
const e=React.createElement;
export default function ModelHealth({data={}}){
 const [symbol,setSymbol]=useState('RELIANCE'),[days,setDays]=useState(7),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[datasets,setDatasets]=useState([]);
 const live=useRef(true);
 useEffect(()=>{live.current=true;return()=>{live.current=false;};},[]);
 useEffect(()=>{setDatasets(data.datasets||[]);},[data]);
 const capture=async event=>{
  event.preventDefault();if(busy)return;setBusy(true);setMessage('Downloading and validating completed 5-minute candles…');
  try{
   const r=await fetch('/api/v1/market-insights/research/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:symbol.trim(),days:Number(days)})});
   const d=await r.json();if(!r.ok)throw Error(d.error||'Snapshot request failed');
   if(!live.current)return;
   if(d.status==='BUSY'){setMessage(d.message);return;}
   setMessage(`Saved ${d.valid_rows} accepted candles; ${d.quarantined_rows} quarantined. Research only — training blocked.`);
   setDatasets(old=>[d,...old.filter(x=>x.dataset_id!==d.dataset_id)].slice(0,30));
  }catch(ex){if(live.current)setMessage(ex.message);}finally{if(live.current)setBusy(false);}
 };
 return e('section',{className:'panel',style:{padding:24}},
  e('h2',null,'Phase 3B · Model Health'),
  e('p',null,data.status||'Waiting for model health status…'),
  e('p',null,'No approved AI probabilities or performance statistics are available. Existing strategy signals are not AI-validated.'),
  e('p',null,'Champion: ',data.champion||'None',' · Automatic training: ',data.automatic_training?'Enabled':'Disabled'),
  e('h3',null,'Save research history'),
  e('p',null,'Select one mapped stock. Saves up to 30 calendar days of completed 5-minute candles. This can run after market close; no training or orders are started.'),
  e('form',{onSubmit:capture},
   e('label',null,'Symbol ',e('input',{value:symbol,onChange:ev=>setSymbol(ev.target.value),maxLength:64,required:true,disabled:busy})),
   e('label',null,' Calendar days ',e('input',{type:'number',min:1,max:30,value:days,onChange:ev=>setDays(ev.target.value),required:true,disabled:busy})),
   e('button',{type:'submit',disabled:busy},busy?'Saving…':'Save Dhan snapshot')),
  e('p',{role:'status'},message),
  e('h3',null,'Saved snapshots'),
  datasets.length?e('div',{style:{overflowX:'auto'}},e('table',null,
   e('thead',null,e('tr',null,...['Symbol','Accepted','Quarantined','Last candle (IST)','Status'].map(x=>e('th',{key:x},x)))),
   e('tbody',null,datasets.map(d=>e('tr',{key:d.dataset_id,title:d.dataset_id},
    e('td',null,d.instrument?.symbol),e('td',null,d.valid_rows),e('td',null,d.quarantined_rows),
    e('td',null,d.last?new Date(d.last).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'—'),e('td',null,d.status)))))):
    e('p',null,'No saved snapshots yet. A snapshot is created only when you request one.'),
  ['implemented','blocked_by','pending'].map(key=>e('div',{key},
   e('h3',null,{implemented:'Research foundation',blocked_by:'Data acceptance required',pending:'Remaining development'}[key]),
   e('ul',null,(data[key]||[]).map(x=>e('li',{key:x},x))))),
  e('p',null,data.fallback||'Deterministic strategies remain unchanged.'));
}
