import React,{useEffect,useState} from 'react';
const e=React.createElement,num=v=>v==null?'—':'₹'+Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
const stamp=v=>v?new Date(v).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'—';
export default function PremarketFollowthrough(){
 const [data,setData]=useState({passes:{}}),[error,setError]=useState('');
 useEffect(()=>{let alive=true,timer;const c=new AbortController();const poll=async()=>{try{const r=await fetch('/api/v1/market-insights/premarket-followthrough',{signal:c.signal,cache:'no-store'});if(!r.ok)throw Error('Live watchlist analysis unavailable');const d=await r.json();if(alive){setData(d);setError('')}}catch(ex){if(alive&&ex.name!=='AbortError')setError(ex.message)}finally{if(alive)timer=setTimeout(poll,15000)}};poll();return()=>{alive=false;c.abort();clearTimeout(timer)}},[]);
 const latest=data.latest||{},signals=!error&&!data.stale?(data.signals||[]):[];
 return e('section',{className:'panel',style:{padding:20}},e('h2',null,'Live watchlist analysis · every 5 minutes from 09:30 IST'),
 e('p',null,'Saved watchlist stocks: ',(data.symbols||[]).join(', ')||'Waiting for a verified completed-session watchlist',' · Trading session: ',data.session||'—'),
 e('p',{className:'small muted'},'First assessment uses candles completed by 09:30 (the 09:15–09:30 opening period), then 09:35, 09:40 and every five minutes through 15:25. The candle starting at 09:30 is first used at 09:35. Late startup checks the latest completed period without replaying missed scans.'),
 error||data.error?e('p',{role:'alert'},error||data.error):null,
 e('p',null,latest.status||'Waiting for 09:30',' · Candle cutoff: ',stamp(latest.cutoff),' · Last assessment: ',stamp(latest.updated_at),' IST'),
 data.stale?e('p',{className:'notice warning'},'No fresh completed assessment. Saved historical levels are not current entry signals.'):null,
 ...['BUY','SELL'].map(side=>e('section',{key:side},e('h3',null,side==='BUY'?'BUY · confirmed breakout setups':'SELL · confirmed breakdown setups'),
 ...signals.filter(s=>s.direction===side).map((s,i)=>e('article',{className:'tile',key:s.symbol+s.strategy+i},e('h3',null,s.symbol,' · ',s.strategy),e('p',null,'Entry ',num(s.entry),' · Target 1 ',num(s.t1),' · Target 2 ',num(s.t2),' · SL ',num(s.sl)),e('p',null,(s.reasons||[]).join('; ')))),
 !signals.some(s=>s.direction===side)?e('p',null,'No confirmed ',side,' entry in the latest assessment.'):null)),
 e('details',null,e('summary',null,'Latest stock checks and source gaps'),...(latest.rows||[]).map(r=>e('article',{key:r.symbol},e('h4',null,r.symbol,' · ',r.status),r.reason?e('p',null,r.reason):null,
 r.metrics?e('p',null,'Close ',num(r.metrics.close),' · VWAP ',num(r.metrics.vwap),' · RSI ',r.metrics.rsi??'—',' · ADX ',r.metrics.adx??'—',' · RVOL ',r.metrics.rvol??'—'):null,
 ...(r.checks||[]).map((c,i)=>e('p',{key:i},c.strategy,' — ',c.status,': ',c.reason)),
 ...(r.context||[]).map((c,i)=>e('p',{key:'c'+i},c.strategy,' — ',c.status,': ',c.reason))))),
 e('details',null,e('summary',null,'Saved assessments for this session'),...Object.entries(data.passes||{}).sort(([a],[b])=>b.localeCompare(a)).map(([slot,p])=>e('p',{key:slot},slot,' · ',p.status,' · ',(p.signals||[]).length,' setups · ',p.historical?'Historical':'Recent'))),
 e('p',{className:'small muted'},'Cash-stock levels only. Liquidity, trend, momentum and completed-candle confirmation filters apply. Longer-term strategies retain their own horizons; unavailable evidence is not invented. Backend must remain open.'));
}
