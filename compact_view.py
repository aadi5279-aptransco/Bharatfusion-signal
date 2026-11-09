"""Presentation only: never changes strategy eligibility or price semantics."""
STRATEGY_TABS=('Stock options','BTST stocks','Institutional stocks','AI selected stocks','RSI strategy')

def strategy_rows(base,name):
 key={'Stock options':'options_row','BTST stocks':'btst_rows','Institutional stocks':'institutional_row','AI selected stocks':'ai_row','RSI strategy':'rsi_row'}[name]
 value=base.get(key)
 if value is None:return [dict(symbol=base['symbol'],strategy=name,matched=False,eligible=False,reason='Waiting for background analysis')]
 return value if isinstance(value,list) else [value]

def all_strategy_rows(base):
 return [r for tab in STRATEGY_TABS for r in strategy_rows(base,tab)]

COLUMNS=('symbol','setup','contract','view_entry','view_t1','view_t2','view_sl','view_status')
HEADINGS=dict(symbol='STOCK / INDEX',setup='SETUP',contract='TRADE',view_entry='ENTRY ₹',view_t1='T1 ₹',view_t2='T2 ₹',view_sl='SL ₹',view_status='STATUS / WHY')

def compact(row,tab):
 r=dict(row)
 if tab in STRATEGY_TABS:
  option=bool(r.get('option_side'))
  r['setup']=r.get('strategy','Waiting')
  strike=r.get('atm_strike');side=r.get('option_side','')
  r['contract']=(f'{strike:g} {side}' if isinstance(strike,(float,int)) else 'ATM '+side+' pending') if option else 'Cash stock'
  prefix='premium_' if option else 'underlying_'
  for dest,src in [('entry','entry'),('t1','t1_est' if option else 't1'),('t2','t2_est' if option else 't2'),('sl','sl_est' if option else 'sl')]:r['view_'+dest]=r.get(prefix+src)
  reason=str(r.get('reason','Waiting for data'))
  if r.get('eligible'):status='READY (research)'
  elif not r.get('matched'):status='WAIT — '+reason
  else:status='NO ENTRY — '+reason
  r['view_status']=status
 else:
  p=r.get('intraday_plan',{}) if tab=='Intraday Top 10' else r
  r['setup']=p.get('plan_direction',r.get('bias','—'));r['contract']='Underlying levels'
  for dest,src in [('entry','plan_entry'),('t1','plan_t1'),('t2','plan_t2'),('sl','plan_stop')]:r['view_'+dest]=p.get(src)
  r['view_status']=p.get('plan_status',r.get('action','WAIT'))
 return r

def details(r):
 option=bool(r.get('option_side'))
 lines=[f"{r.get('symbol','')} — {r.get('strategy','')}",r.get('view_status',r.get('strategy_status','WAIT')),'',
        'Why: '+str(r.get('reason','Waiting for data')),'',
        'Table prices: '+('option premium; T1/T2/SL are estimates, not guaranteed fills.' if option else 'cash-stock prices.'),
        'Expiry: '+str(r.get('expiry','Not available'))+' | Quantity: '+str(r.get('quantity','—')),
        'Updated: '+str(r.get('data_at','Not available')),
        'Trigger: '+str(r.get('trigger_at','Not available')),
        'Underlying entry / T1 / T2 / SL: '+' / '.join(str(r.get('underlying_'+k,'—')) for k in ('entry','t1','t2','sl')),
        'Ban check: '+str(r.get('ban_check','Unknown')),
        'Delivery: '+str(r.get('delivery_pct','—'))+'% | Report date: '+str(r.get('delivery_date','—')),
        'Events: '+str(r.get('event_check','Unknown')),
        'Estimated risk: '+str(r.get('estimated_risk','—')),
        'Stop rule: '+str(r.get('stop_basis','—'))]
 lines += ['Monthly / weekly / daily RSI: '+' / '.join(str(r.get(k,'—')) for k in ('monthly_rsi','weekly_rsi','daily_rsi')), 'Relative volume: '+str(r.get('volume_ratio','—')), 'ScanX source: '+str(r.get('source_at','—')), 'ML context: '+str(r.get('ml_status','Not used for this rule')), 'Evidence: '+'; '.join(r.get('evidence',[]))]
 if r.get('rsi_asof'):lines += ['Completed daily RSI date: '+r['rsi_asof'], 'Monthly / weekly period start: '+r.get('monthly_asof','—')+' / '+r.get('weekly_asof','—'), 'Price / strength checks: '+r.get('price_confirmation','WAIT')+' / '+r.get('strength_confirmation','WAIT'), '15m ADX: '+str(r.get('adx','—')), '15m confirmation close: '+r.get('confirmation_at','—')]
 return '\n'.join(lines)
