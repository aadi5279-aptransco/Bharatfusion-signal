import React, {useEffect,useMemo,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {createChart, CandlestickSeries, HistogramSeries} from 'lightweight-charts';
import './styles.css';
const e=React.createElement;
const RISK='Rule-based analytics, not investment advice. Entries and targets are not guaranteed. Trading carries risk of loss. No orders are placed.';
const tabs=[['Dashboard','▦'],['Analyse','⌕'],['Intraday','↗'],['BTST','◷'],['Index Options','⌁'],['F&O Stocks','≋'],['Swing Trades','↝'],['Multibagger','✦'],['Track Record','▤']];
const route={'Dashboard':'dashboard','Analyse':'analyse','Intraday':'intraday','BTST':'btst','Index Options':'index-options','F&O Stocks':'fo-stocks','Swing Trades':'swing-trades','Multibagger':'multibagger','Track Record':'track-record'};
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
  if(fib)for(const level of ['0','0.44','0.5','1']){
    const v=Number(fib[level]);
    if(!Number.isFinite(v)||v<=0)continue;
    series.createPriceLine({price:v,color:level==='0.44'?'#eeb95f':level==='0.5'?'#77adfa':level==='1'?'#62dbb8':'#ff8b9b',
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
  e('div',{className:'split'},
   e(Section,{title:'Index bias & underlying rules'},indices.length?indices.map((x,i)=>e('div',{className:'bias',key:i},
    e('div',{className:'bias-head'},e('b',null,x.symbol),e(Badge,{type:x.bias==='Uptrend'?'positive':x.bias==='Downtrend'?'negative':''},x.bias),e(Text,{muted:true},`Score ${x.score??'N/A'}`)),
    e('ul',{className:'reasons'},...(x.reasons||[]).map((r,k)=>e('li',{key:k},r))),
    (x.warnings||[]).length?e('p',{className:'small muted'},x.warnings.join(' · ')):null)):e('p',{className:'muted'},'Connect Dhan and provide current completed index candles to calculate bias.')),
   e(Section,{title:'Sector momentum heatmap'},sectors.length?e('div',{className:'heatmap'},sectors.map((s,i)=>e('div',{className:'heat',key:i,style:{background:s.session_change>=0?'var(--heat-green)':'var(--heat-red)'}},e('b',null,s.sector),e('strong',null,`${s.session_change>0?'+':''}${s.session_change}%`),e('small',null,`vs NIFTY ${s.relative_strength??'—'}%`)))):e('div',{className:'empty'},'Sector data unavailable. Rankings will appear only when Dhan provides verified sector candles.'))));
}
function Analyse({data,onSearch,busy}){
 const [symbol,setSymbol]=useState('NIFTY');const [expiry,setExpiry]=useState('');
 const m=data.metrics;
 return e(React.Fragment,null,e('form',{className:'searchbox',onSubmit:ev=>{ev.preventDefault();onSearch(symbol,expiry);}},
   e('input',{value:symbol,onChange:ev=>setSymbol(ev.target.value.toUpperCase()),placeholder:'NIFTY, SENSEX, BANKNIFTY or stock symbol',maxLength:64,'aria-label':'Instrument symbol'}),
   e('input',{value:expiry,onChange:ev=>setExpiry(ev.target.value),placeholder:'Expiry YYYY-MM-DD (optional)','aria-label':'Expiry date'}),
   e('button',{type:'submit',disabled:busy},busy?'Analysing…':'Analyse option chain')),
  data.error?e(Notice,{warning:true},data.error):null,
  m?e(React.Fragment,null,
    e('div',{className:'tile-grid'},e(Tile,{title:'OPEN-INTEREST PCR',value:m.pcr}),e(Tile,{title:'MAX PAIN',value:m.max_pain}),e(Tile,{title:'OI SUPPORT',value:m.oi_support}),e(Tile,{title:'OI RESISTANCE',value:m.oi_resistance})),
    e(Section,{title:'Multi-timeframe trend and flow proxies'},
      e('p',{className:'small muted'},'5m trend: ',data.mtf?.['5m']||'UNAVAILABLE',
        ' · 15m trend: ',data.mtf?.['15m']||'UNAVAILABLE',
        ' · 60m trend: ',data.mtf?.['60m']||'UNAVAILABLE'),
      e('p',{className:'small muted'},'Last price candle: ',data.price_asof||'Unknown',
        ' · Dhan depth: ',data.market_depth?.status||'UNAVAILABLE',
        data.market_depth?.bid_ask_ratio!=null?' · Resting bid/ask ratio '+data.market_depth.bid_ask_ratio:''),
      e('p',{className:'small muted'},'OI changes and order-book quantities are positioning/liquidity proxies, not evidence of executed order flow.')),
    e(Section,{title:`Completed 5-minute price candles · ${data.symbol}`},e(PriceChart,{candles:data.candles||[]})),
    e('div',{className:'split'},e(Section,{title:`Option-chain OI · ${data.symbol} · ${data.expiry}`},e(OiChart,{strikes:m.strikes})),
     e(Section,{title:'OI interpretation'},e('p',null,`Rule-based tilt: ${data.bias||'Undetermined'}`),e('p',{className:'muted'},data.note),e('p',null,`Call OI Δ: ${m.call_change?.toLocaleString('en-IN')} · Put OI Δ: ${m.put_change?.toLocaleString('en-IN')}`),e(Notice,{warning:true},m.iv_percentile_note),e(Signals,{items:data.plan?[data.plan]:[],empty:'No validated entry/target/stop plan for this option chain.'}))))
   :e(Notice,null,'Search a mapped Dhan instrument. Option-chain metrics are retrieved only on request; no NSE website scraping.'));
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

function SwingTrades({data}) {
 const rows=data.signals||[];
 const cols=['Symbol','Strategy','Entry','Stop','Target 2R','Target 3R','Risk:Reward','Volume ratio','Trend strength'];
 const tbody=e('tbody',null,...rows.map((x,i)=>{
   const values=[x.symbol,x.strategy,price(x.entry),price(x.stop),price(x.target),price(x.target_3r),x.risk_reward??'—',x.volume_ratio==null?'—':x.volume_ratio+'×',x.trend_strength??'—'];
   return e('tr',{key:i},...values.map((v,j)=>e('td',{key:j},v)));
 }));
 const table=e('table',{className:'research-table'},e('thead',null,e('tr',null,...cols.map(k=>e('th',{key:k},k)))),tbody);
 return e('div',null,
  e('p',{className:'small muted'},'Daily completed candles only. Entries/targets are research reference levels, not live orders.'),
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
    active==='Swing Trades'?e(SwingTrades,{data}):null,
    active==='Multibagger'?e(MultibaggerResearch,{data}):null,
    ['Intraday','BTST','Index Options','F&O Stocks'].includes(active)?e(React.Fragment,null,
     e(ReadinessPanel),
     e('div',{className:'tile-grid'},e(Tile,{title:'MODULE',value:active,sub:active==='Intraday'?'09:45 Preview · 10:00 Final · 5m Follow-up':active==='BTST'?'Scheduled 15:00 IST':'Every 5 min after 10:00 · research'}),
       e(Tile,{title:'CANDIDATES',value:(data.signals||[]).length,sub:active==='Intraday'?`BUY ${data.qualified_buy||0} · SELL ${data.qualified_sell||0}`:''}),e(Tile,{title:'STATUS',value:data.status||'Waiting'}),e(Tile,{title:'LAST SCAN',value:data.updated_at||'Not yet run'})),
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
       ['Index Options','F&O Stocks'].includes(active)?e(FibOptionSetups,{items:data.fib_setups||[]}):null,
       e(Section,{title:'Existing rule-based research candidates'},
          e(Signals,{items:data.signals||[],empty:data.status||'No qualifying signals. Missing inputs are never filled with invented values.'})))) :null,
    active==='Track Record'?e(TrackRecord,{data}):null,
    e('div',{className:'footer'},'Powered by local Python Flask API · Dhan-sourced analytics only · No broker orders · Data and backtests may be incomplete'))));
}

createRoot(document.getElementById('root')).render(e(App));
