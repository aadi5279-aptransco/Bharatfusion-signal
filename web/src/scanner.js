import React,{useEffect,useState} from 'react';
const e=React.createElement;
async function api(url,options={}){
 const r=await fetch(url,{...options,headers:{Accept:'application/json',...(options.headers||{})},cache:'no-store'});
 const b=await r.json();if(!r.ok)throw Error(b.error||b.status||`HTTP ${r.status}`);return b;
}
const BASE={universe:'fno',exchange:'NSE',limit:100,symbols:''};
const BUILTINS={
 'All loaded stocks':{},
 'Video: liquid uptrend':{fno:'yes',price_min:50,avg_volume_min:2000000,sma20:'above',sma50:'above',sma200:'above'},
 '20-day breakout + volume':{signal:'breakout20',rvol_min:2,price_min:50},
 'RSI oversold':{rsi_max:30},
 'Strong daily trend':{signal:'uptrend',rsi_min:50,rsi_max:70},
 'Downtrend':{signal:'downtrend'}
};
const LABELS={symbol:'Stock / symbol',company:'Company',exchange:'Exchange',sector:'Sector',industry:'Industry',fno:'F&O',
 price:'Close ₹',change_pct:'Day %',volume:'Volume',avg_volume:'Avg vol 20D',rvol:'Rel vol',rsi:'RSI 14',atr_pct:'ATR %',
 sma20:'SMA 20',sma50:'SMA 50',sma200:'SMA 200',perf_week:'1W %',perf_month:'1M %',perf_quarter:'3M %',high52:'52W high',low52:'52W low',
 market_cap_cr:'Mkt cap ₹ Cr',pe:'P/E',roe:'ROE %',debt_equity:'Debt/equity',dividend_yield:'Div yield %',asof:'Candle date',freshness:'Data',security_id:'Dhan ID',metadata_asof:'Fundamentals date'};
const VIEWS={
 Overview:['symbol','exchange','sector','fno','price','change_pct','volume','avg_volume','rvol','asof','freshness'],
 Technical:['symbol','price','sma20','sma50','sma200','rsi','rvol','atr_pct','high52','low52','asof'],
 Performance:['symbol','price','change_pct','perf_week','perf_month','perf_quarter','volume','asof'],
 Fundamental:['symbol','exchange','security_id','market_cap_cr','pe','roe','debt_equity','dividend_yield','industry','metadata_asof']
};
const SORTABLE=['symbol','company','exchange','sector','price','change_pct','volume','avg_volume','rvol','rsi','atr_pct','sma20','sma50','sma200','perf_week','perf_month','perf_quarter','market_cap_cr','pe','roe','debt_equity','dividend_yield','asof'];
const GROUPS={
 Descriptive:['exchange','fno','sector','industry','index','price_min','price_max','avg_volume_min','freshness'],
 Fundamental:['market_cap_cr_min','market_cap_cr_max','pe_max','roe_min','debt_equity_max','dividend_yield_min'],
 Technical:['sma20','sma50','sma200','rsi_min','rsi_max','rvol_min','change_pct_min','change_pct_max','perf_week_min','perf_month_min','pattern','high52']
};
const FILTER_LABELS={exchange:'Exchange',fno:'F&O eligible',sector:'Sector',industry:'Industry',index:'Index membership',
 price_min:'Price above ₹',price_max:'Price below ₹',avg_volume_min:'Average volume ≥ shares',freshness:'Candle freshness',
 market_cap_cr_min:'Market cap ≥ ₹ Cr',market_cap_cr_max:'Market cap ≤ ₹ Cr',pe_max:'P/E ≤',roe_min:'ROE ≥ %',
 debt_equity_max:'Debt / equity ≤',dividend_yield_min:'Dividend yield ≥ %',sma20:'20-day SMA',sma50:'50-day SMA',sma200:'200-day SMA',
 rsi_min:'RSI ≥',rsi_max:'RSI ≤',rvol_min:'Relative volume ≥',change_pct_min:'Daily change ≥ %',change_pct_max:'Daily change ≤ %',
 perf_week_min:'1-week return ≥ %',perf_month_min:'1-month return ≥ %',pattern:'Candlestick',high52:'52-week range'};
