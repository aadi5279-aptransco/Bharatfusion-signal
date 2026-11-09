"""Read-only Dhan v2 transport and local cache. Credentials stay in memory."""
from __future__ import annotations
import io,json,time,sqlite3,urllib.request,urllib.error
from pathlib import Path
import pandas as pd
from engine import clean,IST

class DataError(Exception): pass
class AuthError(DataError): pass

class Dhan:
    def __init__(self,client_id,token,stop):
        self.client_id=client_id; self.token=token; self.stop=stop; self.last=0;self.option_last=0
    def request(self,path,payload=None):
        # Only allow audited read endpoints (Dhan uses POST for historical data).
        if path not in ('/charts/intraday','/marketfeed/quote','/data/companyinfo','/data/newsheadline','/charts/historical','/optionchain','/optionchain/expirylist'):
            raise DataError('Endpoint not allowed')
        for attempt in range(4):
            delay=max(0,.28-(time.monotonic()-self.last),3.1-(time.monotonic()-self.option_last) if path.startswith('/optionchain') else 0)
            if self.stop.wait(delay): raise DataError('Stopped')
            req=urllib.request.Request('https://api.dhan.co/v2'+path,data=json.dumps(payload).encode(),
                headers={'access-token':self.token,'client-id':self.client_id,'Content-Type':'application/json','Accept':'application/json'},method='POST')
            self.last=time.monotonic()
            if path.startswith('/optionchain'):self.option_last=self.last
            try:
                with urllib.request.urlopen(req,timeout=20) as response: result=json.load(response)
                if result.get('status')=='failure':
                    code=str(result.get('errorCode',''))
                    if code in ('DH-901','DH-902'): raise AuthError('Dhan authentication/access rejected. Check token and Data API access.')
                    raise DataError('Dhan returned a failure; check entitlement and instrument mapping.')
                return result
            except urllib.error.HTTPError as exc:
                if exc.code in (401,403): raise AuthError('Dhan rejected access. Check credentials and Data API subscription.') from None
                if exc.code not in (429,500,502,503,504) or attempt==3: raise DataError(f'Dhan HTTP {exc.code}; no signal generated') from None
            except (urllib.error.URLError,TimeoutError):
                if attempt==3: raise DataError('Dhan network timeout/unavailable') from None
            except (ValueError,TypeError): raise DataError('Dhan response schema/JSON invalid') from None
            if self.stop.wait(2**attempt): raise DataError('Stopped')
        raise DataError('Dhan retry limit reached')
    def history(self,item,start,end):
        raw=self.request('/charts/intraday',dict(securityId=item['id'],exchangeSegment=item['segment'],instrument=item['instrument'],interval='1',oi=False,
                    fromDate=start.strftime('%Y-%m-%d %H:%M:%S'),toDate=end.strftime('%Y-%m-%d %H:%M:%S')))
        if not isinstance(raw.get('timestamp'),list): raise DataError('Candle timestamps missing')
        if not raw['timestamp']: raise DataError('No candles returned')
        try:
            f=pd.DataFrame({k:raw[k] for k in ('open','high','low','close','volume')},index=pd.to_datetime(raw['timestamp'],unit='s',utc=True).tz_convert(IST))
            return clean(f)
        except (KeyError,ValueError,TypeError): raise DataError('Invalid candle payload') from None
    def daily(self,item,start,end):
        raw=self.request('/charts/historical',dict(securityId=item['id'],exchangeSegment=item['segment'],instrument=item['instrument'],expiryCode=0,oi=False,fromDate=start.strftime('%Y-%m-%d'),toDate=end.strftime('%Y-%m-%d')))
        try:
            f=pd.DataFrame({k:raw[k] for k in ('open','high','low','close','volume')},index=pd.to_datetime(raw['timestamp'],unit='s',utc=True).tz_convert(IST).normalize()).astype(float)
            import numpy as np
            if f.empty or not np.isfinite(f.to_numpy()).all() or (f[['open','high','low','close']]<=0).any().any() or (f.volume<0).any() or (f.high<f[['open','close','low']].max(axis=1)).any() or (f.low>f[['open','close','high']].min(axis=1)).any():raise ValueError()
            return f[~f.index.duplicated(keep='last')].sort_index()
        except (ValueError,KeyError,TypeError):raise DataError('Invalid daily history') from None
    def expiry_list(self,item):
        return self.request('/optionchain/expirylist',dict(UnderlyingScrip=int(item['id']),UnderlyingSeg=item['segment'])).get('data',[])
    def option_chain(self,item,expiry):
        return self.request('/optionchain',dict(UnderlyingScrip=int(item['id']),UnderlyingSeg=item['segment'],Expiry=expiry))
    def news(self,stock_ids=None,macro=False):
        body=dict(dhanClientId=self.client_id,categories=['INDIAN_ECONOMY','GLOBAL_ECONOMY','EQUITY_MARKETS'] if macro else ['ALL'],limit=50)
        if stock_ids:body['stockList']=list(stock_ids)
        return self.request('/data/newsheadline',body).get('data',{}).get('latestNews',[])
    def company_info(self,item):
        result=self.request('/data/companyinfo',dict(securityId=item['id'],exchangeSegment=item['segment'],instrument='EQUITY',metrics=['CO','RATIOS','SHP']))
        if str(result.get('securityId',''))!=str(item['id']):raise DataError('Company snapshot security ID mismatch')
        return dict(data=result.get('data',{}),fetched_at=pd.Timestamp.now(tz=IST).isoformat())
    def quotes(self,items):
        payload={}
        for x in items: payload.setdefault(x['segment'],[]).append(int(x['id']))
        return self.request('/marketfeed/quote',payload).get('data',{})


