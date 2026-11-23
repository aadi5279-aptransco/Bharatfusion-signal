"""Daily official detailed master cache; no guessed IDs, expiries or lots."""
import io,time,json
from datetime import datetime
from insights.config import IST
from urllib.request import build_opener
import pandas as pd
from .transport import NoRedirect,DataError
URL='https://images.dhan.co/api-data/api-scrip-master-detailed.csv'
REQUIRED={'EXCH_ID','SEGMENT','INSTRUMENT','SECURITY_ID','UNDERLYING_SECURITY_ID','SYMBOL_NAME','SERIES'}
class Master:
    def __init__(self,transport):
        self.transport=transport;self.status={'status':'NOT LOADED'}
        with transport.db() as db:db.execute('CREATE TABLE IF NOT EXISTS instrument_master(id INTEGER PRIMARY KEY, csv BLOB, fetched REAL)');db.commit()
    def load(self,force=False):
        with self.transport.db() as db:cached=db.execute('SELECT csv,fetched FROM instrument_master WHERE id=1').fetchone()
        if cached and not force and datetime.fromtimestamp(cached[1],IST).date()==datetime.now(IST).date():raw=cached[0];fetched=cached[1]
        else:
            try:
                with build_opener(NoRedirect()).open(URL,timeout=45) as r:raw=r.read(100_000_001)
                if len(raw)>100_000_000:raise ValueError()
                fetched=time.time()
            except Exception:
                self.status={'status':'UNAVAILABLE — refresh official instrument master'}
                raise DataError('Official Dhan instrument master unavailable; stale mappings not substituted') from None
        try:
            f=pd.read_csv(io.BytesIO(raw),dtype=str,low_memory=False).fillna('')
            if f.empty or not REQUIRED.issubset(f.columns):raise ValueError()
            if f.SECURITY_ID.eq('').any():raise ValueError()
        except Exception:raise DataError('Unrecognized official instrument master schema') from None
        if not cached or fetched!=cached[1]:
            with self.transport.db() as db:db.execute('INSERT OR REPLACE INTO instrument_master VALUES(1,?,?)',(raw,fetched));db.commit()
        self.status=dict(status='OFFICIAL MASTER LOADED',rows=len(f),fetched_at=fetched,source=URL,
                         surveillance_status='Full ban/suspension/SME eligibility requires separate exchange evidence')
        return f
