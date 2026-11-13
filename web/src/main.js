import React, {useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createChart, CandlestickSeries, HistogramSeries} from 'lightweight-charts';
import './styles.css';
const e=React.createElement;
const RISK='Rule-based analytics, not investment advice. Entries and targets are not guaranteed. Trading carries risk of loss. No orders are placed.';
const tabs=[['Dashboard','▦'],['Analyse','⌕'],['Pre-Market 8 AM','☼'],['Intraday','↗'],['BTST','◷'],['FII Stock Deals','⇄'],['Index Options','⌁'],['F&O Stocks','≋'],['Swing Trades','↝'],['Multibagger','✦'],['Track Record','▤']];
const route={'Dashboard':'dashboard','Analyse':'analyse','Pre-Market 8 AM':'pre-market','Intraday':'intraday','BTST':'btst','FII Stock Deals':'fii-stock-deals','Index Options':'index-options','F&O Stocks':'fo-stocks','Swing Trades':'swing-trades','Multibagger':'multibagger','Track Record':'track-record'};
async function api(url,options={}){const res=await fetch(url,{...options,headers:{Accept:'application/json',...(options.headers||{})},cache:'no-store'});const body=await res.json();if(!res.ok)throw Error(body.error||`HTTP ${res.status}`);return body;}
function Text({children,muted=false}){return e('span',{className:muted?'muted':''},children);}
function Badge({children,type=''}){return e('span',{className:`badge ${type}`},children);}
function Tile({title,value,sub,accent}){return e('div',{className:'tile'},e('div',{className:'kicker'},title),e('div',{className:'tile-value',style:{color:accent||'var(--ink)'}},value??'—'),e('div',{className:'small muted'},sub||''));}
function Notice({children,warning=false}){return e('div',{className:warning?'notice warning':'notice'},children);}
function Section({title,children,extra}){return e('section',{className:'section'},e('div',{className:'section-head'},e('h3',null,title),extra||null),children);}
const price=n=>typeof n==='number'&&Number.isFinite(n)?'₹'+n.toLocaleString('en-IN',{maximumFractionDigits:2}):'—';
function Signals({items=[],empty='No validated signals available.'}){
 if(!items.length)return e('div',{className:'empty'},empty);
 return e('div',{className:'signal-grid'},items.map((s,i)=>e('article',{className:'signal',key:(s.symbol||'')+(s.signal_at||'')+i},
   e('div',{className:'signal-top'},e('div',null,e('h3',null,s.symbol||s.underlying),e(Text,{muted:true},s.strategy||'Rule-based candidate')),
   e(Badge,{type:s.direction==='BUY'||s.direction==='CE'?'positive':'negative'},s.direction||'WATCH')),
   e('div',{className:'levels'},e('div',null,e('label',null,'Entry'),e('b',null,price(s.entry))),e('div',null,e('label',null,'Stop-loss'),e('b',{className:'loss'},price(s.sl))),e('div',null,e('label',null,'Target 1'),e('b',null,price(s.t1))),e('div',null,e('label',null,'Target 2'),e('b',null,price(s.t2)))),
   e('div',{className:'signal-foot'},e('span',null,'R:R ',s.rr??'—'),e('span',null,'Rank ',s.ai_score??s.confidence??'—'),e('span',null,'As of ',s.signal_at||'—')),
   s.rvol!=null?e('p',{className:'small muted'},'5m relative volume: ',s.rvol,'×'):null,
   s.mtf?e('p',{className:'small muted'},'Multi-timeframe: ',
     Object.entries(s.mtf).map(([k,v])=>k+' '+v).join(' · ')):null,
   s.order_flow_proxy?e('p',{className:'small muted'},'Flow evidence: ',s.order_flow_proxy):null,
   s.gann_wave?e('p',{className:'small muted'},
      'Gann levels ',s.gann_wave.gann?.support??'—',' / ',s.gann_wave.gann?.resistance??'—',
      ' · Time cycles ',(s.gann_wave.time_cycle?.near_cycle_minutes||[]).join(', ')||'None',
      ' · Swing-wave ',s.gann_wave.wave?.structure||'UNAVAILABLE',
      ' · alignment ',s.wave_alignment||'UNAVAILABLE'):null,
   e(Badge,{type:'warning'},s.status||s.backtest_status||'RESEARCH ONLY'),
   (s.warnings||[]).length?e('p',{className:'small loss'},s.warnings.join(' · ')):null,
   e('details',null,e('summary',null,'Why this candidate?'),e('ul',null,...(s.reasons||['Awaiting qualifying rules']).map((v,j)=>e('li',{key:j},v)))))));
}
function PriceChart({candles=[],fib=null}){
 const ref=useRef(null);
 useEffect(()=>{
  if(!ref.current||!candles.length)return;
  const chart=createChart(ref.current,{width:ref.current.clientWidth||640,height:280,
   layout:{background:{color:getComputedStyle(ref.current).getPropertyValue('--panel').trim()||'#111d30'},textColor:getComputedStyle(ref.current).getPropertyValue('--muted').trim()||'#9da9bd'},
   grid:{vertLines:{visible:false},horzLines:{color:'#233349'}}});
  const series=chart.addSeries(CandlestickSeries,{upColor:'#41cba5',downColor:'#ef6576',borderVisible:false,wickUpColor:'#41cba5',wickDownColor:'#ef6576'});
  series.setData(candles.map(c=>({time:c.time,open:c.open,high:c.high,low:c.low,close:c.close})));
  if(fib)for(const level of ['0','0.44','0.5','0.56','1']){
    const v=Number(fib[level]);
    if(!Number.isFinite(v)||v<=0)continue;
    series.createPriceLine({price:v,color:level==='0.44'?'#eeb95f':level==='0.5'?'#77adfa':level==='1'?'#62dbb8':level==='0.56'?'#d993e9':'#ff8b9b',
      lineWidth:1,lineStyle:2,axisLabelVisible:true,title:'Fib '+level});
  }
  chart.timeScale().fitContent();
  const obs=new ResizeObserver(()=>chart.applyOptions({width:ref.current?.clientWidth||640}));obs.observe(ref.current);
  return()=>{obs.disconnect();chart.remove();};
 },[candles,fib]);
 return candles.length?e('div',{className:'chart',ref}):e('p',{className:'muted'},'Price candles not available from Dhan.');
}
function OiChart({strikes=[]}){
 const ref=useRef(null);
 useEffect(()=>{
  if(!ref.current||!strikes.length)return;
  const width=ref.current.clientWidth||640;
  const chart=createChart(ref.current,{width,height:300,layout:{background:{color:getComputedStyle(ref.current).getPropertyValue('--panel').trim()||'#111d30'},textColor:getComputedStyle(ref.current).getPropertyValue('--muted').trim()||'#9da9bd'},grid:{vertLines:{visible:false},horzLines:{color:'#233349'}},rightPriceScale:{borderVisible:false}});
  // Lightweight Charts' required time axis is mapped to each ordered strike. Labels display strike prices.
  const origin=1577836800;const ts=(i)=>origin+i*86400;
  const call=chart.addSeries(HistogramSeries,{color:'#ef6576',priceFormat:{type:'volume'},priceScaleId:'right'});
  const put=chart.addSeries(HistogramSeries,{color:'#41cba5',priceFormat:{type:'volume'},priceScaleId:'right'});
  call.setData(strikes.map((s,i)=>({time:ts(i),value:Number(s.ce_oi)||0})));
  put.setData(strikes.map((s,i)=>({time:ts(i)+43200,value:Number(s.pe_oi)||0})));
  chart.timeScale().applyOptions({tickMarkFormatter:(time)=>{
   const ix=Math.floor((Number(time)-origin)/86400);return strikes[ix]?.strike?.toLocaleString('en-IN')||'';}});
  chart.timeScale().fitContent();
  const obs=new ResizeObserver(()=>chart.applyOptions({width:ref.current?.clientWidth||width}));obs.observe(ref.current);
  return()=>{obs.disconnect();chart.remove();};
 },[strikes]);
 return e('div',null,e('div',{className:'legend'},e('span',null,'● Call OI'),e('span',null,'● Put OI'),e('small',{className:'muted'},'X axis: mapped strike levels')),e('div',{ref,className:'chart'}));
}
function ParticipantRings({report}){
 const rows=[['FII','FII','Outer'],['PRO','Pro','Middle'],['CLIENT','Retail / Client','Inner']];
 const rings=[{r:120,key:'FII'},{r:88,key:'PRO'},{r:56,key:'CLIENT'}];
 const members=report?.participants||{};
 const tint=dir=>dir==='UP'?'var(--green)':dir==='DOWN'?'var(--red)':'var(--muted)';
 const overall=report?.overall_direction||'UNAVAILABLE';
 const display=(n,unit='')=>typeof n==='number'&&Number.isFinite(n)?
   (n>0?'+':'')+n.toLocaleString('en-IN',{maximumFractionDigits:2})+unit:'—';
 return e('div',{className:'participant-grid'},
   e('div',{className:'participant-visual'},
     e('svg',{viewBox:'0 0 320 320',role:'img',
        'aria-label':'Nested participant positioning circles: FII outer, Pro middle, Retail inner',
        className:'participant-rings'},
       ...rings.flatMap(({r,key})=>[
         e('circle',{key:key+'-bg',cx:160,cy:160,r,fill:'none',
               stroke:'var(--line)',strokeWidth:22}),
         e('circle',{key:key+'-signal',cx:160,cy:160,r,fill:'none',
               stroke:tint(members[key]?.direction),strokeWidth:19})
       ]),
       e('text',{x:160,y:154,textAnchor:'middle',className:'participant-centre-caption'},'BIAS'),
       e('text',{x:160,y:178,textAnchor:'middle',className:'participant-centre-value'},overall)
     ),
     e('p',{className:'small muted'},'Outside to inside: FII · Pro · Client (Retail)')),
   e('div',{className:'participant-legend'},
     ...rows.map(([key,name,ring])=>{
       const item=members[key]||{};
       return e('div',{key,className:'participant-legend-item'},
          e('div',{className:'participant-legend-heading'},
             e('span',{className:'participant-swatch',
               style:{background:tint(item.direction)}}),
             e('strong',null,name),
             e('span',{className:'small muted'},ring+' circle'),
             e('b',{style:{color:tint(item.direction)}},item.direction||'—')),
          e('p',{className:'small muted'},'Position score: ',display(item.score),
            ' · Day-to-day score Δ: ',display(item.daily_score_change)),
          e('p',{className:'small muted'},'Index futures net: ',
              display(item.index_futures_net),
              ' · Δ from prior report: ',display(item.index_futures_net_change)),
          e('p',{className:'small muted'},'Expiry-window futures net Δ: ',
              display(item.cycle_futures_net_change),
              ' · Volume participation: ',item.volume_alignment||'UNAVAILABLE')
       );
     }))
 );
}
function ParticipantPositioning(){
 const [report,setReport]=useState({status:'LOADING — NSE DAILY REPORTS',participants:{}});
 const [loadError,setLoadError]=useState('');
 const [refresh,setRefresh]=useState(false);
 useEffect(()=>{
   let live=true;
   const load=()=>api('/api/v1/market-insights/participant-positioning')
     .then(data=>{if(live){setReport(data);setLoadError('');}})
     .catch(err=>{if(live)setLoadError('Participant archive unavailable: '+err.message);});
   load();
   const id=setInterval(load,12000);
   return()=>{live=false;clearInterval(id);};
 },[]);
 const manuallyRefresh=async()=>{
   setRefresh(true);setLoadError('');
   try{
      const res=await api('/api/v1/market-insights/participant-positioning/refresh',
                          {method:'POST'});
      if(res.status!=='STARTED')setLoadError(res.status||'NSE refresh not started');
   }catch(err){setLoadError('NSE refresh: '+err.message);}
   finally{setRefresh(false);}
 };
 const loaded=report.participants&&Object.keys(report.participants).length>0;
 return e(Section,{title:'Participant positioning · NSE FII / Pro / Retail',
   extra:e('button',{className:'refresh-btn',onClick:manuallyRefresh,disabled:refresh,
        type:'button'},refresh?'Requesting…':'↻ Refresh NSE reports')},
   e('p',{className:'small muted'},
      'Source: NSE after-close participant futures/options OI and volume reports. ',
      'These figures cover ALL index instruments and expiries, not individual expiry contracts.'),
   e('div',{className:'tile-grid'},
      e(Tile,{title:'POSITIONING BIAS',value:report.overall_direction||'UNAVAILABLE',
         sub:'Weighted FII 50% · Pro 30% · Client 20% (heuristic)'}),
      e(Tile,{title:'REPORT SESSION',value:report.trade_date||'NOT LOADED',sub:'Historical EOD, not live'}),
      e(Tile,{title:'EXPIRY OBSERVATION WINDOW',
         value:report.expiry_date||'UNVERIFIED',sub:report.cycle_label||'Not an expiry-specific breakdown'}),
      e(Tile,{title:'PARTICIPATION ALIGNMENT',
         value:report.all_aligned?'ALL THREE ALIGN':loaded?'MIXED':'UNAVAILABLE',
         sub:'This is not a forecast or win rate'})),
   loaded?e(ParticipantRings,{report}):
      e('div',{className:'empty'},'No verified NSE OI + VOL day-pair stored yet. ',
         'The scanner will retry after NSE publishes its end-of-day reports.'),
   loadError?e(Notice,{warning:true},loadError):null,
   e('p',{className:'small muted'},
       'Sync: ',report.refresh?.status||report.status||'NOT AVAILABLE',
       ' · Last attempt: ',report.refresh?.checked_at||'—',
       ' · Stored trading days: ',report.history_days??0,
       ' · Expiry window sessions observed: ',report.cycle_sessions??'—'),
   report.refresh?.failed_dates?.length?
      e('p',{className:'small muted'},'Some reports could not be retrieved: ',
        report.refresh.failed_dates.slice(0,3).map(x=>x.day+' ('+x.reason+')').join('; ')):null,
   e(Notice,{warning:true},
      'Interpretation only: futures net and directional option-position proxies can reflect hedges, spreads and multi-leg strategies. ',
      'Repeated daily OI levels are NOT summed; expiry-window changes compare stored snapshots. ',
      'No guaranteed FII-led direction or trading signal.')
 );
}

