import React,{useEffect,useState} from 'react';
const e=React.createElement;
const num=v=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
const stamp=v=>v?new Date(v*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'—';
export default function EuropeMarketsPanel(){
 const [data,setData]=useState({markets:[]}),[error,setError]=useState('');
 useEffect(()=>{let alive=true;const controller=new AbortController();let timer;
 const poll=async()=>{try{const r=await fetch('/api/v1/market-insights/europe-markets',{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('European market status unavailable');const d=await r.json();if(alive){setData(d);setError('')}}catch(ex){if(alive)setError('European market connection unavailable — displayed values may be stale')}finally{if(alive)timer=setTimeout(poll,15000)}};poll();return()=>{alive=false;controller.abort();clearTimeout(timer)}},[]);
 return e('section',{className:'panel',style:{padding:20}},e('h2',null,'Europe markets · delayed quotes'),
  e('p',{className:'small muted'},'Independent context feed • refresh approximately every minute • prices are index points'),
  error?e('p',{role:'alert'},error):null,
  e('div',{className:'tile-grid'},...data.markets.map(x=>e('div',{className:'tile',key:x.symbol},
   e('h3',null,x.name),e('small',null,x.region),e('h2',null,num(x.price)),
   e('strong',{style:{color:x.change_pct>0?'var(--green)':x.change_pct<0?'var(--red)':undefined}},x.change>0?'+':'',num(x.change),' (',x.change_pct>0?'+':'',num(x.change_pct),'%)'),
   e('p',null,error?'CONNECTION LOST — CHECK TIMESTAMP':x.quality),e('p',{className:'small'},'Quote: ',stamp(x.quote_at),' IST'),
   e('p',{className:'small'},'Fetched: ',stamp(x.fetched_at),' IST'),
   e('p',{className:'small'},x.scheduled_session),e('p',{className:'small'},'Normal session ',x.normal_open_ist,'–',x.normal_close_ist,' IST'),
   e('p',{className:'small muted'},x.provider_session),x.error?e('p',{role:'alert'},x.error):null))),
  !data.markets.length?e('p',null,'Waiting for European market feed…'):null,
  e('p',{className:'small muted'},data.note||'No changes to Indian-market signals or strategies.'),
  e('p',{className:'small muted'},'Source: Yahoo Finance. UK is included as European market context. Normal hours adjust for daylight saving; they do not certify that an exchange is open.'));
}
