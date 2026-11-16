import React,{useState} from 'react';
const e=React.createElement,n=v=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
export default function IndexScanStatus({data={}}){
 const [message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const age=data.updated_at?(Date.now()-Date.parse(data.updated_at))/1000:null;
 const stale=age==null||!Number.isFinite(age)||age>600||age<0;
 const ready=(data.opening_setups||[]).filter(x=>x.state==='DIRECTION_READY');
 const refresh=async()=>{setBusy(true);try{const r=await fetch('/api/v1/market-insights/index-options/refresh',{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.error||d.status);setMessage('Refresh started. This tab loads results every 20 seconds.')}catch(ex){setMessage(ex.message)}finally{setBusy(false)}};
 return e('section',{className:'panel',style:{padding:20}},e('h2',null,'Index strategy readiness'),
 e('button',{onClick:refresh,disabled:busy},busy?'Requesting…':'Refresh index strategies'),message?e('p',{role:'status'},message):null,
 e('p',null,'Mapped indices scanned: ',data.scanned??0,' · Confirmed underlying directions: ',ready.length,' · Last scan: ',data.updated_at?new Date(data.updated_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST':'Not yet run'),
 e('p',{className:'small muted'},'Checks start at 09:20 IST and catch up once per five-minute interval. First-5m confirmation is possible from 09:30; first-red-bar confirmation is possible from 09:35 or later. Two subsequent completed closes are required. A red bar may not yet exist.'),
 stale?e('p',{className:'notice warning'},'No recent completed scan. Saved setups below are historical; refresh during a verified market session.'):null,
 ...(data.scan_issues||[]).map((x,i)=>e('p',{key:i,role:'alert'},x)),
 ...ready.map((x,i)=>e('div',{className:'notice',key:i},e('strong',null,x.underlying,' · ',x.side,' DIRECTION · ',x.strategy),e('p',null,'Underlying entry ',n(x.spot_entry),' · T1 ',n(x.spot_t1),' · T2 ',n(x.spot_t2),' · SL ',n(x.spot_sl)),e('p',null,x.reason),e('small',null,'CASH INDEX LEVELS, NOT OPTION PREMIUMS. ',x.trade_status))),
 !ready.length?e('p',null,'No confirmed opening setup yet. The strategy table below shows trigger levels and the exact waiting/rejection reason for each index.'):null,
 e('p',{className:'small muted'},'Legacy premium scenarios also require a fresh directional Dashboard, SMC/MTF alignment and option-chain checks. Missing those inputs can block a premium scenario without blocking an independent red-bar direction watch.'));
}
