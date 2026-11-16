import React,{useEffect,useState} from 'react';
const e=React.createElement,num=v=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
const stamp=v=>v?new Date(v).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'—';
export default function PremarketFollowthrough(){
 const [data,setData]=useState({passes:{}}),[error,setError]=useState('');
 useEffect(()=>{let alive=true,timer;const c=new AbortController();const poll=async()=>{try{const r=await fetch('/api/v1/market-insights/premarket-followthrough',{signal:c.signal,cache:'no-store'});if(!r.ok)throw Error('Morning monitor unavailable');const d=await r.json();if(alive){setData(d);setError('')}}catch(ex){if(alive&&ex.name!=='AbortError')setError(ex.message)}finally{if(alive)timer=setTimeout(poll,15000)}};poll();return()=>{alive=false;c.abort();clearTimeout(timer)}},[]);
 return e('section',{className:'panel',style:{padding:20}},e('h2',null,'Opening follow-through · 09:45 & 10:00 IST'),
 e('p',null,'Frozen pre-market stocks: ',(data.symbols||[]).join(', ')||'Waiting for a verified watchlist',' · Session: ',data.session||'—'),
 e('p',{className:'notice warning'},'Cash-stock breakout/breakdown research, not option premiums or executed trades. Scans begin after the 09:45 and 10:00 candles are complete; completion depends on broker response and scan availability. No forced signal when confirmations are missing.'),
 error||data.error?e('p',{role:'alert'},error||data.error):null,
 ...['09:45','10:00'].map(slot=>{const p=data.passes?.[slot];return e('section',{key:slot,style:{marginTop:24}},e('h3',null,slot,' assessment'),!p?e('p',null,'Not run. A late start after 10:00 does not replay the 09:45 pass; after 10:15 neither pass is backfilled.'):e(React.Fragment,null,
 e('p',null,p.status,' · Data cutoff: ',stamp(p.cutoff),' IST · Completed: ',stamp(p.updated_at),' IST'),
 p.historical||error?e('p',{className:'notice warning'},'HISTORICAL / CONNECTION UNVERIFIED — saved levels are not a current entry instruction.'):null,
 ...(p.rows||[]).map(r=>e('article',{className:'tile',key:r.symbol,style:{marginBottom:12}},e('h3',null,r.symbol,' · ',r.status),
 r.reason?e('p',null,r.reason):null,
 r.metrics?e('p',{className:'small'},'Close ',num(r.metrics.close),' · VWAP ',num(r.metrics.vwap),' · EMA20/50 ',num(r.metrics.ema20),' / ',num(r.metrics.ema50),' · RSI ',num(r.metrics.rsi),' · ATR ',num(r.metrics.atr),' · Gap ',num(r.metrics.gap_pct),'% · ADX ',num(r.metrics.adx),' · RVOL ',num(r.metrics.rvol),'× · Volume ',num(r.metrics.session_volume),' · Turnover proxy ₹',num(r.metrics.turnover_cr),' crore'):null,
 ...(r.signals||[]).map((s,i)=>e('div',{key:i,className:'notice'},e('strong',null,s.direction==='BUY'?'BREAKOUT':'BREAKDOWN',' · ',s.strategy),e('p',null,'Entry ₹',num(s.entry),' · T1 ₹',num(s.t1),' · T2 ₹',num(s.t2),' · SL ₹',num(s.sl)),e('p',null,(s.reasons||[]).join('; ')))),
 e('details',null,e('summary',null,'Strategy checks and unavailable confirmations'),...(r.checks||[]).map((c,i)=>e('p',{key:i},c.strategy,' — ',c.status,': ',c.reason)),...(r.context||[]).map((c,i)=>e('p',{key:'c'+i},c.strategy,' — ',c.status,': ',c.reason)))))))}),
 e('p',{className:'small muted'},'Only the displayed pre-market gainers/losers are assessed. Liquidity, RVOL, ADX, VWAP and EMA checks filter morning entries. Longer-term strategies retain their original timeframe; missing OI, fundamentals or benchmark data are not inferred. No continuous refresh after the 10:00 assessment.'));
}
