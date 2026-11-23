"""Resolve index futures from official master fields without contract-name guessing."""
import math
import pandas as pd
from insights.config import IST

ALIASES = {
    'BANKNIFTY': ('NSE', {'BANKNIFTY','NIFTYBANK'}),
    'NIFTY': ('NSE', {'NIFTY','NIFTY50'}),
    'FINNIFTY': ('NSE', {'FINNIFTY','NIFTYFINANCIALSERVICES'}),
    'MIDCPNIFTY': ('NSE', {'MIDCPNIFTY','NIFTYMIDCAPSELECT'}),
    'SENSEX': ('BSE', {'SENSEX'}),
}
def normal(value):
    return ''.join(c for c in str(value).upper() if c.isalnum())

def resolve_index_future(raw,item,now):
    needed={'EXCH_ID','INSTRUMENT','SECURITY_ID','UNDERLYING_SECURITY_ID','SM_EXPIRY_DATE'}
    if raw is None or not needed.issubset(raw.columns):
        return None
    source=str(item.get('id','')).strip().removesuffix('.0')
    if not source:
        return None
    identity=next((v for v in ALIASES.values() if normal(item.get('symbol','')) in v[1]),None)
    rows=raw.copy()
    for col in needed-{'SM_EXPIRY_DATE'}:
        rows[col]=rows[col].fillna('').astype(str).str.strip()
    rows=rows[rows.INSTRUMENT.eq('FUTIDX')].copy()
    if identity:
        rows=rows[rows.EXCH_ID.eq(identity[0])].copy()
    rows['exp']=pd.to_datetime(rows.SM_EXPIRY_DATE,errors='coerce',utc=True)
    rows=rows[rows.exp.notna() & (rows.exp.dt.date>=now.astimezone(IST).date())].copy()
    ids=rows.UNDERLYING_SECURITY_ID.str.removesuffix('.0')
    candidates=rows[ids.eq(source)].copy()
    method='UNDERLYING_SECURITY_ID'
    if candidates.empty and identity and 'UNDERLYING_SYMBOL' in rows.columns:
        names=rows.UNDERLYING_SYMBOL.fillna('').map(normal)
        named=rows[names.isin(identity[1])].copy()
        named_ids=named.UNDERLYING_SECURITY_ID.str.removesuffix('.0')
        # An explicit different ID is a conflict, not permission to guess.
        if (~named_ids.isin(['','0','-1','nan','None'])).any():
            return None
        candidates=named
        method='EXACT_UNDERLYING_SYMBOL'
    if candidates.empty:
        return None
    # Reject a conflicting symbol even when the ID matches.
    if identity and 'UNDERLYING_SYMBOL' in candidates:
        names=candidates.UNDERLYING_SYMBOL.fillna('').map(normal)
        if (~names.isin(identity[1] | {''})).any():
            return None
    candidates=candidates[candidates.SECURITY_ID.ne('')].copy()
    if candidates.empty:
        return None
    nearest=candidates[candidates.exp.eq(candidates.exp.min())]
    if len(nearest[['EXCH_ID','SECURITY_ID']].drop_duplicates())!=1:
        return None
    row=nearest.iloc[0]
    segment={'NSE':'NSE_FNO','BSE':'BSE_FNO'}.get(row.EXCH_ID)
    if not segment:
        return None
    try:
        tick=float(row.get('TICK_SIZE',0))
        tick=tick if math.isfinite(tick) and tick>0 else None
    except (ValueError,TypeError):
        tick=None
    return dict(id=str(row.SECURITY_ID).removesuffix('.0'),segment=segment,
        instrument='FUTIDX',expiry=row.exp.date().isoformat(),
        symbol=str(row.get('SYMBOL_NAME','INDEX-FUTIDX')),tick_size=tick,
        mapping_method=method,underlying_id=source,
        master_underlying_id=str(row.UNDERLYING_SECURITY_ID),
        master_underlying_symbol=str(row.get('UNDERLYING_SYMBOL','')))
