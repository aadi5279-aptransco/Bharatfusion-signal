import React,{useState,useEffect,useRef} from 'react';
const e=React.createElement,stamp=v=>v?new Date(v*1000).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'Time unavailable';
const read=(k,f)=>{try{return localStorage.getItem(k)||f}catch{return f}},write=(k,v)=>{try{localStorage.setItem(k,String(v))}catch{}};
async function post(path,body){const r=await fetch('/api/v1/market-insights/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d}
export function NotificationCenter({onOpen}){
 const [data,setData]=useState({alerts:[],unread:0}),[error,setError]=useState(''),[open,setOpen]=useState(false),[toasts,setToasts]=useState([]),[desktop,setDesktop]=useState(read('bharat-desktop-alerts','off')==='on'),[marking,setMarking]=useState(false);
 const revision=useRef(0),pendingRead=useRef(false);
 const tab=a=>a.tab==='Event Calendar'?'Dashboard':a.tab;
 useEffect(()=>{let alive=true,timer;let cursor=Number(read('bharat-alert-cursor','0'));const controller=new AbortController();
 const poll=async()=>{const startedRevision=revision.current;try{
  const r=await fetch('/api/v1/market-insights/notifications',{signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('Alerts unavailable');const d=await r.json();
  // Ignore a response taken before/during a read mutation. It must not restore
  // a dismissed alert or fire a desktop popup from an older inbox snapshot.
  if(!alive||pendingRead.current||revision.current!==startedRevision)return;
  d.alerts=(d.alerts||[]).filter(a=>!a.seen);setData(d);setError(d.error||'');
  const visible=new Set(d.alerts.map(a=>a.id));setToasts(v=>v.filter(a=>visible.has(a.id)));
  const fresh=d.alerts.filter(a=>a.id>cursor&&Date.now()/1000-a.created>=0&&Date.now()/1000-a.created<120);const newest=d.latest_id??d.alerts[0]?.id??0;
  if(cursor&&fresh.length){setToasts(fresh.slice(0,3));if(desktop&&'Notification' in window&&Notification.permission==='granted'){
   try{const list=fresh.length>3?[{title:`${fresh.length} new BharatSignal alerts`,body:'Open the notification inbox for every alert.',id:newest,tab:'Dashboard'}]:fresh;
    list.forEach(a=>{const n=new Notification(a.title,{body:a.body,tag:'bharat-'+a.id});n.onclick=()=>{window.focus();onOpen(tab(a));n.close()}})}catch{setError('Desktop notifications unavailable; in-app alerts remain active')}}}
  cursor=Math.max(cursor,newest);if(cursor)write('bharat-alert-cursor',cursor);
  if(!cursor)cursor=-1;
 }catch(ex){if(alive&&ex.name!=='AbortError')setError('Notification connection unavailable')}finally{if(alive)timer=setTimeout(poll,5000)}};
 poll();return()=>{alive=false;clearTimeout(timer);controller.abort()}},[desktop]);
 const markRead=async body=>{
  if(pendingRead.current)return;
  pendingRead.current=true;revision.current++;setMarking(true);setError('');
  try{
   const d=await post('notifications/read',body);d.alerts=(d.alerts||[]).filter(a=>!a.seen);
   setData(d);const visible=new Set(d.alerts.map(a=>a.id));setToasts(v=>v.filter(a=>visible.has(a.id)));
   if(d.error)setError(d.error);
  }catch(ex){setError(ex.message)}finally{revision.current++;pendingRead.current=false;setMarking(false)}
 };
 const enable=async()=>{if(desktop){setDesktop(false);write('bharat-desktop-alerts','off');return}if(!('Notification' in window)){setError('Browser does not support desktop notifications');return}try{const p=await Notification.requestPermission();setDesktop(p==='granted');write('bharat-desktop-alerts',p==='granted'?'on':'off');if(p!=='granted')setError('Desktop permission not granted; in-app notifications still work')}catch{setError('Could not enable desktop notifications')}};
 return e('section',{className:'panel',style:{padding:12,marginBottom:14}},e('button',{onClick:()=>setOpen(!open)},'🔔 Notifications · ',data.unread,' unread'),e('button',{onClick:enable},desktop?'Disable desktop alerts':'Enable desktop alerts'),
 error?e('p',{role:'alert'},error):null,
 toasts.length?e('div',{'aria-live':'polite'},...toasts.map(a=>e('div',{key:a.id,className:'notice'},e('strong',null,a.title),e('p',null,a.body),e('button',{onClick:()=>onOpen(tab(a))},'Open ',tab(a)),e('button',{disabled:marking,onClick:()=>markRead({id:a.id})},'Mark as read')))):null,
 open?e('div',null,e('p',{className:'small muted'},'Unread research alerts only. Marked-read alerts stay hidden after refresh and restart. Check the originating tab before using historical levels.'),
 e('button',{disabled:marking||!data.unread,onClick:()=>markRead({through:data.latest_id??data.alerts[0]?.id??0})},marking?'Saving…':'Mark all read'),
 !data.alerts.length?e('p',{role:'status'},'No unread notifications.'):null,
 ...data.alerts.map(a=>e('details',{key:a.id},e('summary',null,'● ',a.title,' · ',stamp(a.created),' IST'),e('p',null,a.body),a.url?e('a',{href:a.url,target:'_blank',rel:'noopener noreferrer'},'Original source'):null,e('button',{onClick:()=>onOpen(tab(a))},'Open ',tab(a)),e('button',{disabled:marking,onClick:()=>markRead({id:a.id})},'Mark as read')))):null);
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