function Dashboard({data,onRefresh,refreshBusy,refreshState,refreshError}){
 const asof=data.data_asof?new Date(data.data_asof).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}):'Not available';
 const refreshed=data.updated_at?new Date(data.updated_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}):'Never';
 const lastSession=data.session_date||'Unknown';
 const mode=data.not_live?'Historical — NOT LIVE':data.data_asof?'Completed session candles':'Not loaded';

 const indices=data.indices||[],sectors=data.sectors||[];
 const find=(v)=>indices.find(x=>(x.symbol||'').toUpperCase().replace(/[^A-Z0-9]/g,'').includes(v));
 const nifty=find('NIFTY'),sensex=find('SENSEX');
 return e(React.Fragment,null,
  e('div',{className:'manual-toolbar'},
   e('div',null,e('strong',null,'Dhan market data'),e('p',{className:'muted small'},'Last completed candle: ',asof,' IST · Session: ',lastSession,' · Fetched: ',refreshed),
      e('p',{className:'muted small'},'Mode: ',mode,' · Manual refresh fetches completed candles only, even after market close.')),
   e('button',{type:'button',className:'refresh-btn',disabled:refreshBusy,onClick:onRefresh},refreshBusy?'Refreshing Dhan…':'↻ Refresh Market Data')),
  refreshError?e(Notice,{warning:true},refreshError):null,
  refreshState?.status==='NO_DATA'||refreshState?.status==='FAILED'?e(Notice,{warning:true},refreshState.message||'Market data unavailable.'):null,
  data.not_live&&data.data_asof?e(Notice,{warning:true},'HISTORICAL SNAPSHOT — NOT LIVE. Bias and changes refer to the completed session dated '+lastSession+'. Do not use these as live entry signals.'):null,
  e('div',{className:'tile-grid'},e(Tile,{title:'NIFTY 50 BIAS',value:nifty?.bias||'Awaiting data',sub:nifty?.score!=null?`Rule score: ${nifty.score}`:'EMA / VWAP / ADX / structure'}),e(Tile,{title:'SENSEX BIAS',value:sensex?.bias||'Awaiting data',sub:sensex?.score!=null?`Rule score: ${sensex.score}`:'Missing inputs are not guessed'}),e(Tile,{title:'SECTORS AVAILABLE',value:sectors.length,sub:'Dhan sector indices'}),e(Tile,{title:'MARKET DATA',value:data.status||'No connection',sub:data.updated_at||'Not updated'})),
  e(ParticipantPositioning),
  e('div',{className:'split'},
   e(Section,{title:'Index bias & underlying rules'},indices.length?indices.map((x,i)=>e('div',{className:'bias',key:i},
    e('div',{className:'bias-head'},e('b',null,x.symbol),e(Badge,{type:x.bias==='Uptrend'?'positive':x.bias==='Downtrend'?'negative':''},x.bias),e(Text,{muted:true},`Score ${x.score??'N/A'}`)),
    e('ul',{className:'reasons'},...(x.reasons||[]).map((r,k)=>e('li',{key:k},r))),
    (x.warnings||[]).length?e('p',{className:'small muted'},x.warnings.join(' · ')):null)):e('p',{className:'muted'},'Connect Dhan and provide current completed index candles to calculate bias.')),
   e(Section,{title:'Sector momentum heatmap'},sectors.length?e('div',{className:'heatmap'},sectors.map((s,i)=>e('div',{className:'heat',key:i,style:{background:s.session_change>=0?'var(--heat-green)':'var(--heat-red)'}},e('b',null,s.sector),e('strong',null,`${s.session_change>0?'+':''}${s.session_change}%`),e('small',null,`vs NIFTY ${s.relative_strength??'—'}%`)))):e('div',{className:'empty'},'Sector data unavailable. Rankings will appear only when Dhan provides verified sector candles.'))));
}
function AnalyseChooser({onSelect,busy}){
 const [choices,setChoices]=useState(null);
 const [error,setError]=useState('');
 const [refresh,setRefresh]=useState(0);
 useEffect(()=>{
  let alive=true;
  api('/api/v1/market-insights/analyse/choices')
   .then(v=>{if(alive)setChoices(v)})
   .catch(err=>{if(alive)setError(err.message)});
  return()=>{alive=false};
 },[refresh]);
 const group=(title,rows)=>e(Section,{title},
  e('div',{className:'analyse-choices'},
   ...(rows||[]).map((x,i)=>e('button',{key:i,type:'button',disabled:busy,
      className:'mover-button',onClick:()=>onSelect(x.symbol)},
      e('strong',null,x.symbol),
      x.change_pct==null?null:e('span',{className:x.change_pct>0?'gain':'loss'},
          (x.change_pct>0?'+':'')+x.change_pct.toFixed(2)+'%')))));
 return e('div',null,
  e('button',{type:'button',onClick:()=>setRefresh(v=>v+1)},'Refresh top movers'),
  e('datalist',{id:'analyse-fno-symbol-options'},
    ...(choices?.fno_symbols||[]).map((x,i)=>
      e('option',{key:i,value:x.ticker||x.symbol,label:x.symbol},
        x.symbol))),
  error?e(Notice,{warning:true},'Mover list unavailable: '+error):null,
  choices?e('div',null,
    e('p',{className:'small muted'},'Dhan quote coverage ',choices.coverage,'/',choices.universe,
       ' · ',choices.asof,' · ',choices.stale?'Market closed / stale snapshot':'Trading session'),
    e('div',{className:'analyse-selection-grid'},
      group('Mapped indices',choices.indices),
      group('Top 20 gainers',choices.gainers),
      group('Top 20 losers',choices.losers))):null,
  e('p',{className:'small muted'},
    'Manual F&O stock: type the Dhan stock name or exchange ticker in the search box below. Start typing to see mapped symbols.'));
}
function AnalyseATM({data}){
 const atm=data.atm_recommendation||{},contract=atm.contract;
 const levels=atm.entry!=null&&atm.sl!=null&&atm.t1!=null&&atm.t2!=null;
 return e(Section,{title:'ATM CE/PE option recommendation · research only'},
  e('div',{className:'tile-grid'},
    e(Tile,{title:'ATM STRIKE',value:atm.atm_strike==null?'—':price(atm.atm_strike),
      sub:contract?.expiry?'Expiry '+contract.expiry:'Expiry '+(data.expiry||'not verified')}),
    e(Tile,{title:'DIRECTION',value:atm.direction||'NO TRADE',
      sub:atm.signal_source||'Awaiting completed price confirmation'}),
    e(Tile,{title:'OPTION CONTRACT',value:contract?.symbol||'UNAVAILABLE',
      sub:contract?.security_id?'Dhan ID '+contract.security_id:'No verified Dhan contract ID'}),
    e(Tile,{title:'TRADE STATE',value:atm.status||'UNAVAILABLE',
      sub:'Quote age not verified · No broker order'})),
  e('p',{className:'small muted'},atm.reason||'No ATM assessment',
      ' · Spot: ',price(atm.spot),' · ATM distance: ',
      atm.atm_distance_pct==null?'—':atm.atm_distance_pct+'%'),
  e('p',{className:'small muted'},'Dhan best bid ',price(atm.bid),' · Best ask ',
      price(atm.ask),' · Spread ',atm.spread_pct==null?'—':atm.spread_pct+'%',
      ' · Assessment at ',atm.assessment_at||'—',
      ' (assessment time does NOT verify exchange quote freshness)'),
  levels?e('div',{className:'tile-grid'},
    e(Tile,{title:'ILLUSTRATIVE BUY ENTRY',value:price(atm.entry),sub:'Best ask from chain, NOT executable'}),
    e(Tile,{title:'ILLUSTRATIVE STOP',value:price(atm.sl),sub:'Option premium, not spot level'}),
    e(Tile,{title:'TARGET 1 · 1.5R',value:price(atm.t1)}),
    e(Tile,{title:'TARGET 2 · 2.5R',value:price(atm.t2)})):
    e('p',{className:'small muted'},'No premium entry, stop or targets until direction, listed ATM leg, contract ID and bid/ask quality are checked.'),
  e(Notice,{warning:true},atm.warning||'Research only: live contract quote timestamp and risk are not verified.'),
  e('p',{className:'small muted'},
    'Displayed ATM prices are hypothetical scenarios, not a trade instruction or calibrated success probability.'));
}
function AnalyseEvidence({data}){
 const a=data.analysis||{},mtf=a.mtf||{},plan=data.entry_plan;
 return e('div',null,
  e(AnalyseATM,{data}),
  e('div',{className:'tile-grid'},
    e(Tile,{title:'DIRECTION',value:data.bias||'UNAVAILABLE'}),
    e(Tile,{title:'SETUP SCORE',value:a.score??'—',sub:'Heuristic, not probability'}),
    e(Tile,{title:'WIN PROBABILITY',value:'UNAVAILABLE',sub:'No calibrated walk-forward model'}),
    e(Tile,{title:'CHAIN STATUS',value:data.chain_status||'UNAVAILABLE'})),
  e(Section,{title:'Multi-timeframe bias and risk plan'},
    ...['5m','15m','60m'].map(k=>e('p',{key:k,className:'small muted'},
      k,' · ',mtf[k]?.trend||'UNAVAILABLE',' · RSI ',mtf[k]?.rsi14??'—',
      ' · ',mtf[k]?.asof||'—')),
    plan?e('div',null,
      e('p',null,'Underlying ',plan.direction,
        ' · Entry ',price(plan.entry),' · SL ',price(plan.sl),
        ' · T1 ',price(plan.t1),' · T2 ',price(plan.t2)),
      e('p',{className:'small muted'},plan.entry_type,' · Risk ',plan.stop_distance_pct,'%')):
      e('p',{className:'small muted'},'NO TRADE: no verified multi-timeframe breakout and acceptable stop.')),
  e(Section,{title:'Order-flow evidence · Gann cycles · wave geometry'},
    e('p',{className:'small muted'},'Depth: ',data.market_depth?.status||'UNVERIFIED',
      ' · Bid/ask resting ratio: ',data.market_depth?.bid_ask_ratio??'—'),
    e('p',{className:'small muted'},'Gann support: ',data.gann_wave?.gann?.support??'—',
      ' · resistance: ',data.gann_wave?.gann?.resistance??'—'),
    e('p',{className:'small muted'},'Near 9:15 cycle minutes: ',
      (data.gann_wave?.time_cycle?.near_cycle_minutes||[]).join(', ')||'None',
      ' · confirmed swing pattern: ',data.gann_wave?.wave?.structure||'UNAVAILABLE'),
    e('p',{className:'small muted'},'Not executed trade flow, a validated Elliott count, or a win probability.')));
}
function Analyse({data,onSearch,busy}){
 const [symbol,setSymbol]=useState('NIFTY');const [expiry,setExpiry]=useState('');
 const m=data.metrics;
 return e(React.Fragment,null,e(AnalyseChooser,{busy,onSelect:x=>{setSymbol(x);setExpiry('');onSearch(x,'')}}),e('form',{className:'searchbox',onSubmit:ev=>{ev.preventDefault();onSearch(symbol,expiry);}},
   e('input',{value:symbol,onChange:ev=>setSymbol(ev.target.value.toUpperCase()),
       list:'analyse-fno-symbol-options',
       placeholder:'Enter any mapped F&O stock (e.g. HDFCLIFE) or index',
       maxLength:64,'aria-label':'Instrument symbol'}),
   e('input',{value:expiry,onChange:ev=>setExpiry(ev.target.value),placeholder:'Expiry YYYY-MM-DD (optional)','aria-label':'Expiry date'}),
   e('button',{type:'submit',disabled:busy},busy?'Analysing…':'Analyse stock / ATM option')),
  data.error?e(Notice,{warning:true},data.error):null,
  data.symbol?e(AnalyseEvidence,{data}):null,
  data.symbol&&!m?e(Section,{title:'Cash or index price chart'},e(PriceChart,{candles:data.candles||[]})):null,
  m?e(React.Fragment,null,
    e('div',{className:'tile-grid'},e(Tile,{title:'OPEN-INTEREST PCR',value:m.pcr}),e(Tile,{title:'MAX PAIN',value:m.max_pain}),e(Tile,{title:'OI SUPPORT',value:m.oi_support}),e(Tile,{title:'OI RESISTANCE',value:m.oi_resistance})),
    e(Section,{title:'Multi-timeframe trend and flow proxies'},
      e('p',{className:'small muted'},'5m trend: ',data.mtf?.['5m']?.trend||'UNAVAILABLE',
        ' · 15m trend: ',data.mtf?.['15m']?.trend||'UNAVAILABLE',
        ' · 60m trend: ',data.mtf?.['60m']?.trend||'UNAVAILABLE'),
      e('p',{className:'small muted'},'Last price candle: ',data.price_asof||'Unknown',
        ' · Dhan depth: ',data.market_depth?.status||'UNAVAILABLE',
        data.market_depth?.bid_ask_ratio!=null?' · Resting bid/ask ratio '+data.market_depth.bid_ask_ratio:''),
      e('p',{className:'small muted'},'OI changes and order-book quantities are positioning/liquidity proxies, not evidence of executed order flow.')),
    e(Section,{title:`Completed 5-minute price candles · ${data.symbol}`},e(PriceChart,{candles:data.candles||[]})),
    e('div',{className:'split'},e(Section,{title:`Option-chain OI · ${data.symbol} · ${data.expiry}`},e(OiChart,{strikes:m.strikes})),
     e(Section,{title:'Legacy OI-gated premium scenario'},e('p',null,`Rule-based tilt: ${data.bias||'Undetermined'}`),e('p',{className:'muted'},data.note),e('p',null,`Call OI Δ: ${m.call_change?.toLocaleString('en-IN')} · Put OI Δ: ${m.put_change?.toLocaleString('en-IN')}`),e(Notice,{warning:true},m.iv_percentile_note),e(Signals,{items:data.plan?[data.plan]:[],empty:'No validated entry/target/stop plan for this option chain.'}))))
   :data.symbol?e(Notice,null,'Optional option-chain unavailable. Underlying price research remains shown above.'):
     e(Notice,null,'Choose a mapped index or mover, or search a Dhan instrument. Quotes are retrieved only on request.'));
}
function TrackRecord({data}){
 const stats=data.stats||[],signals=data.signals||[];
 return e(React.Fragment,null,e(Notice,null,'Win rates exclude unresolved/open signals. Research candidates are not claimed as real executed trades.'),
  e(Section,{title:'Observed outcomes'},stats.length?e('div',{className:'tablewrap'},e('table',null,e('thead',null,e('tr',null,...['Strategy','Signals','Open','Wins','Losses','Expired','Observed win rate'].map(x=>e('th',{key:x},x)))),e('tbody',null,stats.map((s,i)=>e('tr',{key:i},...[s.strategy,s.total,s.open_count,s.wins,s.losses,s.expired,s.win_rate==null?'—':s.win_rate+'%'].map((v,j)=>e('td',{key:j},v??0))))))):e('div',{className:'empty'},'No outcomes recorded yet.')),
  e(Section,{title:'Historical validation (eligible only after independent walk-forward)'},
    (data.backtests||[]).length?e('div',{className:'tablewrap'},e('table',null,e('thead',null,e('tr',null,...['Strategy','Samples','Win rate','Profit factor','Average R','Eligible'].map(x=>e('th',{key:x},x)))),
      e('tbody',null,(data.backtests||[]).map((v,i)=>e('tr',{key:i},...[v.strategy,v.samples,v.win_rate??'—',v.profit_factor??'—',v.avg_r??'—',v.eligible?'YES':'NO'].map((x,j)=>e('td',{key:j},x))))))):e('p',{className:'muted'},'No independently validated strategy backtests. Trading remains disabled.')),
  e(Section,{title:'Signal journal'},signals.length?e('div',{className:'tablewrap'},e('table',null,e('thead',null,e('tr',null,...['Date','Strategy','Symbol','Direction','Entry','Stop','T1','Outcome'].map(x=>e('th',{key:x},x)))),e('tbody',null,signals.map((s,i)=>e('tr',{key:i},...[s.signal_at,s.strategy,s.symbol,s.direction,price(s.entry),price(s.sl),price(s.t1),s.status].map((v,j)=>e('td',{key:j},v))))))):e('div',{className:'empty'},'Journal is empty. Real observed outcomes will appear here.')));
}
function BTSTClosingStrength(){
 const [view,setView]=useState({status:'WAITING FOR 14:30',candidates:[]});
 const [error,setError]=useState('');
 useEffect(()=>{
   let alive=true;
   const load=()=>api('/api/v1/market-insights/btst-closing')
    .then(data=>{if(alive){setView(data);setError('');}})
    .catch(err=>{if(alive)setError(err.message);});
   load();
   const id=setInterval(load,20000);
   return()=>{alive=false;clearInterval(id);};
 },[]);
 const rows=(view.candidates||[]).map((x,i)=>{
   const cells=[
     ['Completed 5m price',price(x.observed_close)],
     ['Near session high',x.proximity_to_high_pct==null?'—':x.proximity_to_high_pct+'% below'],
     ['Matched-time RVOL',x.matched_volume?.ratio==null?'—':x.matched_volume.ratio+'×'],
     ['Watch score',x.research_score??'—']
   ].map(([heading,value])=>e('div',{key:heading},
       e('span',{className:'small muted'},heading+' '),e('strong',null,value)));
   const levels=x.entry==null?
     e('p',{className:'small muted'},'No qualified entry or risk levels yet.'):
     e('p',null,'Cash trigger ',price(x.entry),' · Stop ',price(x.sl),
         ' · T1 ',price(x.t1),' · T2 ',price(x.t2));
   const checks=Object.entries(x.checks||{}).map(([k,v])=>
      e('li',{key:k},(v?'PASS':'WAIT')+' — '+k.replaceAll('_',' ')));
   return e('article',{key:x.symbol+i,className:'btst-close-card'},
     e('div',{className:'signal-top'},
       e('h3',null,x.symbol),
       e(Badge,{type:x.entry==null?'warning':'positive'},x.phase||'WATCH')),
     e('p',{className:'small muted'},x.status||'RESEARCH ONLY'),
     e('div',{className:'btst-close-stats'},...cells),
     levels,
     e('p',{className:'small muted'},
       '20-day high ',price(x.previous_20day_high),
       ' · Prior-day high ',price(x.previous_day_high),
       ' · Futures OI ',x.futures_oi?.classification||'UNAVAILABLE',
       ' · Delivery ',x.delivery?.status||'UNAVAILABLE'),
     e('details',null,e('summary',null,'Passed / missing conditions'),
       e('ul',null,...checks),
       e('p',{className:'small muted'},
         'Missing: ',(x.blockers||[]).join(', ')||'None',
         ' · News/GIFT/US feeds: not verified')));
 });
 return e(React.Fragment,null,
   e(Section,{title:'NEW · BTST Closing Strength (14:30 / 15:05 / 15:20)'},
      e('p',{className:'small muted'},
        'Independent of strict BTST. Previous completed daily trend and same-clock historical volume. ',
        '15:05 is NOT the official auction/closing price.'),
      e('p',{className:'small muted'},
        'Status: ',view.status||'WAITING',
        ' · Phase: ',view.phase||'—',
        ' · Inspected: ',view.inspected??'—',
        ' · Confirmed: ',view.confirmed?.length??0,
        ' · Missing volume history: ',view.missing_matched_volume??'—'),
      error?e(Notice,{warning:true},error):null,
      e(Notice,{warning:true},
        'Research only. Any entry, stop, T1/T2 are CASH stock levels. ',
        'Overnight gaps, news and actual closing auction prices can differ; no orders.')),
   e(Section,{title:'Ranked pre-close research watchlist'},
     rows.length?e('div',{className:'btst-close-list'},...rows):
       e('div',{className:'empty'},'Awaiting 14:30 scan or verified cash candles.')));
}
function FIIStockDealsPanel(){
 const [data,setData]=useState({bought:[],sold:[],status:'WAITING FOR VERIFIED NSE DISCLOSURES'});
 const [error,setError]=useState('');
 const [requesting,setRequesting]=useState(false);
 useEffect(()=>{
   let alive=true;
   const load=()=>api('/api/v1/market-insights/fii-stock-deals')
     .then(value=>{if(alive){setData(value);setError('');}})
     .catch(err=>{if(alive)setError(err.message)});
   load();const id=setInterval(load,20000);
   return()=>{alive=false;clearInterval(id);};
 },[]);
 const refresh=async()=>{
   setRequesting(true);setError('');
   try{
     const result=await api('/api/v1/market-insights/fii-stock-deals/refresh',{method:'POST'});
     if(result.status!=='STARTED')setError(result.status||'Refresh unavailable');
   }catch(err){setError(err.message);}
   finally{setRequesting(false);}
 };
 const group=(heading,items,kind)=>
   e(Section,{title:heading},
     items.length?e('div',{className:'tablewrap'},
       e('table',{className:'research-table'},
          e('thead',null,e('tr',null,
            ...['Report date','Stock','Client','Shares','Reported price','Approx ₹ Cr','Type','Evidence']
             .map(x=>e('th',{key:x},x)))),
          e('tbody',null,...items.map((x,i)=>e('tr',{key:i},
            e('td',null,x.trade_date),
            e('td',null,e('strong',null,x.symbol)),
            e('td',null,x.client),
            e('td',null,(x.quantity||0).toLocaleString('en-IN')),
            e('td',null,price(x.price)),
            e('td',null,x.approx_value_crore??'—'),
            e('td',null,x.deal_type),
            e('td',null,
              e('a',{href:x.source_url,target:'_blank',rel:'noopener noreferrer'},'NSE report'),
              ' · ',
              e('a',{href:x.verification_source,target:'_blank',rel:'noopener noreferrer'},'FPI identity'))))))):
       e('p',{className:'empty'},'No attributable FII/FPI '+kind+' disclosure found in stored reports. This does NOT mean FIIs made no '+kind.toLowerCase()+' trades.'));
 return e('div',null,
   e(Section,{title:'NSE disclosed foreign institutional stock transactions'},
     e('p',{className:'small muted'},'Only verified FII/FPI-name bulk and block deal disclosures; NOT all daily foreign institutional stock buying or selling. Aggregate FII index derivatives OI cannot identify individual stocks.'),
     e('div',{className:'tile-grid'},
       e(Tile,{title:'VERIFIED FII BOUGHT',value:(data.bought||[]).length}),
       e(Tile,{title:'VERIFIED FII SOLD',value:(data.sold||[]).length}),
       e(Tile,{title:'LATEST REPORT',value:data.latest_report_date||'NOT AVAILABLE'}),
       e(Tile,{title:'UNVERIFIED CLIENT DEALS',value:data.unclassified_disclosed_rows??0,
          sub:'Not counted as FII'})),
     e('button',{type:'button',disabled:requesting,onClick:refresh},requesting?'Requesting…':'Refresh official NSE disclosures'),
     e('p',{className:'small muted'},'Source: NSE public bulk/block disclosures · Identity registry matches: ',data.verified_client_names??0,
        ' · Refresh: ',data.refresh?.status||'NOT STARTED'),
     error?e(Notice,{warning:true},error):null,
     e(Notice,{warning:true},'FII labels require documented identity confirmation. Unknown clients remain unclassified. Results are historical disclosures only, not complete institutional flow or trade recommendations.')),
   e('div',{className:'fii-deals-columns'},
      group('FII / FPI bought stocks',data.bought||[],'BUY'),
      group('FII / FPI sold stocks',data.sold||[],'SELL')),
   (data.unclassified_examples||[]).length?e(Section,{title:'Other disclosed transactions — FII identity NOT verified'},
     e('details',null,e('summary',null,'View up to 30 unclassified deals (not FII lists)'),
       e('div',{className:'fii-unknown-list'},
         ...(data.unclassified_examples||[]).map((x,i)=>
           e('p',{className:'small',key:i},x.trade_date,' · ',x.symbol,
             ' · ',x.client,' · ',x.side,' · ',x.deal_type))))):null,
   e('p',{className:'small muted'},data.note||'A registered FPI client identity must have an exact sourced match; configure verified_fpi_clients.json in the application data directory.'));
}
function ReadinessPanel(){
 const [state,setState]=useState(null);const [loading,setLoading]=useState(true);
 useEffect(()=>{let live=true;api('/api/v1/market-insights/readiness')
  .then(r=>{if(live)setState(r);}).catch(ex=>{if(live)setState({error:ex.message});})
  .finally(()=>{if(live)setLoading(false);});return()=>{live=false;};},[]);
 return e(Section,{title:'Scanner readiness — historical / diagnostic only'},
  loading?e('p',{className:'muted'},'Checking local scan configuration…'):
  state?.error?e(Notice,{warning:true},state.error):
  e('div',null,
   e('div',{className:'scan-diagnostics'},
    e('div',null,'Exchange session now: ',e('b',null,state.market_session_now?'OPEN':'CLOSED / HOLIDAY')),
    e('div',null,'Holiday calendar: ',e('b',null,state.calendar_configured?'Configured':'Missing')),
    e('div',null,'Dhan credentials: ',e('b',null,state.dhan_credentials_present?'Detected':'Missing')),
    e('div',null,'Cached index sectors: ',e('b',null,state.cached_index_count,' indices / ',state.cached_sector_count,' sectors')),
    e('div',null,'Sector mappings: ',e('b',null,state.mapped_sector_symbols)),
    e('div',null,'Orders: ',e('b',null,'DISABLED'))),
   e('p',{className:'small muted'},'This panel checks infrastructure only. Preliminary 09:45 rankings are not orders; 10:00 is the target shortlist lock; later checks reuse that shortlist.'),
   ...(state.warnings||[]).map((w,j)=>e('p',{className:'small muted',key:j},'• ',w)),
   e('p',{className:'small muted'},'For a read-only Dhan data, option-chain and futures OI test, run CHECK_SCANNER_READINESS.bat from your application folder.')));
}



