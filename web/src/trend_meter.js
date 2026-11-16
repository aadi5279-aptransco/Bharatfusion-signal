import React from 'react';
const e=React.createElement;
const point=(s,r)=>{const a=s*Math.PI/200;return [140+r*Math.sin(a),145-r*Math.cos(a)]};
const arc=(a,b)=>{const p=point(a,110),q=point(b,110);return `M ${p[0]} ${p[1]} A 110 110 0 0 1 ${q[0]} ${q[1]}`};
export default function TrendMeter({title,bias,score,asof,sessionPoints,sessionChange,historical=false}){
 const valid=typeof score==='number'&&Number.isFinite(score)&&['Uptrend','Downtrend','Sideways'].includes(bias);
 const label=!valid?'Awaiting data':bias==='Uptrend'?'Bullish':bias==='Downtrend'?'Bearish':'Sideways';
 const tone=!valid?'neutral':bias==='Uptrend'?'bull':bias==='Downtrend'?'bear':'neutral';
 const tip=point(valid?Math.max(-100,Math.min(100,score)):0,88);
 const when=asof&&Number.isFinite(Date.parse(asof))?new Date(asof).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):null;
 return e('article',{className:'tile trend-meter '+(!valid?'trend-meter-empty':'')},e('div',{className:'kicker'},title),
 e('svg',{viewBox:'0 0 280 178',className:'trend-meter-svg',role:'img','aria-label':`${title}: ${label}${valid?`, signed rule score ${score} out of 100`:''}${historical?', historical snapshot':''}`},
 ...[[-100,-42,'bear'],[-38,38,'neutral'],[42,100,'bull']].map(([a,b,c])=>e('path',{key:c,d:arc(a,b),fill:'none',strokeWidth:17,className:'trend-arc-'+c})),
 ...[-100,-75,-50,-25,0,25,50,75,100].map(n=>{const a=point(n,124),b=point(n,130);return e('line',{key:n,x1:a[0],y1:a[1],x2:b[0],y2:b[1],className:'trend-tick'})}),
 valid?e('line',{x1:140,y1:145,x2:tip[0],y2:tip[1],className:'trend-needle'}):null,e('circle',{cx:140,cy:145,r:8,className:'trend-pivot'}),
 e('text',{x:17,y:172,className:'trend-end-label'},'Bearish'),e('text',{x:263,y:172,textAnchor:'end',className:'trend-end-label'},'Bullish')),
 e('div',{className:'trend-reading trend-'+tone},label,valid?e('strong',null,`${score>0?'+':''}${score}`):null),
 e('p',{className:'trend-caption'},valid?'TECHNICAL TREND SCORE / 100 · NOT PROBABILITY':'NO VERIFIED TREND SCORE'),
 Number.isFinite(sessionPoints)?e('p',{className:'small'},`Since first session candle open: ${sessionPoints>=0?'+':''}${sessionPoints.toFixed(2)} pts (${Number.isFinite(sessionChange)?sessionChange.toFixed(2):'—'}%)`):null,
 e('p',{className:'small muted'},'Day change from official previous close is not supplied by this candle snapshot.'),
 e('p',{className:'small muted'},historical?'Historical snapshot · not live':'Completed-candle trend'),when?e('p',{className:'small muted'},when,' IST'):null);
}
