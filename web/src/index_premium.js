import React from 'react';
const e=React.createElement,m=v=>v==null?'—':'₹'+Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
export default function IndexPremium({rows=[]}){
 return e('section',{className:'panel',style:{padding:20}},e('h2',null,'ATM option premium entries'),
 e('p',null,'ATM strike identifies the contract. Entry, SL and targets below are option premium prices. CE and PE are option-buying setups; a direction needs confirmation before levels appear.'),
 ...['CE','PE'].map(side=>e('section',{key:side},e('h3',null,side==='CE'?'CE · bullish index setups':'PE · bearish index setups'),
 ...rows.filter(r=>r.direction===side).map(r=>e('article',{key:r.underlying,className:'tile'},
 e('h3',null,r.underlying,' · ATM ',r.strike??'—',' ',side,' · ',r.expiry||'Expiry unavailable'),
 e('strong',null,r.status),e('p',null,'Premium entry ',m(r.entry),' · Target 1 ',m(r.t1),' · Target 2 ',m(r.t2),' · SL ',m(r.sl)),
 e('p',{className:'small muted'},'Last option trade: ',r.quote_asof||'Unverified',' · Spread: ',r.spread_pct??'—','%'),
 ...(r.blockers||[]).map((s,i)=>e('p',{key:'b'+i,className:'notice warning'},'WAIT: ',s)),
 ...(r.warnings||[]).map((s,i)=>e('p',{key:'w'+i,className:'small'},'Caution: ',s)),
 e('details',null,e('summary',null,'Strategy and pricing reasons'),...(r.reasons||[]).map((s,i)=>e('p',{key:i},s))))))),
 !rows.length?e('p',null,'Waiting for index/option data. Check source diagnostics below.'):null);
}