function PremarketWatch({data={}}){
 const headers=['Symbol','Previous day %','Close','20-day close break','Daily volume ratio','Watch score','Why selected'];
 const group=(title,items)=>e(Section,{title},
  items.length?e('div',{className:'tablewrap'},e('table',{className:'research-table'},
    e('thead',null,e('tr',null,...headers.map(h=>e('th',{key:h},h)))),
    e('tbody',null,...items.map((x,i)=>{
      const v=[x.symbol,x.previous_day_change_pct+'%',price(x.close),
        x.closing_breakout?'UP BREAK':x.closing_breakdown?'DOWN BREAK':'NOT CONFIRMED',
        x.volume_ratio==null?'—':x.volume_ratio+'×',x.score,
        e('details',null,e('summary',null,'Rule evidence'),
           e('ul',null,...(x.reasons||[]).map((reason,j)=>e('li',{key:j},reason))))];
      return e('tr',{key:i},...v.map((value,j)=>e('td',{key:j},value)));
    })))):e('div',{className:'empty'},'No prior-session candidates verified.'));
 return e('div',null,
   e(Notice,{warning:true},'08:00 morning list uses the previous COMPLETED trading session. These are candidates, not CE/PE/stock buy or sell signals.'),
   e('div',{className:'tile-grid'},
      e(Tile,{title:'WATCHLIST STATE',value:data.status||'WAITING'}),
      e(Tile,{title:'DAILY DATA DATE',value:data.previous_session||'—'}),
      e(Tile,{title:'COVERAGE',value:data.assessed??'—',sub:'Sampled '+(data.universe??'—')+' of '+(data.available_instrument_master??'—')}),
      e(Tile,{title:'DATA ERRORS',value:(data.unavailable_count??0)+(data.insufficient_history??0)})),
   data.mixed_data_dates?e(Notice,{warning:true},'Multiple data session dates found; freshness needs checking.'):null,
   e('div',{className:'analyse-selection-grid'},
       group('Top previous-day gainers',data.gainers||[]),
       group('Top previous-day losers',data.losers||[])),
   e('p',{className:'small muted'},data.note||'Starts at 8:00 AM on an eligible session when app is running and broker history is accessible.'));
}
function OpeningOptionSetups({items=[]}){
 const [index,setIndex]=useState(0);
 const selected=items[Math.min(index,Math.max(0,items.length-1))]||null;
 const names=['Underlying','Strategy','State','Side','CE trigger','PE trigger','Spot entry','Spot SL','Spot T1','Spot T2','Option status'];
 const rows=items.map((x,i)=>{
   const values=[x.underlying,x.strategy,x.state,x.side||'—',
     x.trigger_ce??'—',x.trigger_pe??'—',x.spot_entry??'—',x.spot_sl??'—',
     x.spot_t1??'—',x.spot_t2??'—',x.trade_status||'UNVERIFIED'];
   return e('tr',{key:i},...values.map((v,j)=>e('td',{key:j},v)));
 });
 const table=e('table',{className:'research-table'},
     e('thead',null,e('tr',null,...names.map(n=>e('th',{key:n},n)))),
     e('tbody',null,...rows));
 const chooser=e('select',{value:Math.min(index,Math.max(0,items.length-1)),
      onChange:event=>setIndex(Number(event.target.value))},
      ...items.map((x,i)=>e('option',{key:i,value:i},
         (x.underlying||'Spot')+' · '+x.strategy)));
 return e(React.Fragment,null,
   e(Section,{title:'NEW · First 5m opening range + first red bar Fib'},
     e('p',{className:'small muted'},'First 5m: 0=09:15 low, 1=09:15 high; above 1 CE, below 0 PE. Red bar: exclude 09:15 candle, use first later RED bar, Fib 0=HIGH and 1=LOW; above upper 0.44 CE, below lower 0.56 PE. Two completed 5m closes outside levels required. NO TRADE inside range/band.'),
     items.length?e('div',{className:'tablewrap'},table):
       e('div',{className:'empty'},'Awaiting verified 5-minute spot candles.')),
   selected?e(Section,{title:'5m underlying chart · select instrument and strategy'},
     chooser,
     e('p',{className:'small muted'},'Reference: ',selected.reference_at||'—',
       ' · ',selected.orientation||'—',' · ',selected.reason||'—'),
     e('p',{className:'small muted'},'OI: ',selected.oi?.status||'UNAVAILABLE',
       ' · option contract: ',selected.option_contract?
         selected.option_contract.strike+' '+selected.option_contract.side:'NOT VERIFIED',
       ' · quote freshness: NOT VERIFIED'),
     e(PriceChart,{candles:selected.spot_candles||[],fib:selected.fib||null})
   ):null);
}
function FibOptionSetups({items=[]}){
 const [active,setActive]=useState(0);
 const selected=items[Math.max(0,Math.min(active,items.length-1))]||null;
 const heads=['Spot symbol','Strategy','State','Side','0','0.44','0.50','1','Spot entry','Spot stop','Spot target','OI'];
 const rows=items.map((x,i)=>{
   const fib=x.fib||{};
   const values=[x.underlying,x.strategy,x.trade_status||x.state||'WAITING',
      x.side||'—',fib['0']??'—',fib['0.44']??'—',fib['0.5']??'—',fib['1']??'—',
      x.spot_entry??'—',x.spot_sl??'—',x.spot_t1??'—',
      (x.oi?.status||'UNAVAILABLE')+' / '+(x.futures_oi?.status||'UNAVAILABLE')];
   return e('tr',{key:i},...values.map((v,j)=>e('td',{key:j},v)));
 });
 const table=e('table',{className:'research-table'},
   e('thead',null,e('tr',null,...heads.map(k=>e('th',{key:k},k)))),
   e('tbody',null,...rows));
 const explanations=items.map((x,i)=>e('details',{className:'fib-evidence',key:i},
   e('summary',null,(x.underlying||'Underlying')+' · '+x.strategy+' · '+(x.state||'WAITING')),
   e('p',{className:'small muted'},x.reason||'No verified opportunity'),
   e('p',{className:'small muted'},'No-trade zone: ',x.no_trade_zone||'—',
       ' · Reference: ',x.reference?.interval||'—',' · Candle: ',x.reference?.color||'—'),
   e('p',{className:'small muted'},'SMC: ',x.smc?.reason||'Not confirmed'),
   e('p',{className:'small muted'},'Gann support/resistance: ',
      x.gann_wave?.gann?.support??'—',' / ',x.gann_wave?.gann?.resistance??'—',
      ' · wave ',x.gann_wave?.wave?.structure||'UNAVAILABLE'),
   e('p',{className:'small muted'},'Chain OI: ',x.oi?.reason||'Not verified',
       ' · Futures: ',x.futures_oi?.reason||'Not verified'),
   e('p',{className:'small muted'},'Option premium: ',x.premium_status||'UNVERIFIED')));
 return e(React.Fragment,null,
  e(Section,{title:'Additional 09:45 and 12:45 Fib + SMC + OI research'},
    e('p',{className:'small muted'},'Fib levels and entry/stop/targets refer to the spot or cash underlying, NOT option premiums. Requires completed reference candles and 5m confirmations. Missing or contradictory OI blocks verified status.'),
    items.length?e('div',{className:'tablewrap'},table):
      e('div',{className:'empty'},'No Fib reference setups or watch states yet.')),
  selected?e(Section,{title:'Spot / cash 5-minute candlesticks with Fib 0, 0.44, 0.5, 1'},
    e('label',{className:'small muted'},'Reference study: ',
      e('select',{value:Math.max(0,Math.min(active,items.length-1)),
          onChange:ev=>setActive(Number(ev.target.value))},
         ...items.map((x,i)=>e('option',{value:i,key:i},(x.underlying||'Spot')+' · '+x.strategy)))),
    e('p',{className:'small muted'},'Fib lines are drawn on the underlying SPOT/CASH 5m chart; these are not option premium entry or stop prices.'),
    e(PriceChart,{candles:selected.spot_candles||[],fib:selected.fib||null})
   ):null,
  items.length?e(Section,{title:'Fib / SMC evidence and no-trade explanations'},...explanations):null);
}
function IntradayTopTen({items=[]}){
 const headers=['#','Symbol','Side','Rank','Entry trigger','Stop','T1','T2','Stop %','Daily RVOL','15m RVOL'];
 const rows=items.map((x,i)=>{
  const vals=[i+1,x.symbol,x.direction,x.ai_score??'—',price(x.entry),price(x.sl),price(x.t1),price(x.t2),
     x.stop_distance_pct!=null?x.stop_distance_pct+'%':'—',
     x.daily_volume_ratio!=null?x.daily_volume_ratio+'×':'—',
     x.volume_ratio15!=null?x.volume_ratio15+'×':'—'];
  return e('tr',{key:x.symbol+x.direction+i},...vals.map((v,j)=>e('td',{key:j},v)));
 });
 return e(Section,{title:'AI-ready top 10 momentum setups · BUY and SELL'},
  e('p',{className:'small muted'},'Transparent evidence ranking, not a trained ML prediction or win probability. All 11 daily/15m rules and ATR/structure risk checks must pass. Entry is a conditional future trigger; no fill or perfect stop is implied.'),
  items.length?e('div',{className:'tablewrap'},
   e('table',{className:'research-table'},
      e('thead',null,e('tr',null,...headers.map(x=>e('th',{key:x},x)))),
      e('tbody',null,...rows)
   )):e('div',{className:'empty'},'No qualified candidates yet. We never force ten picks.'));
}
function IntradaySignals({data}){
 const [direction,setDirection]=useState('BUY');
 const isBuy=direction==='BUY';
 const signals=isBuy?(data.buy_signals||[]):(data.sell_signals||[]);
 const preview=isBuy?(data.preview_buy||[]):(data.preview_sell||[]);
 return e(React.Fragment,null,
   e(IntradayTopTen,{items:data.ai_top10||[]}),
   e('div',{className:'direction-tabs','role':'tablist','aria-label':'Intraday direction'},
    e('button',{type:'button',role:'tab','aria-selected':isBuy,
      className:'direction-tab '+(isBuy?'is-active buy':''),
      onClick:()=>setDirection('BUY')},
      '↗ Breakout + huge volume — BUY'),
    e('button',{type:'button',role:'tab','aria-selected':!isBuy,
      className:'direction-tab '+(!isBuy?'is-active sell':''),
      onClick:()=>setDirection('SELL')},
      '↘ Breakdown + huge volume — SELL')),
   e(Section,{title:isBuy?'Buy-side breakout candidates':'Sell-side breakdown candidates'},
    e('p',{className:'small muted'},isBuy?
       'Daily bullish momentum: all 8 conditions and 15m EMA20/RSI>60/volume >2× average. Provisional daily candle.':
       'Daily bearish momentum: all 8 conditions and 15m EMA20/RSI<40/volume >2× average. Provisional daily candle.'),
    e(Signals,{items:signals,empty:!data.shortlist_finalized?
      'Awaiting 09:45 preliminary and 10:00 finalized watchlist. Early rankings are NOT executable trades.':
      'No qualifying '+(isBuy?'breakout BUY':'breakdown SELL')+' signals on the locked shortlist.'})),
   data.shortlist_finalized?e(Section,{title:'10:00 locked shortlist — monitored without broad rescans'},
       (data.shortlist_symbols||[]).length?
       e('div',{className:'shortlist-chips'},(data.shortlist_symbols||[]).map((name,i)=>
         e('span',{key:i,className:'shortlist-chip'},name))):
       e('p',{className:'small muted'},'No eligible stocks were shortlisted. This is not a trade signal.')):null,
   preview.length?e(Section,{title:isBuy?'Early BUY watchlist — NOT signals':'Early SELL watchlist — NOT signals'},
     e('div',{className:'tablewrap'},e('table',null,
       e('thead',null,e('tr',null,...['Symbol','Rank score','RVOL','Data as of','Status'].map(k=>e('th',{key:k},k)))),
       e('tbody',null,preview.map((x,i)=>e('tr',{key:i},
          e('td',null,x.symbol),e('td',null,x.ranking_score),e('td',null,x.rvol),
          e('td',null,x.data_asof),e('td',null,x.status))))))):null);
}

