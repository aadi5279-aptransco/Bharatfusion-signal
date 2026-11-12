"""Conservative completed-candle multibagger research ranking.

Score each criterion 0/1; missing data stays UNVERIFIED, never assumed PASS.
Eligibility guards are separate from score (cap, exchange, liquidity, risk).
Fundamentals and surveillance require attributed, dated local JSON data.
"""
from __future__ import annotations
from datetime import date
import math
import pandas as pd

TECH_CRITERIA={
 'monthly_ema':'Last completed monthly close > monthly EMA20',
 'weekly_ema':'Last completed weekly close > weekly EMA20',
 'monthly_rising':'Monthly EMA20 rising',
 'weekly_rising':'Weekly EMA20 rising',
 'near_52w_high':'Within 25% of 52-week high',
 'above_150dma':'Close > 150 DMA',
 'above_200dma':'Close > 200 DMA',
 'rising_200dma':'200 DMA rising 20 sessions',
 'ma_alignment':'50 DMA > 150 DMA > 200 DMA',
 'above_52w_low':'Close 30% above 52-week low',
 'rs_rank':'NIFTY 500 RS rank >70 (independent verified rank)',
}
FUNDAMENTALS={
 'sales_cagr_3y':('Sales CAGR over three years >20%',lambda x:x>20),
 'profit_cagr_3y':('Profit CAGR over three years >20%',lambda x:x>20),
 'quarter_profit_yoy':('Latest quarterly profit YoY >25%',lambda x:x>25),
 'roce':('ROCE >18%',lambda x:x>18),
 'debt_equity':('Debt/equity <0.5',lambda x:x<.5),
 'promoter_holding':('Promoter holding >50%',lambda x:x>50),
 'promoter_pledging':('Promoter pledging <5%',lambda x:x<5),
 'operating_cash_flow':('Operating cash flow positive',lambda x:x>0),
 'peg':('PEG <1.5',lambda x:x<1.5),
}
GUARD_KEYS=('listed_exchange','market_cap_cr','listing_date','asm','gsm',
            'frequent_circuit_locks')