def parse_master(f,extra_ids=()):
    required={'EXCH_ID','SEGMENT','INSTRUMENT','SECURITY_ID','UNDERLYING_SECURITY_ID','SYMBOL_NAME','SERIES'}
    if not required.issubset(f.columns): raise DataError('Unexpected detailed instrument-master schema')
    f=f.fillna('').astype(str)
    futures=f[(f.EXCH_ID=='NSE')&(f.INSTRUMENT=='FUTSTK')]
    if 'SM_EXPIRY_DATE' in futures:
        expiry=pd.to_datetime(futures.SM_EXPIRY_DATE,errors='coerce',utc=True)
        futures=futures[expiry.dt.date>=pd.Timestamp.now(tz=IST).date()]
    ids=set(futures.UNDERLYING_SECURITY_ID.str.replace(r'\.0$','',regex=True))
    stocks=f[(f.EXCH_ID=='NSE')&(f.SEGMENT=='E')&(f.INSTRUMENT=='EQUITY')&(f.SERIES=='EQ')]
    stocks=stocks[stocks.SECURITY_ID.isin(ids|set(extra_ids))]
    stocks=stocks[~stocks.SYMBOL_NAME.str.contains('TEST|DUMMY',case=False,regex=True)]
    if 'ASM_GSM_FLAG' in stocks: stocks=stocks[stocks.ASM_GSM_FLAG!='Y']
    items=[dict(symbol=r.SYMBOL_NAME,ticker=getattr(r,'UNDERLYING_SYMBOL',''),id=r.SECURITY_ID,segment='NSE_EQ',instrument='EQUITY',kind='stock') for r in stocks.drop_duplicates('SECURITY_ID').itertuples()]
    # Attach genuine futures and option contracts; never use equity bars as a futures substitute.
    for item in items:
        subset=f[(f.EXCH_ID=='NSE')&(f.UNDERLYING_SECURITY_ID.str.replace(r'\.0$','',regex=True)==item['id'])]
        contracts=[];future_rows=[]
        for row in subset.to_dict('records'):
            try:
                expiry=str(pd.Timestamp(row.get('SM_EXPIRY_DATE')).date())
                if expiry<=str(pd.Timestamp.now(tz=IST).date()):continue
                if row['INSTRUMENT']=='FUTSTK':future_rows.append(dict(id=row['SECURITY_ID'],segment='NSE_FNO',instrument='FUTSTK',expiry=expiry,symbol=row['SYMBOL_NAME']))
                if row['INSTRUMENT']=='OPTSTK' and row.get('OPTION_TYPE') in ('CE','PE'):
                    contracts.append(dict(id=row['SECURITY_ID'],segment='NSE_FNO',instrument='OPTSTK',expiry=expiry,side=row['OPTION_TYPE'],strike=float(row['STRIKE_PRICE']),lot=int(float(row['LOT_SIZE'])),symbol=row['SYMBOL_NAME']))
            except (ValueError,TypeError,KeyError):continue
        item['future']=min(future_rows,key=lambda x:x['expiry']) if future_rows else None
        item['options']=contracts
    names={'NIFTY','NIFTY50','NIFTYBANK','BANKNIFTY','NIFTYFINANCIALSERVICES','FINNIFTY','NIFTYMIDCAPSELECT','MIDCPNIFTY','SENSEX'}
    from market_dashboard import SECTORS
    indexes=f[f.INSTRUMENT.isin(['INDEX'])]
    for r in indexes.itertuples():
        normal=''.join(c for c in r.SYMBOL_NAME.upper() if c.isalnum())
        if normal in SECTORS:items.append(dict(symbol=r.SYMBOL_NAME,id=r.SECURITY_ID,segment='IDX_I',instrument='INDEX',kind='sector',sector=SECTORS[normal]))
        if normal in names: items.append(dict(symbol=r.SYMBOL_NAME,id=r.SECURITY_ID,segment='IDX_I',instrument='INDEX',kind='index'))
    items=list({(x['segment'],x['id']):x for x in items}.values())
    if not any(x['kind']=='stock' for x in items): raise DataError('No eligible F&O stock underlyings mapped; scan blocked')
    if not any(x['kind']=='index' for x in items): raise DataError('No major indices mapped; inspect current Dhan master')
    return sorted(items,key=lambda x:(x['kind']!='index',x['symbol']))


