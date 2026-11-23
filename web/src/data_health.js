import React from 'react';
const e=React.createElement;
export default function DataHealth({data}){
 if(!data)return null;
 const p=data.profile||{},q=data.quota||{},quality=data.quality||{};
 return e('details',{className:'notice'},e('summary',null,'Dhan data health · ',p.status||'Not checked',q.quota_warning?' · QUOTA WARNING':''),
 e('p',null,'Data plan: ',p.data_plan||'Unverified',' · Token validity: ',p.token_validity||'Unverified',' · Data validity: ',p.data_validity||'Unverified'),
 p.error?e('p',{role:'alert'},p.error):null,
 e('p',null,'Data requests today: ',q.data_requests||0,' / ',q.data_limit||100000,' · Quote requests: ',q.requests?.quote||0),
 q.last_error?e('p',{role:'alert'},q.last_error):null,
 e('p',null,'Latest candle validation: ',quality.status||'No history checked',' · Latest stored bar: ',quality.last_bar||'—'),
 e('p',null,'Instrument master: ',data.master?.status||'Not loaded'),
 e('p',null,data.adjustment_status),e('p',null,q.quota_scope),e('p',null,data.live_validation));
}