function savedPresets(){try{const x=JSON.parse(localStorage.getItem('bharat-scanner-presets')||'{}');return x&&typeof x==='object'&&!Array.isArray(x)?x:{};}catch{return {}}}
function display(key,value){
 if(value==null)return '—';if(key==='fno')return value?'Yes':'No';
 if(typeof value==='number')return value.toLocaleString('en-IN',{maximumFractionDigits:['volume','avg_volume'].includes(key)?0:2});
 return String(value);
}
export default function ScannerPanel({onAnalyse}){
 const [data,setData]=useState({rows:[],facets:{},refresh:{},coverage:{}});
 const [filters,setFilters]=useState({});const [group,setGroup]=useState('Descriptive');const [view,setView]=useState('Overview');
 const [settings,setSettings]=useState(BASE);const [sort,setSort]=useState('symbol');const [order,setOrder]=useState('asc');
 const [page,setPage]=useState(1);const [size,setSize]=useState(25);const [error,setError]=useState('');
 const [busy,setBusy]=useState(false);const [reload,setReload]=useState(0);const [poll,setPoll]=useState('10');
 const [presets,setPresets]=useState(savedPresets);const [preset,setPreset]=useState('');const [presetName,setPresetName]=useState('');
 const [file,setFile]=useState(null);const [importMessage,setImportMessage]=useState('');
 const params=new URLSearchParams({filters:JSON.stringify(filters),sort,order,page:String(page),page_size:String(size)}).toString();
 useEffect(()=>{
   let alive=true;
   const load=()=>api('/api/v1/market-insights/scanner?'+params).then(d=>{if(alive){setData(d);setError('');}}).catch(err=>{if(alive)setError(err.message)});
   const first=setTimeout(load,200);const id=poll==='off'?null:setInterval(load,Number(poll)*1000);
   return()=>{alive=false;clearTimeout(first);if(id)clearInterval(id)};
 },[params,poll,reload]);
 const put=(k,v)=>{setFilters(old=>{const next={...old};if(v==='')delete next[k];else next[k]=v;return next});setPage(1);setPreset('')};
 const action=async(path,body)=>{
   setBusy(true);setError('');
   try{await api('/api/v1/market-insights/scanner/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});setReload(x=>x+1);}
   catch(err){setError(err.message)}finally{setBusy(false)}
 };
 const running=data.refresh.status==='RUNNING';
 const changed=['universe','exchange','symbols'].some(k=>data.coverage.selection?.[k]!==settings[k]);
 const updatePresets=next=>{try{localStorage.setItem('bharat-scanner-presets',JSON.stringify(next));setPresets(next)}catch{setError('Browser storage unavailable; preset was not saved')}};
 const choosePreset=value=>{
   setPreset(value);setPage(1);
   if(value.startsWith('built:'))setFilters({...BUILTINS[value.slice(6)]});
   else if(value.startsWith('saved:')){const p=presets[value.slice(6)];if(p){setFilters(p.filters||{});setSort(p.sort||'symbol');setOrder(p.order||'asc');setView(p.view||'Overview')}}
 };
 const save=()=>{
   const name=presetName.trim();if(!name||name.length>60){setError('Enter a preset name of 1–60 characters');return}
   if(Object.keys(presets).length>=20&&!Object.hasOwn(presets,name)){setError('Maximum 20 saved presets');return}
   updatePresets({...presets,[name]:{filters,sort,order,view}});setPreset('saved:'+name);setPresetName('');
 };
 const control=(key)=>{
   let choices=null;
   if(key==='exchange')choices=[['NSE','NSE'],['BSE','BSE']];
   if(key==='fno')choices=[['yes','F&O stocks'],['no','Cash only']];
   if(['sector','industry','index'].includes(key))choices=(data.facets[key]||[]).map(x=>[x,x]);
   if(key==='freshness')choices=[['fresh','Latest expected session'],['stale','Older candles']];
   if(key.startsWith('sma'))choices=[['above','Price above SMA'],['below','Price below SMA'],['cross_up','Crossed above'],['cross_down','Crossed below']];
   if(key==='pattern')choices=[['doji','Doji'],['bullish_engulfing','Bullish engulfing']];
   if(key==='high52')choices=[['near_high','Within 5% of high'],['near_low','Within 5% of low']];
   if(key==='avg_volume_min')choices=[['100000','1 lakh'],['500000','5 lakh'],['1000000','10 lakh'],['2000000','20 lakh'],['5000000','50 lakh']];
   return e('label',{key,htmlFor:'scan-'+key},FILTER_LABELS[key],choices?
     e('select',{id:'scan-'+key,value:filters[key]??'',onChange:ev=>put(key,ev.target.value)},
       e('option',{value:''},'Any'),...choices.map(([v,t])=>e('option',{key:v,value:v},t))):
     e('input',{id:'scan-'+key,type:'number',step:'any',placeholder:'Any',value:filters[key]??'',onChange:ev=>put(key,ev.target.value)}));
 };
 const exportURL='/api/v1/market-insights/scanner/export?'+params;
 return e('div',{className:'stock-scanner'},
   e('div',{className:'scanner-title'},e('div',null,e('h2',null,'Indian Stock Scanner'),
     e('p',null,'NSE / BSE · Completed daily candles · ₹ INR')),
     e('span',{className:'badge'},'READ-ONLY RESEARCH')),
   e('details',{className:'scanner-universe',open:data.loaded===0},
     e('summary',null,'Data universe & refresh · ',data.coverage.selection?.universe==='all'?'All mapped cash equities':'F&O cash equities',
       ' · ',data.loaded||0,' loaded'),
     e('div',{className:'scanner-source-controls'},
       e('label',null,'Universe',e('select',{value:settings.universe,onChange:ev=>setSettings({...settings,universe:ev.target.value})},e('option',{value:'fno'},'F&O cash stocks'),e('option',{value:'all'},'All listed cash stocks'))),
       e('label',null,'Fetch exchange',e('select',{value:settings.exchange,onChange:ev=>setSettings({...settings,exchange:ev.target.value})},...['NSE','BSE','ALL'].map(x=>e('option',{value:x,key:x},x)))),
       e('label',null,'Batch size',e('select',{value:settings.limit,onChange:ev=>setSettings({...settings,limit:Number(ev.target.value)})},...[25,50,100,200,500].map(x=>e('option',{value:x,key:x},x)))),
       e('label',{className:'scanner-symbols'},'Optional exact symbols / Dhan IDs (comma separated)',e('input',{value:settings.symbols,onChange:ev=>setSettings({...settings,symbols:ev.target.value}),placeholder:'RELIANCE, INFY or 2885'})),
       e('button',{disabled:busy||running,onClick:()=>action('refresh',{...settings,offset:0})},'Load / refresh first batch'),
       e('button',{disabled:busy||running||changed||!data.coverage.has_more,onClick:()=>action('refresh',{...settings,offset:data.coverage.next_offset})},'Load next batch'),
       running?e('button',{onClick:()=>action('cancel',{})},'Cancel scan'):null),
     e('p',{className:'small muted'},'One background Dhan request at a time. Reuses cached completed-session features; intraday jobs share the broker lock. Loading all listed stocks may require multiple batches. Filters below apply to loaded data.'),
     changed&&data.loaded?e('p',{className:'small'},'Universe selection changed. Load the first batch before continuing. Existing results still show the previous selection.'):null),
   e('div',{className:'scanner-toolbar'},
     e('label',null,'My presets',e('select',{value:preset,onChange:ev=>choosePreset(ev.target.value)},
       e('option',{value:''},'Custom filters'),e('optgroup',{label:'Built-in'},...Object.keys(BUILTINS).map(x=>e('option',{key:x,value:'built:'+x},x))),
       e('optgroup',{label:'Saved in this browser'},...Object.keys(presets).map(x=>e('option',{key:x,value:'saved:'+x},x))))),
     e('label',null,'Order by',e('select',{value:sort,onChange:ev=>{setSort(ev.target.value);setPage(1)}},...SORTABLE.map(x=>e('option',{key:x,value:x},LABELS[x]||x)))),
     e('label',null,'Direction',e('select',{value:order,onChange:ev=>setOrder(ev.target.value)},e('option',{value:'asc'},'Ascending'),e('option',{value:'desc'},'Descending'))),
     e('label',null,'Signal',e('select',{value:filters.signal||'',onChange:ev=>put('signal',ev.target.value)},
       ...[['','All stocks'],['uptrend','SMA uptrend'],['downtrend','SMA downtrend'],['breakout20','20D breakout'],['breakdown20','20D breakdown'],['high_volume','Relative volume ≥2'],['cross20_up','Crossed SMA20 above'],['cross20_down','Crossed SMA20 below']].map(([v,t])=>e('option',{value:v,key:v},t)))),
     e('label',null,'Search loaded stocks',e('input',{value:filters.search||'',onChange:ev=>put('search',ev.target.value),placeholder:'Symbol, company, ID'}))),
   e('div',{className:'scanner-filter-box'},
     e('div',{className:'scanner-group-tabs'},
       ...[...Object.keys(GROUPS),'All'].map(name=>e('button',{key:name,className:group===name?'active':'',onClick:()=>setGroup(name)},name,
         e('span',null,(name==='All'?Object.values(GROUPS).flat():GROUPS[name]).filter(k=>filters[k]!=null&&filters[k]!=='').length||''))),
       e('button',{className:'scanner-reset',onClick:()=>{setFilters({});setPage(1);setPreset('')}},'Reset filters')),
     e('div',{className:'scanner-filter-grid'},...(group==='All'?Object.values(GROUPS).flat():GROUPS[group]).map(control)),
     ['Fundamental','All'].includes(group)?e('p',{className:'small muted'},'Fundamentals available for ',data.metadata_covered||0,' loaded rows. Missing or expired values never pass an active filter; import dated metadata below.'):null,
     ['Descriptive','All'].includes(group)&&!data.facets.sector?.length?e('p',{className:'small muted'},'Sector, industry and index dropdowns populate from dated metadata imports.'):null),
   e('div',{className:'scanner-preset-save'},e('input',{value:presetName,onChange:ev=>setPresetName(ev.target.value),placeholder:'Name this preset',maxLength:60,'aria-label':'New preset name'}),
     e('button',{onClick:save},'Save preset'),preset.startsWith('saved:')?e('button',{onClick:()=>{const next={...presets};delete next[preset.slice(6)];updatePresets(next);setPreset('')}},'Delete selected preset'):null),
   error?e('div',{className:'notice warning',role:'alert'},error):null,
   data.refresh.error?e('div',{className:'notice warning'},data.refresh.error):null,
   e('div',{className:'scanner-results-bar'},
     e('div',{className:'scanner-view-tabs'},...Object.keys(VIEWS).map(name=>e('button',{key:name,className:view===name?'active':'',onClick:()=>setView(name)},name))),
     e('label',null,'Table refresh ',e('select',{value:poll,onChange:ev=>setPoll(ev.target.value)},e('option',{value:'10'},'10 sec'),e('option',{value:'60'},'1 min'),e('option',{value:'off'},'Off'))),
     e('a',{className:'scanner-export',href:exportURL},'Export filtered CSV')),
   e('div',{className:'scanner-status',role:'status'},
     e('strong',null,data.total||0,' matches'), ' / ',data.loaded||0,' loaded · Mapped universe: ',data.coverage.available_master??'not loaded',
     ' · ',data.refresh.status||'IDLE',running?` ${data.refresh.completed||0}/${data.refresh.requested||0} · ${data.refresh.current_symbol||''}`:'',
     ' · Saved: ',data.coverage.saved_at||'—',
     data.refresh.previous_retained?' · Previous data retained after failed refresh':''),
   e('div',{className:'scanner-table-wrap'},e('table',{className:'scanner-table'},
     e('thead',null,e('tr',null,e('th',null,'#'),...VIEWS[view].map(key=>e('th',{key},
       SORTABLE.includes(key)?e('button',{onClick:()=>{setSort(key);setOrder(sort===key&&order==='asc'?'desc':'asc');setPage(1)}},LABELS[key],sort===key?(order==='asc'?' ↑':' ↓'):''):LABELS[key])))),
     e('tbody',null,...data.rows.map((row,i)=>e('tr',{key:row.key},
       e('td',null,((data.page||1)-1)*size+i+1),
       ...VIEWS[view].map(key=>e('td',{key,className:['change_pct','perf_week','perf_month','perf_quarter'].includes(key)?row[key]>0?'positive-text':row[key]<0?'negative-text':'':''},
         key==='symbol'?e('button',{className:'scanner-stock-link',title:row.company+' · '+row.exchange+' · ID '+row.security_id,onClick:()=>onAnalyse(row.symbol)},row.symbol):
         key==='freshness'?e('span',{className:row.freshness==='FRESH'?'scanner-fresh':'scanner-stale'},row.freshness):display(key,row[key])))))))),
   !data.rows.length?e('div',{className:'scanner-empty'},data.loaded?'No loaded stocks match these filters. Reset filters or load the next batch.':'Load a batch to start scanning Indian stocks. Your Dhan data access must be active.'):null,
   e('div',{className:'scanner-pagination'},
     e('button',{disabled:(data.page||1)<=1,onClick:()=>setPage((data.page||1)-1)},'← Previous'),
     e('span',null,'Page ',data.page||1,' / ',data.pages||1),
     e('button',{disabled:(data.page||1)>=(data.pages||1),onClick:()=>setPage((data.page||1)+1)},'Next →'),
     e('label',null,'Rows ',e('select',{value:size,onChange:ev=>{setSize(Number(ev.target.value));setPage(1)}},...[25,50,100].map(x=>e('option',{key:x,value:x},x))))),
   (data.refresh.coverage?.failures||data.coverage.failures||[]).length?e('details',{className:'scanner-errors'},e('summary',null,'Unavailable stocks / source errors'),
     ...(data.refresh.coverage?.failures||data.coverage.failures).map((x,i)=>e('p',{key:i},x.symbol,': ',x.error))):null,
   e('details',{className:'scanner-import'},e('summary',null,'Import sector, index and fundamental data'),
     e('p',{className:'small'},'Use a dated CSV from your own source. Match by exchange and Dhan Security ID (shown in Fundamental view/export), not guessed names. Source URLs and dates are required. Imports replace the scanner metadata only; data older than 180 days is ignored.'),
     e('a',{href:'/api/v1/market-insights/scanner/metadata-template'},'Download CSV headers'),
     e('div',{className:'scanner-preset-save'},e('input',{type:'file',accept:'.csv,text/csv','aria-label':'Scanner metadata CSV',onChange:ev=>setFile(ev.target.files?.[0]||null)}),
       e('button',{disabled:!file||busy,onClick:async()=>{
         setBusy(true);setError('');setImportMessage('');try{const form=new FormData();form.append('file',file);
           const r=await api('/api/v1/market-insights/scanner/metadata',{method:'POST',body:form});setImportMessage(`${r.rows} metadata rows imported`);setReload(x=>x+1);
         }catch(err){setError(err.message)}finally{setBusy(false)}
       }},'Import metadata')),
     importMessage?e('p',{role:'status'},importMessage):null),
   e('p',{className:'small muted'},'Daily change = latest completed close vs prior close. Relative volume = completed-session volume / preceding 20-session average. Table polling does not fetch live prices. Presets are saved in this browser. ',data.note||''));
}
