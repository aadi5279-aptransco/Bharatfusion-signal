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
 const repairSnapshot=async id=>{
  if(busy)return;setBusy(true);setMessage('Comparing fresh 5-minute and 1-minute history. This may take several minutes; do not submit again.');
  try{
   const r=await fetch('/api/v1/market-insights/research/repair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:id})});
   const d=await r.json();if(!r.ok)throw Error(d.error||'Repair request failed');
   if(!live.current)return;
   if(!d.dataset_id){setMessage(d.message||d.status);return;}
   setDatasets(old=>[d,...old.filter(x=>x.dataset_id!==d.dataset_id)].slice(0,30));
   setMessage('Repair comparison saved: '+d.repair.added_rows+' rows recovered; '+d.repair.remaining_regular_grid_gaps+' regular-grid gaps remain; '+d.repair.conflicts+' conflicts. Original snapshot retained. Training remains blocked.');
  }catch(ex){if(live.current)setMessage(ex.message);}finally{if(live.current)setBusy(false);}
 };
 return e('section',{className:'panel',style:{padding:24}},
  e('h2',null,'Phase 3D · Model Health'),
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
  e('h3',null,'Snapshot readiness — review before training'),
  datasets.map(d=>e('details',{key:d.dataset_id,style:{marginBottom:12}},
   e('summary',null,(d.instrument?.symbol||'Snapshot')+' · '+(d.readiness?.status||'Audit available on next refresh')),
   d.readiness?e('div',null,
    e('p',null,d.readiness.scope),
    e('button',{type:'button',disabled:busy||d.instrument?.segment!=='NSE_EQ',onClick:()=>repairSnapshot(d.dataset_id)},'Verify and repair from Dhan'),
    e('p',null,'Checks up to five affected sessions per request; saves a new version. No invented candles or automatic training.'),
    d.repair?e('div',null,
     e('p',null,'Repair result: ',d.repair.outcome,' · Recovered: ',d.repair.added_rows,' · Remaining gaps: ',d.repair.remaining_regular_grid_gaps,' · Conflicts: ',d.repair.conflicts,' · Deferred sessions: ',d.repair.sessions_deferred),
     e('p',{className:'small'},'Parent snapshot: ',d.repair.parent_dataset_id),
     e('ul',null,d.repair.sessions.map(s=>e('li',{key:s.date},s.date+' · added '+s.added+' · conflicts '+s.conflicts+' · '+s.requests.map(r=>r.interval+'m: '+r.status+(r.usable_rows!=null?' ('+r.usable_rows+' usable)':'')).join('; '))))):null,
    e('p',null,'Missing bars in observed sessions: ',d.readiness.missing_in_observed_sessions,' · Training approved: No'),
    e('ul',null,d.readiness.reasons.map((x,i)=>e('li',{key:i},x))),
    e('div',{style:{overflowX:'auto'}},e('table',null,
     e('thead',null,e('tr',null,...['Session','Expected regular bars','Present','Missing','Classification'].map(x=>e('th',{key:x},x)))),
     e('tbody',null,d.readiness.sessions.map(s=>e('tr',{key:s.date},
      e('td',null,s.date),e('td',null,s.expected_regular_bars),e('td',null,s.present),
      e('td',null,s.missing_regular_bars),e('td',null,s.classification))))))):null)),
  ['implemented','blocked_by','pending'].map(key=>e('div',{key},
   e('h3',null,{implemented:'Research foundation',blocked_by:'Data acceptance required',pending:'Remaining development'}[key]),
   e('ul',null,(data[key]||[]).map(x=>e('li',{key:x},x))))),
  e('p',null,data.fallback||'Deterministic strategies remain unchanged.'));
}
