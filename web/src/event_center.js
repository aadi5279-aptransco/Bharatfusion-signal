import React,{useState,useEffect} from 'react';
const e=React.createElement,stamp=v=>v?new Date(v*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'Time unavailable';
const read=(k,f)=>{try{return localStorage.getItem(k)||f}catch{return f}},write=(k,v)=>{try{localStorage.setItem(k,String(v))}catch{}};
async function post(path,body){const r=await fetch('/api/v1/market-insights/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
export function NotificationCenter({onOpen}){
 const [data,setData]=useState({alerts:[],unread:0}),[error,setError]=useState(''),[open,setOpen]=useState(false),[toasts,setToasts]=useState([]),[desktop,setDesktop]=useState(read('bharat-desktop-alerts','off')==='on');
 useEffect(()=>{let alive=true,timer;let cursor=Number(read('bharat-alert-cursor','0'));const controller=new AbortController();
 const poll=async()=>{try{const r=await fetch('/api/v1/market-insights/notifications',{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('Alerts unavailable');const d=await r.json();if(!alive)return;setData(d);setError(d.error||'');
 const fresh=d.alerts.filter(a=>a.id>cursor&&!a.seen&&Date.now()/1000-a.created<120);const newest=d.alerts[0]?.id||0;
 if(cursor&&fresh.length){setToasts(fresh.slice(0,3));if(desktop&&'Notification' in window&&Notification.permission==='granted'){
  try{const list=fresh.length>3?[{title:`${fresh.length} new BharatSignal alerts`,body:'Open the notification inbox for every alert.',id:newest,tab:'Event Calendar'}]:fresh;
  list.forEach(a=>{const n=new Notification(a.title,{body:a.body,tag:'bharat-'+a.id});n.onclick=()=>{window.focus();onOpen(a.tab);n.close()}})}catch{setError('Desktop notifications unavailable; in-app alerts remain active')}}}
 cursor=Math.max(cursor,newest);if(cursor)write('bharat-alert-cursor',cursor);
 // A first empty inbox still establishes a baseline for the next poll.
 if(!cursor)cursor=-1;
 }catch(ex){if(alive&&ex.name!=='AbortError')setError('Notification connection unavailable')}finally{if(alive)timer=setTimeout(poll,5000)}};poll();return()=>{alive=false;clearTimeout(timer);controller.abort()}},[desktop]);
 const enable=async()=>{if(desktop){setDesktop(false);write('bharat-desktop-alerts','off');return}if(!('Notification' in window)){setError('Browser does not support desktop notifications');return}try{const p=await Notification.requestPermission();setDesktop(p==='granted');write('bharat-desktop-alerts',p==='granted'?'on':'off');if(p!=='granted')setError('Desktop permission not granted; in-app notifications still work')}catch{setError('Could not enable desktop notifications')}};
 return e('section',{className:'panel',style:{padding:12,marginBottom:14}},e('button',{onClick:()=>setOpen(!open)},'🔔 Notifications · ',data.unread,' unread'),e('button',{onClick:enable},desktop?'Disable desktop alerts':'Enable desktop alerts'),
 error?e('p',{role:'alert'},error):null,
 toasts.length?e('div',{'aria-live':'polite'},...toasts.map(a=>e('div',{key:a.id,className:'notice'},e('strong',null,a.title),e('p',null,a.body),e('button',{onClick:()=>{onOpen(a.tab);setToasts(v=>v.filter(x=>x.id!==a.id))}},'Open ',a.tab),e('button',{onClick:()=>setToasts(v=>v.filter(x=>x.id!==a.id))},'Dismiss')))):null,
 open?e('div',null,e('p',{className:'small muted'},'Research alerts, not executed trades. Historical alerts may no longer be valid; check the originating tab. Backend and browser must remain open for desktop pop-ups.'),
 e('button',{onClick:async()=>{try{await post('notifications/read',{through:data.alerts[0]?.id||0});setData({...data,unread:0,alerts:data.alerts.map(a=>({...a,seen:true}))});setToasts([])}catch(ex){setError(ex.message)}}},'Mark all read'),
 ...data.alerts.map(a=>e('details',{key:a.id},e('summary',null,a.seen?'':'● ',a.title,' · ',stamp(a.created),' IST'),e('p',null,a.body),a.url?e('a',{href:a.url,target:'_blank',rel:'noopener noreferrer'},'Original source'):null,e('button',{onClick:()=>onOpen(a.tab)},'Open ',a.tab)))):null);
}
export function EventCalendar({data,onRefresh}){
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[filter,setFilter]=useState(''),[date,setDate]=useState('');
 const match=x=>(!filter||(x.title+' '+x.tag+' '+x.source).toLowerCase().includes(filter.toLowerCase()))&&(!date||x.at&&new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(x.at*1000))===date);
 const add=async ev=>{ev.preventDefault();const form=ev.currentTarget;const body=Object.fromEntries(new FormData(form));setBusy(true);try{await post('events/add',body);form.reset();setError('');onRefresh()}catch(ex){setError(ex.message)}finally{setBusy(false)}};
 const card=x=>e('article',{className:'tile',key:x.id},e('h3',null,e('a',{href:x.url,target:'_blank',rel:'noopener noreferrer'},x.title)),e('p',null,x.source,' · ',stamp(x.at),' IST'),e('p',null,x.tag,' · Possible exposure: ',x.sectors),
 x.source==='User schedule'?e('button',{onClick:async()=>{try{await post('events/remove',{id:x.id});onRefresh()}catch(ex){setError(ex.message)}}},'Remove my event'):null);
 return e('section',{className:'panel',style:{padding:20}},e('h2',null,'Market Event Calendar & News'),
 e('p',{className:'notice warning'},'Free public sources; refresh approximately every 5 minutes. Keyword-based relevance is not a prediction of direction or magnitude. News publication times are not scheduled event times. No trading strategy is changed.'),
 e('p',null,'Upcoming BLS economic releases are automatic. Add officially announced RBI MPC, Budget or company-result dates below; a complete Indian earnings calendar is not supplied.'),
 e('label',null,'Search ',e('input',{value:filter,onChange:ev=>setFilter(ev.target.value),placeholder:'Inflation, crude, RBI…'})),e('label',null,' IST date ',e('input',{type:'date',value:date,onChange:ev=>setDate(ev.target.value)})),
 error||data.error?e('p',{role:'alert'},error||data.error):null,
 e('details',null,e('summary',null,'Source health and last successful fetch'),...(data.sources||[]).map(s=>e('p',{key:s.name},s.name,' · ',stamp(s.updated_at),' IST · ',s.error||((Date.now()/1000-s.updated_at>900)?'STALE CACHE':'Fetch successful')))),
 e('h3',null,'Scheduled events · reminders within 15 minutes'),e('div',{className:'tile-grid'},...(data.events||[]).filter(match).map(card)),!(data.events||[]).filter(match).length?e('p',null,'No scheduled events available for this filter. Check source health; this does not mean there are no market events.'):null,
 e('details',null,e('summary',null,'Add an announced event with its source'),e('form',{onSubmit:add,style:{display:'flex',gap:10,flexWrap:'wrap'}},e('label',null,'Event ',e('input',{name:'title',required:true,maxLength:200})),e('label',null,'Date/time (IST) ',e('input',{name:'at',type:'datetime-local',required:true})),e('label',null,'Official source URL ',e('input',{name:'url',type:'url',required:true})),e('button',{disabled:busy},'Save event')),e('p',null,'User-entered dates are not independently verified. Remove and re-add if a schedule changes.')),
 e('h3',null,'Latest source headlines'),e('div',{className:'tile-grid'},...(data.news||[]).filter(match).map(card)),!(data.news||[]).filter(match).length?e('p',null,'No headlines available for this filter.'):null,
 e('p',{className:'small muted'},'Attribution: RBI, PIB, Federal Reserve, ECB, BLS and BBC News. Links open the original publisher. Initial feed history is loaded silently; only newly detected recent relevant headlines trigger alerts.'));
}
