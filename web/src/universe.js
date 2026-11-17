import React from 'react';
const e=React.createElement;
export default function UniverseCoverage({data}){
 if(!data)return null;
 const missing=data.missing_symbols||[],ambiguous=data.ambiguous_symbols||[],excluded=data.surveillance_excluded||[],ineligible=data.ineligible_constituents||[];
 return e('div',{className:'notice'},
  e('strong',null,'NIFTY 500 universe · ',data.status||'Awaiting source'),
  e('p',{className:'small'},'Constituent rows: ',data.constituents??'—',' · Mapped eligible NSE equities: ',data.mapped??'—',' · Missing: ',missing.length,' · Ambiguous: ',ambiguous.length,
   ' · Excluded: ',excluded.length+ineligible.length),
  e('p',{className:'small muted'},'List retrieved: ',data.retrieved_at||'—',' · ',data.origin||'',' · Cache age: ',data.cache_age_days??'—',' days'),
  data.error?e('p',{role:'alert'},data.error):null,
  missing.length+ambiguous.length+excluded.length+ineligible.length?e('details',null,e('summary',null,'Mapping and eligibility exceptions'),
   missing.length?e('p',null,'No exact ISIN mapping: ',missing.join(', ')):null,
   ambiguous.length?e('p',null,'Ambiguous mapping: ',ambiguous.join(', ')):null,
   excluded.length?e('p',null,'Dhan surveillance flag: ',excluded.join(', ')):null,
   ...ineligible.map(x=>e('p',{key:x.symbol},x.symbol,': ',x.reason))):null,
  data.source?e('a',{href:data.source,target:'_blank',rel:'noreferrer'},'Official constituent CSV'):null);
}