_MASTER=None

def universe(extra_ids=(),reuse=False):
    global _MASTER
    try:
        if not reuse or _MASTER is None:
            with urllib.request.urlopen('https://images.dhan.co/api-data/api-scrip-master-detailed.csv',timeout=45) as response: payload=response.read()
            _MASTER=pd.read_csv(io.BytesIO(payload),dtype=str,low_memory=False)
        return parse_master(_MASTER,extra_ids)
    except DataError: raise
    except Exception: raise DataError('Cannot download/parse the Dhan detailed master. Check internet connection.') from None

class Cache:
    def __init__(self,folder):
        Path(folder).mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(Path(folder)/'market.sqlite',timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS book (key TEXT,ts INTEGER,spread_bps REAL,book_imbalance REAL,PRIMARY KEY(key,ts))')
        self.db.execute('CREATE INDEX IF NOT EXISTS book_time ON book(ts)')
        self.db.execute('CREATE TABLE IF NOT EXISTS bars (key TEXT, ts INTEGER, o REAL,h REAL,l REAL,c REAL,v REAL,PRIMARY KEY(key,ts))')
        self.db.execute('CREATE TABLE IF NOT EXISTS daily (key TEXT, ts INTEGER,o REAL,h REAL,l REAL,c REAL,v REAL,PRIMARY KEY(key,ts))')
        self.db.execute('CREATE TABLE IF NOT EXISTS journal (key TEXT PRIMARY KEY, created TEXT, payload TEXT)')
    def save_book(self,key,quote,received,commit=True):
        try:
            t=pd.Timestamp(quote['last_trade_time'],dayfirst=True)
            if t.tzinfo is None:t=t.tz_localize(IST)
            if not 0<=(received-t).total_seconds()<=120:return False
            buys=quote['depth']['buy'];sells=quote['depth']['sell'];bid=float(buys[0]['price']);ask=float(sells[0]['price'])
            if bid<=0 or ask<bid:return False
            b=sum(float(x['quantity']) for x in buys);a=sum(float(x['quantity']) for x in sells)
            if a+b<=0:return False
            spread=(ask-bid)/((ask+bid)/2)*10000;imb=(b-a)/(b+a)
            self.db.execute('INSERT OR REPLACE INTO book VALUES (?,?,?,?)',(key,float(received.timestamp()),spread,imb));
            if commit:self.db.commit()
            return True
        except (KeyError,ValueError,TypeError,IndexError):return False
    def load_book(self,key):
        rows=self.db.execute('SELECT ts,spread_bps,book_imbalance FROM book WHERE key=? ORDER BY ts',(key,)).fetchall()
        if not rows:return None
        f=pd.DataFrame(rows,columns=['timestamp','spread_bps','book_imbalance']);f.index=pd.to_datetime(f.pop('timestamp'),unit='s',utc=True).dt.tz_convert(IST);return f
    def load(self,key):
        rows=self.db.execute('SELECT ts,o,h,l,c,v FROM bars WHERE key=? ORDER BY ts',(key,)).fetchall()
        if not rows: return None
        f=pd.DataFrame(rows,columns=['timestamp','open','high','low','close','volume'])
        f.index=pd.to_datetime(f.pop('timestamp'),unit='s',utc=True).dt.tz_convert(IST)
        return f
    def save(self,key,f):
        self.db.executemany('INSERT OR REPLACE INTO bars VALUES (?,?,?,?,?,?,?)',[(key,int(t.timestamp()),*map(float,row)) for t,row in f.iterrows()])
        cutoff=int((pd.Timestamp.now(tz=IST)-pd.Timedelta(days=90)).timestamp())
        self.db.execute('DELETE FROM bars WHERE ts < ?',(cutoff,)); self.db.commit()
    def load_daily(self,key):
        rows=self.db.execute('SELECT ts,o,h,l,c,v FROM daily WHERE key=? ORDER BY ts',(key,)).fetchall()
        if not rows:return None
        f=pd.DataFrame(rows,columns=['timestamp','open','high','low','close','volume']);f.index=pd.to_datetime(f.pop('timestamp'),unit='s',utc=True).dt.tz_convert(IST);return f
    def save_daily(self,key,f):
        self.db.executemany('INSERT OR REPLACE INTO daily VALUES (?,?,?,?,?,?,?)',[(key,int(t.timestamp()),*map(float,row)) for t,row in f.iterrows()]);self.db.commit()
    def record(self,result,mode):
        if result['action']=='WAIT': return False
        key=f"{mode}:{result['symbol']}:{result['candle']}:{result['action']}"
        cur=self.db.execute('INSERT OR IGNORE INTO journal VALUES (?,?,?)',(key,pd.Timestamp.now(tz=IST).isoformat(),json.dumps(result)))
        self.db.commit(); return cur.rowcount==1
    def close(self): self.db.close()
