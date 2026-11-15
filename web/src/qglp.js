import React,{useEffect,useState} from 'react';
const e=React.createElement,fmt=v=>v==null?'—':Number(v).toLocaleString('en-IN',{maximumFractionDigits:2});
export default function QGLPPanel(){
 const [data,setData]=useState({rows:[]}),[error,setError]=useState(''),[busy,setBusy]=useState(false),[filter,setFilter]=useState('ALL'),[page,setPage]=useState(0);
 useEffect(()=>{let live=true;fetch('/api/v1/market-insights/qglp').then(r=>{if(!r.ok)throw Error('QGLP data unavailable');return r.json()}).then(d=>{if(live)setData(d)}).catch(ex=>{if(live)setError(ex.message)});return()=>{live=false}},[]);
 const upload=async ev=>{ev.preventDefault();const body=new FormData(ev.currentTarget);setBusy(true);setError('');try{const r=await fetch('/api/v1/market-insights/qglp/import',{method:'POST',body});const d=await r.json();if(!r.ok)throw Error(d.error||'Import failed');setData(d);setPage(0)}catch(ex){setError(ex.message)}finally{setBusy(false)}};
 const rows=(data.rows||[]).filter(x=>filter==='ALL'||x.status===filter),shown=rows.slice(page*25,page*25+25);
 return e('section',{className:'panel',style:{padding:20}},e('h2',null,'QGLP fundamental shortlist · additional research'),
 e('p',null,'Quality, growth, longevity review and price. Import dated fundamentals to apply your uploaded strategy; existing technical research remains below.'),
 e('p',{className:'notice warning'},'This is a relative fundamental screen, not a guaranteed multibagger, entry signal or return probability. Longevity, sector suitability and accounting quality require manual review. No entry/target/SL is inferred from financial ratios.'),
 e('a',{href:'/api/v1/market-insights/qglp/template',download:true},'Download CSV column template'),
 e('form',{onSubmit:upload,style:{display:'flex',gap:12,flexWrap:'wrap',margin:'16px 0'}},
 e('label',null,'CSV export ',e('input',{type:'file',name:'file',accept:'.csv',required:true})),
 e('label',null,'Export date ',e('input',{type:'date',name:'asof',required:true})),
 e('label',null,'Financial period end ',e('input',{type:'date',name:'period_end',required:true})),
 e('label',null,'Source ',e('input',{name:'source',placeholder:'Screener.in export / annual reports',required:true,minLength:3,maxLength:200})),
 e('button',{disabled:busy,type:'submit'},busy?'Validating…':'Import and rank')),
 e('p',{className:'small muted'},'Use percentages as 15 (not 0.15), market cap and cumulative three-year cash flow/profit in ₹ crore. CFO and profit must cover the same three financial years. Save Excel as CSV UTF-8. Import only rows with the financial period entered above; blanks remain unverified.'),
 error||data.error?e('p',{role:'alert'},error||data.error):null,
 e('p',null,data.status||'Loading…',' · Qualified ',data.qualified??0,' / ',data.count??0),
 data.source?e('p',null,'Source: ',data.source,' · Export: ',data.asof,' · Period end: ',data.period_end):null,
 e('p',{className:'small muted'},'Filters: cap ₹500–15,000 crore; ROCE ≥15%; sales/profit growth ≥15%; debt/equity ≤0.7; promoter ≥40%; pledge ≤10%; positive P/E and 3-year profit; cash conversion ≥0.7. All scoring inputs required.'),
 e('label',null,'Show ',e('select',{value:filter,onChange:ev=>{setFilter(ev.target.value);setPage(0)}},...['ALL','QUALIFIED','REJECTED','UNVERIFIED','UNSUPPORTED SECTOR','STALE'].map(x=>e('option',{key:x,value:x},x)))),
 e('div',{className:'tablewrap'},e('table',{className:'research-table'},
 e('thead',null,e('tr',null,...['Company','Status / rank','Score /100','ROCE %','Sales / profit growth %','Debt/equity','PEG','Cash conversion','Reasons'].map(h=>e('th',{key:h},h)))),
 e('tbody',null,...shown.map((r,i)=>e('tr',{key:r.symbol||r.name},e('td',null,r.name,r.symbol?' ('+r.symbol+')':''),e('td',null,r.status,r.rank?' #'+r.rank:''),e('td',null,fmt(r.score)),e('td',null,fmt(r.roce)),e('td',null,fmt(r.sales_g3),' / ',fmt(r.profit_g3)),e('td',null,fmt(r.de)),e('td',null,fmt(r.peg)),e('td',null,fmt(r.cash_conv)),
 e('td',null,e('details',null,e('summary',null,'View checks and score'),
 r.missing?.length?e('p',null,'Missing/invalid: ',r.missing.join(', ')):null,
 ...(r.checks||[]).map((c,j)=>e('p',{key:j},c.status,' · ',c.label,' · ',fmt(c.value))),
 ...(r.score_parts||[]).map(c=>e('p',{key:c.metric},c.metric,': ',fmt(c.points),' / ',c.weight*100,' points')),
 ...(r.warnings||[]).map((w,j)=>e('p',{key:'w'+j},w))))))))),
 e('p',null,rows.length,' matching rows · Page ',page+1),e('button',{disabled:page===0,onClick:()=>setPage(page-1)},'Previous'),e('button',{disabled:(page+1)*25>=rows.length,onClick:()=>setPage(page+1)},'Next'),
 e('p',{className:'small muted'},data.note,' Scores compare only qualified companies in this import; ties share ranks and a single survivor scores 50. No automatic fundamental data is fabricated.'));
}