def _number(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None


def _result(key,label,value,source):
    state='UNVERIFIED' if value is None else ('PASS' if bool(value) else 'FAIL')
    return dict(id=key,label=label,status=state,points=int(state=='PASS'),source=source)


def _local_row(bundle,symbol,asof):
    """Source data must have a valid dated envelope and a named source."""
    if not isinstance(bundle,dict):return None
    try:
        d=date.fromisoformat(str(bundle['asof']))
        today=date.fromisoformat(str(asof))
        if d>today or (today-d).days>180:return None
    except (ValueError,TypeError,KeyError):return None
    symbols=bundle.get('symbols') or {}
    if not isinstance(symbols,dict):return None
    normalize=lambda x:''.join(c for c in str(x).upper() if c.isalnum())
    row=next((v for k,v in symbols.items() if normalize(k)==normalize(symbol)),None)
    if not isinstance(row,dict) or not str(row.get('source','')).strip():return None
    try:
        period=date.fromisoformat(str(row['period_end']))
        if period>today or (today-period).days>210:return None
    except (ValueError,TypeError,KeyError):return None
    return row


def evaluate(frame,symbol,asof,fundamentals=None,surveillance=None,rs_rank=None):
    """Completed historical daily frame. Never use current partial daily bar."""
    if frame is None or not isinstance(frame,pd.DataFrame):return None
    if not {'open','high','low','close','volume'}.issubset(frame.columns):return None
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.tz is None:return None
    f=frame.sort_index().copy()
    end=date.fromisoformat(str(asof))
    f=f[f.index.date<=end]
    if f.index.has_duplicates or len(f)<300:return None
    try:
        f[['open','high','low','close','volume']]=f[['open','high','low','close','volume']].astype(float)
    except (ValueError,TypeError):return None
    if f[['open','high','low','close','volume']].isna().any().any():return None
    if (f[['open','high','low','close']]<=0).any().any() or (f.volume<0).any():return None
    c=f.close; last=float(c.iloc[-1])
    e150=c.rolling(150).mean();e200=c.rolling(200).mean();e50=c.rolling(50).mean()
    weekly=f.resample('W-FRI').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    monthly=f.resample('ME').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    # Must discard the last incomplete week/month; close from prior completed period only.
    weekly=weekly[weekly.index.date<=end]
    monthly=monthly[monthly.index.date<=end]
    # pandas timestamps W-FRI/ME label the end of the period. If date is
    # earlier than period end the bar is not included; no look-ahead.
    wet=weekly.close.ewm(span=20,adjust=False).mean() if len(weekly)>=21 else None
    met=monthly.close.ewm(span=20,adjust=False).mean() if len(monthly)>=21 else None
    h52=float(f.high.tail(252).max());l52=float(f.low.tail(252).min())
    criteria=[
        _result('monthly_ema',TECH_CRITERIA['monthly_ema'],
                float(monthly.close.iloc[-1])>float(met.iloc[-1]) if met is not None else None,'Dhan OHLCV'),
        _result('weekly_ema',TECH_CRITERIA['weekly_ema'],
                float(weekly.close.iloc[-1])>float(wet.iloc[-1]) if wet is not None else None,'Dhan OHLCV'),
        _result('monthly_rising',TECH_CRITERIA['monthly_rising'],
                float(met.iloc[-1])>float(met.iloc[-2]) if met is not None else None,'Dhan OHLCV'),
        _result('weekly_rising',TECH_CRITERIA['weekly_rising'],
                float(wet.iloc[-1])>float(wet.iloc[-2]) if wet is not None else None,'Dhan OHLCV'),
        _result('near_52w_high',TECH_CRITERIA['near_52w_high'],last>=.75*h52,'Dhan OHLCV'),
        _result('above_150dma',TECH_CRITERIA['above_150dma'],last>e150.iloc[-1],'Dhan OHLCV'),
        _result('above_200dma',TECH_CRITERIA['above_200dma'],last>e200.iloc[-1],'Dhan OHLCV'),
        _result('rising_200dma',TECH_CRITERIA['rising_200dma'],e200.iloc[-1]>e200.iloc[-21],'Dhan OHLCV'),
        _result('ma_alignment',TECH_CRITERIA['ma_alignment'],e50.iloc[-1]>e150.iloc[-1]>e200.iloc[-1],'Dhan OHLCV'),
        _result('above_52w_low',TECH_CRITERIA['above_52w_low'],last>=1.30*l52,'Dhan OHLCV'),
        _result('rs_rank',TECH_CRITERIA['rs_rank'],
                _number(rs_rank)>70 if _number(rs_rank) is not None else None,'Verified NIFTY 500 rank'),
    ]
    frow=_local_row(fundamentals,symbol,end)
    for key,(label,predicate) in FUNDAMENTALS.items():
        v=_number(frow.get(key)) if frow else None
        criteria.append(_result(key,label,predicate(v) if v is not None else None,
                                str(frow['source']) if frow else 'Fundamentals unavailable'))
    srow=_local_row(surveillance,symbol,end)
    source=str(srow['source']) if srow else 'Exchange surveillance unavailable'
    exc=str(srow.get('listed_exchange','')).upper() if srow else ''
    guards=[
        _result('exchange','NSE or BSE listed',exc in ('NSE','BSE','NSE/BSE','BOTH') if exc else None,source),
        _result('listing_age','At least 365 days listed',
                (end-date.fromisoformat(str(srow['listing_date']))).days>=365
                 if srow and srow.get('listing_date') and _valid_date(srow.get('listing_date')) else None,source),
        _result('asm','Not ASM-listed',not srow['asm'] if srow and type(srow.get('asm')) is bool else None,source),
        _result('gsm','Not GSM-listed',not srow['gsm'] if srow and type(srow.get('gsm')) is bool else None,source),
        _result('circuit','No frequent circuit locks',not srow['frequent_circuit_locks']
                if srow and type(srow.get('frequent_circuit_locks')) is bool else None,source),
    ]
    cap=_number(frow.get('market_cap_cr')) if frow else None
    guards.append(_result('market_cap_data','Verified market capitalization available',cap is not None
                          if frow else None,str(frow['source']) if frow else 'Fundamentals unavailable'))
    # 3-month *daily traded value* is computed from Dhan historical volume
    # times typical price. It is not an executed turnover feed.
    recent=f.tail(63)
    traded=((recent.high+recent.low+recent.close)/3*recent.volume)
    avg_value=float(traded.mean()) if len(recent)>=55 else None
    guards.append(_result('liquidity','63-session average daily traded value > ₹50 lakh',
                          avg_value>5_000_000 if avg_value is not None else None,'Dhan OHLCV traded-value approximation'))
    statuses=[g['status'] for g in guards]
    eligible=(all(x=='PASS' for x in statuses))
    return dict(symbol=symbol,asof=f.index[-1].date().isoformat(),last_close=round(last,2),
        score=sum(x['points'] for x in criteria),score_max=len(criteria),
        verified_count=sum(x['status']!='UNVERIFIED' for x in criteria),
        criteria=criteria,guards=guards,eligible=eligible,
        eligibility_status='ELIGIBLE' if eligible else
          ('BLOCKED' if 'FAIL' in statuses else 'UNVERIFIED'),
        market_cap_cr=cap,avg_daily_traded_value_lakh=round(avg_value/100000,2) if avg_value is not None else None,
        note='Eligibility also depends on the user-selected min/max market cap sliders; no fundamentals or surveillance are inferred.')


def _valid_date(value):
    try:date.fromisoformat(str(value));return True
    except (ValueError,TypeError):return False


def within_market_cap(row,min_cr=300,max_cr=20000):
    """Apply configurable bounds without manufacturing a missing market cap."""
    cap=_number(row.get('market_cap_cr'))
    if cap is None:return False
    return 0<=min_cr<=max_cr and min_cr<=cap<=max_cr