function SwingOpportunityFinder({data}){
 const [showWatch,setShowWatch]=useState(true);
 const ready=data.opportunity_ready||[];
 const watch=data.opportunity_watch||[];
 function cards(rows,style){
  return rows.map((x,i)=>{
   const gw=x.swing_gann_wave||{};
   const checks=Object.entries(x.checks||{}).map(([k,v])=>
     e('li',{key:k},(v?'PASS':'WAIT')+' · '+k.replaceAll('_',' ')));
   const levels=x.entry==null?
     e('p',{className:'small muted'},'No conditional trade levels until all rules confirm.'):
     e('p',null,'NEXT-SESSION TRIGGER ',price(x.entry),
       ' · SL ',price(x.stop),' · T1 2R ',price(x.target),
       ' · T2 3R ',price(x.target_3r));
   return e('article',{className:'swing-opportunity',key:x.symbol+i},
     e('div',{className:'research-candidate-header'},
       e('strong',null,x.symbol),
       e(Badge,{type:style},x.readiness||'WATCH'),
       e('strong',null,'Score ',x.score??'—',' /100')),
     e('p',null,'Setup: ',x.setup,
       ' · Daily trend: ',x.daily_trend,
       ' · Weekly trend: ',x.weekly_trend),
     e('p',{className:'small muted'},'Daily close ',price(x.close),
       ' · Prior 20d high ',price(x.breakout_level),
       ' · Relative volume ',x.volume_ratio??'—','×',
       ' · RSI14 ',x.rsi14??'—'),
     levels,
     e('p',{className:'small muted'},'EMA21 ',price(x.ema21),
       ' · EMA50 ',price(x.ema50),' · EMA200 ',price(x.ema200),
       ' · Avg traded value ₹',x.avg_traded_value_lakh??'—',' lakh'),
     e('p',{className:'small muted'},
       'Gann: ',gw.gann?.support??'—',' / ',gw.gann?.resistance??'—',
       ' · Daily/weekly swing: ',gw.wave?.daily_structure||'—',' / ',
          gw.wave?.weekly_structure||'—'),
     e('p',{className:'small muted'},x.fii_evidence_scope||'No verified FII transaction evidence'),
     e('details',null,
       e('summary',null,'Screening conditions and blockers'),
       e('ul',null,...checks),
       e('p',{className:'small muted'},'Not met: ',
         (x.blockers||[]).join(' · ')||'None')));
  });
 }
 return e('div',null,
   e(Section,{title:'NEW · Swing Opportunity Finder (daily + weekly)'},
     e('p',{className:'small muted'},
       'Independent 20-day closing breakouts and EMA21 pullback recovery watches, from completed daily and weekly candles.'),
     e('div',{className:'tile-grid'},
       e(Tile,{title:'READY',value:ready.length}),
       e(Tile,{title:'DEVELOPING WATCH',value:watch.length}),
       e(Tile,{title:'OPPORTUNITIES',value:data.opportunity_count??'—'}),
       e(Tile,{title:'UNIVERSE',value:data.universe??'—',sub:'Mapped '+(data.available_instrument_master??'—')})),
     e(Notice,{warning:true},
       'Research only: no win probability. Triggers are not fills; overnight gaps and circuit risk may bypass stops.'),
     e('label',null,
       e('input',{type:'checkbox',checked:showWatch,
         onChange:event=>setShowWatch(event.target.checked)}),
       ' Show developing watchlist')),
   e(Section,{title:'Conditional READY setups · 2R and 3R'},
     ready.length?e('div',{className:'swing-opportunities'},...cards(ready,'positive')):
       e('div',{className:'empty'},'No completed breakout or pullback currently meets all rule and risk guards.')),
   showWatch?e(Section,{title:'Developing swing watches · no entry levels'},
     watch.length?e('div',{className:'swing-opportunities'},...cards(watch,'warning')):
       e('div',{className:'empty'},'No developing watch candidates in the sampled universe.')):null
 );
}
function SwingGuideLayer({data}){
 const rows=data.guide_layer||[];
 const table=e('table',{className:'research-table'},
   e('thead',null,e('tr',null,
      ...['Stock','PDF setups','Status','NIFTY RS','RS rank','Conditional entry',
         '2×ATR stop','2R target','Vol ratio','Why / exit']
       .map(v=>e('th',{key:v},v)))),
   e('tbody',null,...rows.map((x,i)=>e('tr',{key:x.symbol+i},
      e('td',null,e('strong',null,x.symbol)),
      e('td',null,(x.matched_setups||[]).join(' · ')),
      e('td',null,x.readiness||'WATCH'),
      e('td',null,x.rs_score==null?'UNAVAILABLE':x.rs_score+'%'),
      e('td',null,x.rs_rank_percentile==null?'—':x.rs_rank_percentile+'th percentile'),
      e('td',null,price(x.entry)),
      e('td',null,price(x.stop)),
      e('td',null,price(x.target_2r)),
      e('td',null,x.volume_ratio==null?'—':x.volume_ratio+'×'),
      e('td',null,e('details',null,e('summary',null,'Review evidence'),
        e('p',{className:'small muted'},'Daily data ',x.asof,
          ' · ',x.freshness,' · Turnover ₹',x.average_turnover_cr??'—',' Cr'),
        e('p',{className:'small muted'},'Blockers: ',(x.blockers||[]).join(' · ')||'None'),
        e('p',{className:'small muted'},x.note),
        e('ul',null,...Object.entries(x.exit_rules||{}).map(([k,v])=>
          e('li',{key:k},k+': '+v)))))))));
 return e(Section,{title:'NEW · Swing Trading Guide — four setups + NIFTY relative strength'},
   e('p',{className:'small muted'},'20 EMA pullback · tight-base 20-day breakout · RSI(2) oversold dip · Bollinger volatility squeeze. ',
      'NIFTY-relative 63/126-session returns rank the mapped Dhan sample. Completed daily bars only.'),
   e('p',{className:'small muted'},'Detected ',data.guide_layer_count??0,
      ' · Conditional research ',data.guide_layer_conditional??0,
      ' · Benchmark ',data.guide_benchmark_status||'NOT LOADED',
      ' · ',data.guide_rs_universe||'Sampled mapped symbols only'),
   e(Notice,{warning:true},
     'Conditional BUY-stop levels are next-session research triggers, not fills. ',
     'Earnings/events, ASM/GSM and gaps may invalidate trades. Position sizing and win probability require user risk settings and backtesting.'),
   rows.length?e('div',{className:'tablewrap'},table):
     e('p',{className:'empty'},'No completed-candle PDF strategy matches in the current sampled universe.'));
}
function SwingTrades({data}) {
 const rows=data.signals||[];
 const cols=['Symbol','Strategy','Entry','Stop','Target 2R','Target 3R','Risk:Reward','Volume ratio','Trend strength','Gann support','Gann resistance','D/W Wave','Time cycle'];
 const tbody=e('tbody',null,...rows.map((x,i)=>{
   const gw=x.swing_gann_wave||{},wave=gw.wave||{},cycles=gw.time_cycle||{};
   const values=[x.symbol,x.strategy,price(x.entry),price(x.stop),
     price(x.target),price(x.target_3r),x.risk_reward??'—',
     x.volume_ratio==null?'—':x.volume_ratio+'×',x.trend_strength??'—',
     gw.gann?.support??'—',gw.gann?.resistance??'—',
     (wave.daily_structure||'—')+' / '+(wave.weekly_structure||'—'),
     'D '+((cycles.near_daily_sessions||[]).join(',')||'—')+
       ' · W '+((cycles.near_weekly_bars||[]).join(',')||'—')];
   return e('tr',{key:i},...values.map((v,j)=>e('td',{key:j},v)));
 }));
 const table=e('table',{className:'research-table'},e('thead',null,e('tr',null,...cols.map(k=>e('th',{key:k},k)))),tbody);
 return e('div',null,
  e(SwingOpportunityFinder,{data}),
  e(SwingGuideLayer,{data}),
  e('p',{className:'small muted'},'Completed daily and weekly candles only. Gann price levels, pivot-based trading-day/week cycles and confirmed swing geometry are additional research evidence, not trade filters, win probabilities or predictive Elliott counts. Original 2R/3R levels are unchanged.'),
  e('p',{className:'small muted'},'Status: ',data.status||'Waiting',' · Updated: ',data.updated_at||'—',' · Universe: ',data.universe??'—',
   ' / ',data.available_instrument_master??'—',' available cash stocks'),
  e(Section,{title:'Swing setups · ranked by Risk:Reward and trend strength'},
    rows.length?e('div',{className:'tablewrap'},table):e('div',{className:'empty'},'No qualified swing setup from completed daily candles.')));
}
function MultibaggerResearch({data}) {
 const [minCap,setMinCap]=useState(300);
 const [maxCap,setMaxCap]=useState(20000);
 const [showUnverified,setShowUnverified]=useState(true);
 const scored=(data.candidates||[]).map(x=>{
   const capStatus=x.market_cap_cr==null?'UNVERIFIED':x.market_cap_cr>=minCap&&x.market_cap_cr<=maxCap?'PASS':'FAIL';
   return {...x,capStatus,eligible:!!x.eligible&&capStatus==='PASS'};
 });
 const rows=scored.filter(x=>showUnverified||x.eligible);
 const criterion=x=>e('div',{className:'criterion',key:x.id},
   e('span',null,x.label,' · ',x.source||'Unverified source'),
   e('span',{className:'small muted'},x.status,' · ',x.points??0,' point'));
 const cards=rows.map((x,i)=>{
   const details=e('details',null,
     e('summary',null,'Show score breakdown and eligibility checks'),
     e('h4',null,'Scored technical and fundamental criteria'),
     ...(x.criteria||[]).map(criterion),
     e('h4',null,'Mandatory eligibility guards'),
     ...(x.guards||[]).map(criterion),
     e('p',null,'Market-cap range: ',x.capStatus));
   return e('article',{className:'research-candidate',key:x.symbol+i},
     e('div',{className:'research-candidate-header'},
       e('strong',null,x.symbol),e('strong',null,x.score,' / ',x.score_max,' points'),
       e(Badge,{type:x.eligible?'positive':'warning'},x.eligible?'ELIGIBLE':x.eligibility_status==='BLOCKED'||x.capStatus==='FAIL'?'BLOCKED':'UNVERIFIED')),
     e('p',{className:'small muted'},'Close: ',price(x.last_close),
       ' · Market cap: ',x.market_cap_cr==null?'UNVERIFIED':'₹'+x.market_cap_cr.toLocaleString('en-IN')+' cr',
       ' · Avg traded value: ',x.avg_daily_traded_value_lakh==null?'UNVERIFIED':'₹'+x.avg_daily_traded_value_lakh+' lakh',
       ' · As of: ',x.asof),
     details);
 });
 return e('div',null,
   e(Notice,{warning:true},'Long-term research only. Market cap, fundamentals, ASM/GSM and circuit flags must be sourced and dated; missing information blocks eligibility.'),
   e(Section,{title:'Market capitalization filter · ₹ crore'},
     e('div',{className:'cap-controls'},
       e('label',null,'Minimum: ',minCap.toLocaleString('en-IN'),
         e('input',{type:'range',min:0,max:50000,step:100,value:minCap,onChange:v=>setMinCap(Math.min(Number(v.target.value),maxCap))})),
       e('label',null,'Maximum: ',maxCap.toLocaleString('en-IN'),
         e('input',{type:'range',min:0,max:50000,step:100,value:maxCap,onChange:v=>setMaxCap(Math.max(Number(v.target.value),minCap))}))),
     e('label',null,e('input',{type:'checkbox',checked:showUnverified,onChange:v=>setShowUnverified(v.target.checked)}),
       ' Include blocked/unverified candidates for review')),
   e('p',{className:'small muted'},'Status: ',data.status||'Waiting',' · Reviewed: ',scored.length,
     ' · Fully eligible at selected cap: ',scored.filter(x=>x.eligible).length,
     ' · Sampled: ',data.universe??'—',' / ',data.available_instrument_master??'—',
     ' · Updated: ',data.updated_at||'—'),
   e(Section,{title:'Multibagger score breakdown'},
     cards.length?e('div',{className:'research-candidates'},...cards):e('div',{className:'empty'},'No candidates to show yet.')));
}
function App(){
 const [active,setActive]=useState('Dashboard');const [theme,setTheme]=useState(localStorage.getItem('bharat-theme')||'dark');
 const [health,setHealth]=useState({status:'Connecting…',read_only:true});const [data,setData]=useState({});const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 const [refreshBusy,setRefreshBusy]=useState(false);const [refreshError,setRefreshError]=useState('');
 useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('bharat-theme',theme);},[theme]);
 useEffect(()=>{let alive=true;const load=async()=>{try{const h=await api('/api/v1/health');if(alive)setHealth(h);}catch{if(alive)setHealth({status:'OFFLINE',read_only:true});}};load();const id=setInterval(load,15000);return()=>{alive=false;clearInterval(id);};},[]);
 useEffect(()=>{if(active==='Analyse')return;let alive=true;const load=async()=>{try{const d=await api('/api/v1/market-insights/'+route[active]);if(alive){setData(d);setError('');}}catch(ex){if(alive)setError(ex.message);}};load();const id=setInterval(load,20000);return()=>{alive=false;clearInterval(id);};},[active]);
 const onRefresh=async()=>{
  if(refreshBusy)return;
  setRefreshBusy(true);setRefreshError('');
  try {
   const result=await api('/api/v1/market-insights/dashboard/refresh',{method:'POST'});
   if(result.status!=='STARTED')throw Error(result.error||'Unable to start refresh');
  } catch(ex) {
   setRefreshError(ex.message||'Dhan refresh failed');setRefreshBusy(false);
  }
 };
 useEffect(()=>{
  if(!refreshBusy)return;
  let alive=true;
  const poll=async()=>{
   try {
    const h=await api('/api/v1/health');
    if(!alive)return;
    setHealth(h);
    const state=h.manual_refresh||{};
    if(state.status==='RUNNING'||state.status==='IDLE')return;
    setRefreshBusy(false);
    if(state.status!=='SUCCEEDED')setRefreshError(state.message||state.status||'Refresh failed');
    const d=await api('/api/v1/market-insights/dashboard');
    if(alive&&active==='Dashboard')setData(d);
   } catch(ex){if(alive){setRefreshBusy(false);setRefreshError(ex.message);}}
  };
  poll();const id=setInterval(poll,2500);
  return()=>{alive=false;clearInterval(id);};
 },[refreshBusy,active]);
 const onSearch=async(symbol,expiry)=>{setBusy(true);setError('');try{setData(await api('/api/v1/market-insights/analyse?symbol='+encodeURIComponent(symbol.trim())+(expiry?'&expiry='+encodeURIComponent(expiry):'')));}catch(ex){setData({});setError(ex.message);}finally{setBusy(false);}};
 const select=label=>{setActive(label);setError('');setData({});};
 return e('div',{className:'shell'},
  e('aside',{className:'sidebar'},e('div',{className:'brand'},e('div',{className:'brand-icon'},'B'),e('div',null,e('strong',null,'BHARATSIGNAL'),e('small',null,'FUSION · PRO'))),
   e('div',{className:'nav-caption'},'WORKSPACE'),e('div',{className:'nav-caption subtle'},'MARKET INSIGHTS'),
   e('nav',null,tabs.map(([label,ic])=>e('button',{className:'nav-item '+(active===label?'selected':''),key:label,onClick:()=>select(label)},e('span',{className:'nav-icon'},ic),label))),
   e('div',{className:'sidebar-bottom'},e('span',{className:'dot '+(health.status==='CONNECTED'?'green':'amber')}),e('span',null,health.status||'Waiting'),e('p',null,'Local only · Read-only'))),
  e('div',{className:'workspace'},
   e('header',{className:'topbar'},e('div',null,e('small',{className:'muted'},'BHARATSIGNAL / MARKET INSIGHTS'),e('h1',null,active)),
    e('div',{className:'top-actions'},e(Badge,{type:'positive'},'NO ORDER PLACEMENT'),e(Badge,null,'DHAN · '+health.status),e('button',{className:'theme-btn',onClick:()=>setTheme(theme==='dark'?'light':'dark')},theme==='dark'?'☀ Light':'☾ Dark'))),
   e('main',{className:'content'},e(Notice,{warning:true},RISK),
    error?e(Notice,{warning:true},error):null,
    active==='Dashboard'?e(Dashboard,{data,onRefresh,refreshBusy,refreshState:health.manual_refresh,refreshError}):null,
    active==='Analyse'?e(Analyse,{data,onSearch,busy}):null,
    active==='Pre-Market 8 AM'?e(PremarketWatch,{data}):null,
    active==='FII Stock Deals'?e(FIIStockDealsPanel):null,
    active==='Swing Trades'?e(SwingTrades,{data}):null,
    active==='Multibagger'?e(MultibaggerResearch,{data}):null,
    ['Intraday','BTST','Index Options','F&O Stocks'].includes(active)?e(React.Fragment,null,
     e(ReadinessPanel),
     active==='BTST'?e(BTSTClosingStrength):null,
     e('div',{className:'tile-grid'},e(Tile,{title:'MODULE',value:active,sub:active==='Intraday'?'09:45 Preview · 10:00 Final · 5m Follow-up':active==='BTST'?'Scheduled 15:00 IST':'Opening 09:30 · every 5m · research'}),
       e(Tile,{title:['Index Options','F&O Stocks'].includes(active)?'SPOT WATCHES + LEGACY':'CANDIDATES',
           value:(data.signals||[]).length+(['Index Options','F&O Stocks'].includes(active)?(data.opening_ready||0):0),
           sub:active==='Intraday'?`BUY ${data.qualified_buy||0} · SELL ${data.qualified_sell||0}`:
             ['Index Options','F&O Stocks'].includes(active)?`Directional watches ${data.opening_ready||0} · Legacy option scenarios ${(data.signals||[]).length}`:''}),e(Tile,{title:'STATUS',value:data.status||'Waiting'}),e(Tile,{title:'LAST SCAN',value:data.updated_at||'Not yet run'})),
     data.scanned!=null?e('p',{className:'small muted'},
       'Deep universe: ',data.universe_scanned_at_discovery??data.scanned,' · Broad quote coverage: ',data.breadth_quotes??'—',
       ' · Discovery method: ',data.discovery_mode??'—',' · Locked shortlist: ',data.shortlisted??data.shortlist_size??'—',
       ' · Eligible candle sets: ',data.data_assessed??'—',
       ' · Sector missing/stale: ',data.missing_sector??'—',
       ' · Market data unavailable: ',data.unavailable_count??'—',
       ' · Candles too old: ',data.stale_data??'—',
       ' · Discovery candles assessed: ',data.discovery_data_assessed??'—',
       ' · Discovery missing bars: ',data.discovery_stale??'—',
       ' · Discovery invalid structure: ',data.discovery_missing_structure??'—',
       ' · Discovery errors: ',data.discovery_errors??'—',
       ' · Rules not met: ',data.rules_not_met??'—'):null,
     data.note?e(Notice,{warning:true},data.note):null,
     ['Index Options','F&O Stocks'].includes(active)?e(Notice,{warning:true},
       'Option premiums are hypothetical until quote timestamps, expiry and historical performance are independently verified. No trades are placed or recorded as executed.'):null,
     active==='Intraday'?e(IntradaySignals,{data}):
     e(React.Fragment,null,
       ['Index Options','F&O Stocks'].includes(active)?e(React.Fragment,null,
       e(OpeningOptionSetups,{items:data.opening_setups||[]}),
       e(FibOptionSetups,{items:data.fib_setups||[]})):null,
       e(Section,{title:'Existing rule-based research candidates'},
          e(Signals,{items:data.signals||[],empty:data.status||'No qualifying signals. Missing inputs are never filled with invented values.'})))) :null,
    active==='Track Record'?e(TrackRecord,{data}):null,
    e('div',{className:'footer'},'Powered by local Python Flask API · Dhan-sourced analytics only · No broker orders · Data and backtests may be incomplete'))));
}

createRoot(document.getElementById('root')).render(e(App));
