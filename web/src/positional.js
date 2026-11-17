import React,{useEffect,useState} from 'react';
import UniverseCoverage from './universe';
const e=React.createElement;
const money=x=>x==null?'—':'₹'+Number(x).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2});
export default function PositionalPanel(){
 const [data,setData]=useState({rows:[],coverage:{},refresh:{},sources:[]});
 const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [reload,setReload]=useState(0);
 const [timeframe,setTimeframe]=useState('');const [strategy,setStrategy]=useState('');const [search,setSearch]=useState('');const [ready,setReady]=useState(false);
 useEffect(()=>{let alive=true;const load=async()=>{try{const r=await fetch('/api/v1/market-insights/positional');if(!r.ok)throw Error('Could not load positional scan');const d=await r.json();if(alive){setData(d);setError('')}}catch(ex){if(alive)setError(ex.message)}};
 load();const id=setInterval(load,10000);return()=>{alive=false;clearInterval(id)}},[reload]);
 const refresh=async()=>{setBusy(true);setError('');try{const r=await fetch('/api/v1/market-insights/positional/refresh',{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.error||d.status);setReload(x=>x+1)}catch(ex){setError(ex.message)}finally{setBusy(false)}};
 const rows=data.rows.filter(r=>(!timeframe||(r.timeframe==='Daily'?'1D':r.timeframe.includes('INTRADAY')?'15m':r.timeframe)===timeframe)&&(!strategy||r.strategy===strategy)&&(!ready||r.status==='READY — REVIEW ENTRY')&&(`${r.symbol} ${r.company}`).toLowerCase().includes(search.toLowerCase()));
 const daily=rows.filter(r=>!r.timeframe.includes('INTRADAY')),intraday=rows.filter(r=>r.timeframe.includes('INTRADAY'));
 const table=(list,title)=>e('section',{className:'panel positional-results'},e('h3',null,title),
  e('div',{className:'scanner-table-wrap'},e('table',{className:'scanner-table'},
   e('thead',null,e('tr',null,...['Stock / strategy','Entry reference','Target 1','Target 2','SL','Last 5m close','Status / reason'].map(x=>e('th',{key:x},x)))),
   e('tbody',null,...list.map(r=>e('tr',{key:r.key},
    e('td',null,e('strong',null,r.symbol),e('small',null,r.exchange+' · '+r.side),e('small',null,r.strategy+' · '+r.timeframe),e('small',null,'Signal: '+r.signal_at),e('small',null,'Last checked: '+(r.checked_at||'—'))),
    e('td',null,money(r.entry)),e('td',null,money(r.t1)),e('td',null,money(r.t2)),e('td',null,money(r.sl),e('small',null,r.risk_pct+'% risk')),
    e('td',null,money(r.last_price),e('small',null,r.price_at||'Awaiting completed market candle')),
    e('td',{className:'positional-reason'},e('strong',{className:r.status.startsWith('READY')?'positive-text':'muted'},r.status),e('p',null,r.reason),
     e('details',null,e('summary',null,'Entry, targets & exit rules'),e('p',null,r.entry_basis),e('p',null,r.target_basis),e('p',null,r.exit_rule),r.ema9!=null?e('p',null,'EMA9: ',money(r.ema9),' · Trendline: ',money(r.trendline),' · Volume: ',r.volume_ratio.toFixed(2),'× · ',r.adjustment_status,' · Anchors: ',r.pivot1_at,' (',money(r.pivot1_price),') → ',r.pivot2_at,' (',money(r.pivot2_price),')'):null))))))),
  !list.length?e('p',{className:'scanner-empty'},data.updated_at?'No qualifying setups in this scan/filter. Check coverage and source errors below.':'Waiting for the first background scan.'):null);
 return e('div',{className:'positional-panel'},
  e('section',{className:'panel'},e('div',{className:'scanner-title'},e('div',null,e('h2',null,'Positional stock watchlist'),e('p',null,'Daily + EMA9 multi-timeframe setups · 5-minute background checks')),
   e('button',{onClick:refresh,disabled:busy||data.refresh.status==='RUNNING'},busy?'Requesting…':'Check now')),
   e('p',{role:'status'},e('strong',null,data.refresh.status||'Waiting'),' · Last completed scan: ',data.updated_at||'Not yet run',
     data.refresh.status==='RUNNING'?` · ${data.refresh.completed||0}/${data.refresh.total||'…'} stocks`:''),
   e('p',{className:'small muted'},'Mapped: ',data.coverage.mapped??'—',' · Selected: ',data.coverage.selected??'—',' · Scanned: ',data.coverage.scanned??'—',' · Valid daily charts: ',data.coverage.eligible??'—',' · Not checked this cycle: ',data.coverage.omitted??'—'),
   e(UniverseCoverage,{data:data.coverage.membership}),
   e('p',null,'Across rotating batches: ',data.coverage.unique_attempted??0,' attempted · ',data.coverage.unique_assessed??0,' assessed · ',data.coverage.remaining??'—',' pending for the current completed daily session.'),
   data.coverage.budget_exhausted?e('p',{className:'notice warning'},'Cycle time budget reached. Saved progress will resume in the next cycle.'):null,
   e('p',{className:'small'},'Background scans run while the backend stays open, even when you leave this tab. Daily candles confirm after 15:40 IST; five-minute checks do not turn unfinished daily candles into signals. Universe: NIFTY 500 eligible NSE equities, mapped by ISIN. Discovery rotates through batches of 25 (INSIGHTS_POSITIONAL_BATCH_SIZE); existing setups get a separate bounded monitoring lane. Initial full coverage takes multiple cycles and depends on source response time. Individual rows expire after 10 minutes without a check. Legacy INSIGHTS_MAX_SYMBOLS and INSIGHTS_WATCHLIST do not truncate this universe.'),
   error?e('p',{className:'notice warning',role:'alert'},error):null,
   data.refresh.error?e('p',{className:'notice warning'},data.refresh.error):null,
   data.stale&&data.updated_at?e('p',{className:'notice warning'},'Scan is stale or failed. Previous rows are for inspection only.'):null),
  e('section',{className:'panel'},e('div',{className:'positional-filters'},
   e('label',null,'Search stock',e('input',{value:search,onChange:ev=>setSearch(ev.target.value),placeholder:'Stock name'})),
   e('label',null,'Strategy',e('select',{value:strategy,onChange:ev=>setStrategy(ev.target.value)},e('option',{value:''},'All strategies'),
    ...['EMA9 Trendline + Volume','PDF Morning Star','PDF Supertrend + RSI','Donchian 20D breakout','Moving Momentum','PDF R1 + Supertrend','PDF S1 + Supertrend'].map(s=>e('option',{key:s,value:s},s)))),
   e('label',null,'Timeframe',e('select',{value:timeframe,onChange:ev=>setTimeframe(ev.target.value)},...['','1H','1D','1W','1M','15m'].map(t=>e('option',{value:t,key:t},t||'All timeframes')))),
   e('label',null,e('input',{type:'checkbox',checked:ready,onChange:ev=>setReady(ev.target.checked)}),' Ready for entry review only'))),
  table(daily,'Positional / swing setups'),
  e('p',{className:'notice warning'},'The PDF’s R1/S1 strategy is intraday only. Its positions must not be treated as overnight positional trades.'),
  table(intraday,'PDF companion: R1 / S1 intraday setups'),
  e('section',{className:'panel'},e('h3',null,'Rules and data coverage'),
   e('p',null,'EMA9 Trendline + Volume checks closed 1H/1D/1W/1M candles independently. Confirmed lower highs (5 bars on each side), fresh descending-line cross, close above EMA9 and volume >1.5× prior 20-bar mean. SL: prior 10-bar low; T1: added 1.5R; T2: specified 3R. Minimum 60 bars; risk capped at 15%. EMA9 rows remain research watches unless adjusted data is confirmed and the complete post-signal 5m price path is available.'),
   e('details',null,e('summary',null,'EMA9 timeframe coverage'),...(data.coverage.ema9_checks||[]).map((x,i)=>e('p',{key:i,className:'small'},x.symbol,' · ',x.timeframe,' · ',x.bars??'—',' bars · ',x.status))),
   e('p',null,'Morning Star uses quantified candle-body rules and downtrend context. Supertrend + RSI uses the PDF’s 3% SL. Both have a five-session exit rule. The two daily targets are added at 1.5R and 2.5R; they were not fixed targets in the PDF. R1/S1 setups require room to R2/S2 beyond the first 2% target.'),
   e('p',null,'Added setups: a 20-day Donchian breakout with trend/volume filters, and Moving Momentum (SMA20/150, Stochastic pullback, MACD histogram turn). These are testable adaptations, not a claim of superior returns. Liquidity filter: price ≥₹20, average volume ≥1 lakh and average turnover proxy ≥₹1 crore.'),
   e('p',null,'READY means the most recent completed 5m close is within 1% beyond the entry reference. It is not a fill or live executable quote. SL/target touches are conservative observations, not portfolio tracking. PDF daily watches stay for five completed sessions after their signal, with older signals marked track-only. This is signal-age monitoring, not tracking an actual purchase; apply the five-day hold from your own fill date. Event/news filters are not automated.'),
   ...(data.sources||[]).map(s=>e('p',{key:s.name,className:'small'},s.url?e('a',{href:s.url,target:'_blank',rel:'noreferrer'},s.name):s.name,' — ',s.strategies)),
   e('details',null,e('summary',null,'Source errors: '+(data.coverage.errors||[]).length),...(data.coverage.errors||[]).map((x,i)=>e('p',{key:i},x.symbol,': ',x.error))),
   e('p',{className:'small muted'},data.note)));
}
