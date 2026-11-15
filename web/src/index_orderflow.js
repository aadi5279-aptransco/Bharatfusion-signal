import React,{useEffect,useState} from 'react';
const e=React.createElement;
const num=v=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
const stamp=v=>v?new Date(v*1000).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour12:false}):'—';
export default function IndexOrderFlowPanel(){
 const [data,setData]=useState({instruments:[]});const [error,setError]=useState('');
 useEffect(()=>{let alive=true;const get=async()=>{try{const r=await fetch('/api/v1/market-insights/index-orderflow',{cache:'no-store'});if(!r.ok)throw Error('Feed status unavailable');const d=await r.json();if(alive){setData(d);setError('')}}catch(ex){if(alive)setError(ex.message)}};get();const id=setInterval(get,2000);return()=>{alive=false;clearInterval(id)}},[]);
 return e('section',{className:'panel positional-panel',style:{padding:20}},
  e('h2',null,'Index order flow · live test'),
  e('p',null,e('strong',null,data.status||'Waiting'),' · Recorded packets: ',num(data.recorded_packets)),
  e('p',{className:'notice warning'},'Paper-test only. Inferred delta from sampled index FUTURES trades; not exchange-labelled aggressor data. Levels below are futures prices, never CE/PE premiums. Existing option strategies remain separate.'),
  error||data.error?e('p',{role:'alert'},error||data.error):null,
  data.recording_error?e('p',{role:'alert'},'Recording stopped or failed: check disk space and the daily 250 MB cap.'):null,
  e('p',{className:'small muted'},'Start the backend before the session. Requires 20 complete one-minute warm-up bars, ≥80% classified volume, then a confirming next bar. Feed gaps reset the warm-up. No orders are placed.'),
  ...data.instruments.map(x=>{const b=x.latest||{},s=x.signal;return e('div',{key:x.contract.segment+':'+x.contract.id,className:'panel',style:{padding:16}},
   e('h3',null,x.contract.underlying,' · ',x.contract.symbol),
   e('p',null,x.status,' · Last trade ',stamp(x.last_trade_at),' IST · Warm-up ',x.warmup_bars,' / ',x.required_warmup,' · Tick ₹',num(x.tick_size)),
   e('div',{className:'tile-grid'},...[
    ['Last closed minute',stamp(b.start)],['Inferred delta',num(b.delta)],['Observed CVD',num(x.cvd)],['Classified volume',num(b.classification_pct)+'%'],['Unknown volume',num(b.unknown)]
   ].map(([label,value])=>e('div',{className:'tile',key:label},e('small',null,label),e('p',null,value)))),
   e('p',null,'Buy imbalance levels: ',(b.buy_imbalances||[]).join(', ')||'None',' · Sell: ',(b.sell_imbalances||[]).join(', ')||'None'),
   e('p',null,b.absorption||'No absorption pattern', ' · ',b.divergence||'No price/CVD divergence'),
   s?e('div',{className:'notice'},e('strong',null,s.option_bias,' — direction research only'),e('p',null,s.reason),
      e('p',null,'Futures reference ₹',num(s.entry),' · SL ₹',num(s.sl),' · T1 ₹',num(s.t1),' · T2 ₹',num(s.t2)),e('small',null,s.level_basis)):
      e('p',{className:'muted'},'No current confirmed order-flow research signal.'),
   e('details',null,e('summary',null,'Last closed bar footprint (up to 150 levels)'),e('div',{className:'tablewrap'},e('table',{className:'research-table'},
     e('thead',null,e('tr',null,...['Futures price','Inferred sell','Inferred buy'].map(h=>e('th',{key:h},h)))),
     e('tbody',null,...(b.footprint||[]).map(r=>e('tr',{key:r.price},e('td',null,num(r.price)),e('td',null,num(r.sell)),e('td',null,num(r.buy)))))))),
   e('p',{className:'small muted'},x.cvd_scope));}),
  ...(data.mapping_issues||[]).map((message,i)=>e('p',{key:'mapping-'+i,className:'notice warning'},message)),
  !data.instruments.length?e('p',null,'No live contracts yet. Mapping and connection start during a verified market session.'):null,
  e('p',{className:'small muted'},data.scope),e('p',{className:'small muted'},data.limitations));
}
