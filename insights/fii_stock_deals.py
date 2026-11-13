"""NSE disclosed FII/FPI stock bulk/block deals (NOT total daily FII trades).

The NSE F&O participant OI files contain no stock-level FII transactions.
This module processes exchange disclosed cash bulk/block deals with exact,
auditable FPI identity matching. No fund name guessing or fabricated flows.
"""
from __future__ import annotations

import csv
import io
import json
import hashlib
import math
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen,Request
from urllib.error import HTTPError,URLError

from insights.config import IST,is_market_session

SOURCE_PAGE="https://www.nseindia.com/report-detail/display-bulk-and-block-deals"
SOURCE_API="https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
VERSION="verified-fii-disclosed-deals-v1"


def _normal(value):
    return re.sub("[^a-z0-9]","",str(value or "").lower())


def _date(value):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    s=str(value or "").strip()
    for fmt in ("%Y-%m-%d","%d-%m-%Y","%d-%b-%Y","%d-%B-%Y","%d/%m/%Y",
                "%d %b %Y","%d %B %Y"):
        try:return datetime.strptime(s,fmt).date()
        except ValueError:continue
    raise ValueError("Unrecognized exchange deal date")


def _headers(names):
    options={
     "trade_date":("date","tradedate","dealdate"),
     "symbol":("symbol","stocksymbol","securitysymbol"),
     "client":("clientname","client","buyername","sellername"),
     "side":("buysell","bs","buysellindicator","transactiontype"),
     "quantity":("quantitytraded","quantity","volume","qty"),
     "price":("tradepricewghtavgprice","tradepriceweightedavgprice",
              "weightedavgprice","price","tradeprice","tradepricewgtavgprice"),
    }
    columns=[_normal(v) for v in names]
    matched={}
    for k,alternatives in options.items():
        for alias in alternatives:
            if alias in columns:
                matched[k]=columns.index(alias);break
    if not {"trade_date","symbol","client","side","quantity","price"}.issubset(matched):
        raise ValueError("NSE disclosed-deal CSV column mapping unsupported")
    return matched


def parse_report(raw,kind):
    """Strict report mapping. Reject HTML/JSON, malformed rows and unknown sides."""
    if kind not in ("bulk","block"):raise ValueError("Unsupported deal type")
    if not isinstance(raw,bytes) or not 45<len(raw)<=2_000_000:
        raise ValueError("NSE report empty or too large")
    text=raw.decode("utf-8-sig")
    if "<html" in text[:500].lower() or text.lstrip().startswith(("{","[")):
        raise ValueError("NSE did not return a deals CSV")
    rows=list(csv.reader(io.StringIO(text)))
    header_idx=None;fields=None
    for i,line in enumerate(rows[:10]):
        try:
            fields=_headers(line);header_idx=i;break
        except ValueError:continue
    if header_idx is None:raise ValueError("NSE deal report missing required header")
    output=[]
    for line in rows[header_idx+1:]:
        if not line or not any(x.strip() for x in line):continue
        if max(fields.values())>=len(line):raise ValueError("Truncated NSE disclosed-deal row")
        d=_date(line[fields["trade_date"]])
        symbol=line[fields["symbol"]].strip().upper()
        client=line[fields["client"]].strip()
        side=line[fields["side"]].strip().upper()
        if side in ("B","BUY"):side="BUY"
        elif side in ("S","SELL"):side="SELL"
        else:raise ValueError("Unsupported NSE buy/sell flag")
        try:
            qty=int(float(line[fields["quantity"]].replace(",","")))
            price=float(line[fields["price"]].replace(",",""))
        except (ValueError,TypeError):raise ValueError("Invalid trade quantity/price") from None
        if not re.fullmatch(r"[A-Z0-9&._-]{1,32}",symbol) or not client or len(client)>240:
            raise ValueError("Invalid reported symbol or client")
        if qty<=0 or not math.isfinite(price) or price<=0:
            raise ValueError("Invalid deal quantity or traded price")
        output.append(dict(trade_date=d.isoformat(),symbol=symbol,client=client,
                           side=side,quantity=qty,price=round(price,4),deal_type=kind.upper()))
    return output


def _registry(root):
    """Only exact verified client-name matches; never infer FPI from 'fund'."""
    path=Path(os.getenv("INSIGHTS_VERIFIED_FPI_REGISTRY") or
              (Path(root)/"verified_fpi_clients.json"))
    try:raw=json.loads(path.read_text("utf-8"))
    except (OSError,ValueError):return {}
    if not isinstance(raw,dict):return {}
    items=raw.get("clients",[])
    if not isinstance(items,list):return {}
    verified={}
    for item in items[:5000]:
        if not isinstance(item,dict):continue
        name=str(item.get("client_name") or "").strip()
        status=str(item.get("category") or "").upper()
        proof=str(item.get("verification_source") or "").strip()
        if name and status in ("FII","FPI") and proof.startswith("https://"):
            verified[_normal(name)]={"name":name,"category":status,"proof":proof}
    return verified


def _identity(name,registry):
    exact=registry.get(_normal(name))
    if exact:return dict(verified=True,proof=exact["proof"],identity=exact["category"])
    # Labels such as 'FUND', 'CAPITAL', and 'FOREIGN' alone do not prove
    # registration as an FPI. Unknown identities must not be classified.
    return dict(verified=False,proof=None,identity="UNVERIFIED")


class DealStore:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS disclosed_deals(
                trade_date TEXT NOT NULL, deal_type TEXT NOT NULL,
                symbol TEXT NOT NULL, client TEXT NOT NULL,
                side TEXT NOT NULL, quantity INTEGER NOT NULL,
                price REAL NOT NULL, report_sha256 TEXT NOT NULL,
                source_url TEXT NOT NULL,
                PRIMARY KEY(trade_date,deal_type,symbol,client,side,quantity,price))""")
            db.execute("""CREATE TABLE IF NOT EXISTS disclosed_report_days(
                trade_date TEXT NOT NULL, deal_type TEXT NOT NULL,
                report_sha256 TEXT NOT NULL, loaded_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                PRIMARY KEY(trade_date,deal_type))""")

    @contextmanager
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=8)
        try:
            db.execute("PRAGMA busy_timeout=8000")
            with db:yield db
        finally:db.close()

    def ingest(self,raw,kind,day,url):
        day=_date(day)
        rows=parse_report(raw,kind)
        if any(row["trade_date"]!=day.isoformat() for row in rows):
            raise ValueError("NSE disclosed report contains another trading date")
        digest=hashlib.sha256(raw).hexdigest()
        with self.connect() as db:
            db.execute("DELETE FROM disclosed_deals WHERE trade_date=? AND deal_type=?",
                       (day.isoformat(),kind.upper()))
            for r in rows:
                db.execute("""INSERT OR REPLACE INTO disclosed_deals
                    (trade_date,deal_type,symbol,client,side,quantity,price,report_sha256,source_url)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (r["trade_date"],r["deal_type"],r["symbol"],r["client"],
                     r["side"],r["quantity"],r["price"],digest,url))
            db.execute("""INSERT OR REPLACE INTO disclosed_report_days
                (trade_date,deal_type,report_sha256,loaded_at,source_url)
                VALUES(?,?,?,?,?)""",
                (day.isoformat(),kind.upper(),digest,datetime.now(IST).isoformat(),url))
        return len(rows)

    def has_day(self,kind,day):
        with self.connect() as db:
            return bool(db.execute("""SELECT 1 FROM disclosed_report_days
                 WHERE trade_date=? AND deal_type=?""",
                 (_date(day).isoformat(),kind.upper())).fetchone())

    def recent(self,days=15):
        with self.connect() as db:
            return db.execute("""SELECT trade_date,deal_type,symbol,client,side,quantity,price,source_url
                  FROM disclosed_deals
                  WHERE trade_date IN (SELECT trade_date FROM disclosed_report_days
                        GROUP BY trade_date ORDER BY trade_date DESC LIMIT ?)
                  ORDER BY trade_date DESC, symbol""",(max(1,min(90,int(days))),)).fetchall()

    def report_dates(self):
        with self.connect() as db:
            return db.execute("""SELECT trade_date,COUNT(DISTINCT deal_type)
                     FROM disclosed_report_days GROUP BY trade_date
                     ORDER BY trade_date DESC LIMIT 25""").fetchall()


def _fetch(kind,day):
    if kind not in ("bulk","block"):raise ValueError("Unknown deal kind")
    params=urlencode(dict(optionType=kind+"_deals",
                          **{"from":day.strftime("%d-%m-%Y"),
                             "to":day.strftime("%d-%m-%Y")},csv="true"))
    url=SOURCE_API+"?"+params
    request=Request(url,headers={
        "User-Agent":"BharatSignalResearch/1.0",
        "Accept":"text/csv,text/plain",
        "Referer":SOURCE_PAGE,
    })
    try:
        with urlopen(request,timeout=12) as response:
            if not response.geturl().startswith("https://www.nseindia.com/"):
                raise ValueError("Unexpected NSE deal report redirect")
            data=response.read(2_000_001)
        if len(data)>2_000_000:raise ValueError("Deal report too large")
        return data,url
    except HTTPError as exc:
        if exc.code in (403,429):
            raise PermissionError("NSE refused automated access (HTTP "+str(exc.code)+")") from exc
        raise ValueError("NSE daily deal report not published or unavailable") from exc
    except (URLError,TimeoutError,OSError) as exc:
        raise ValueError("Official NSE deal source inaccessible") from exc


class FIIStockDeals:
    def __init__(self,root,holiday_provider,fetcher=None):
        root=Path(root)
        self.root=root
        self.store=DealStore(root/"fii_disclosed_deals.sqlite")
        self.holidays=holiday_provider
        self.fetcher=fetcher or _fetch
        self._lock=threading.Lock()
        self._thread=None
        self._attempts=set()
        self._sync=dict(status="NOT FETCHED",checked_at=None)

    def ingest_local_files(self):
        """Optional official NSE CSV downloads. Named bulk_YYYY-MM-DD.csv etc."""
        folder=Path(os.getenv("INSIGHTS_NSE_DEALS_FOLDER") or
                    (self.root/"nse_disclosed_deals"))
        results=[]
        for path in sorted(folder.glob("*.csv"))[:200]:
            match=re.fullmatch(r"(bulk|block)_(\d{4}-\d{2}-\d{2})\.csv",path.name,re.I)
            if not match:continue
            try:
                day=_date(match.group(2));kind=match.group(1).lower()
                if self.store.has_day(kind,day):continue
                raw=path.read_bytes()
                count=self.store.ingest(raw,kind,day,SOURCE_PAGE)
                results.append(dict(day=day.isoformat(),kind=kind,rows=count))
            except (OSError,ValueError):continue
        return results

    def snapshot(self,now=None):
        now=(now or datetime.now(IST)).astimezone(IST)
        registry=_registry(self.root)
        rows=self.store.recent(15)
        buys=[];sells=[];unclassified=0;unknown_examples=[]
        for day,kind,symbol,client,side,qty,price,url in rows:
            identity=_identity(client,registry)
            if not identity["verified"]:
                unclassified+=1
                if len(unknown_examples)<30:
                    unknown_examples.append(dict(trade_date=day,symbol=symbol,
                        client=client,side=side,deal_type=kind,
                        source_url=url,identity='NOT VERIFIED AS FII/FPI'))
                continue
            obj=dict(trade_date=day,symbol=symbol,client=client,side=side,
                 quantity=qty,price=round(price,2),
                 approx_value_crore=round(qty*price/10_000_000,3),
                 deal_type=kind,verification_source=identity["proof"],
                 source_url=url,scope="NSE DISCLOSED BULK/BLOCK DEAL")
            (buys if side=="BUY" else sells).append(obj)
        with self._lock:state=dict(self._sync)
        reports=self.store.report_dates()
        return dict(status=("VERIFIED DISCLOSED FII DEALS" if buys or sells else
                "NO VERIFIED FII CLIENT DEALS IN STORED DISCLOSURES"),
            bought=buys[:100],sold=sells[:100],
            unclassified_disclosed_rows=unclassified,
            unclassified_examples=unknown_examples,
            verified_client_names=len(registry),
            report_dates=[dict(date=d,types=n) for d,n in reports],
            latest_report_date=reports[0][0] if reports else None,
            updated_at=now.isoformat(),refresh=state,
            data_scope="NSE DISCLOSED BULK/BLOCK DEALS ONLY; NOT ALL FII TRADES",
            note="Client identity must exactly match a sourced FPI/FII registry. "
                 "The NSE participant OI reports cannot identify stock-level FII trades. "
                 "Missing entries do not mean FIIs made no trades.")

    def _target(self,now,holidays):
        d=now.date()
        if (now.hour,now.minute)<(18,0):d-=timedelta(days=1)
        for _ in range(15):
            stamp=datetime(d.year,d.month,d.day,10,0,tzinfo=IST)
            if is_market_session(stamp,holidays):return d
            d-=timedelta(days=1)
        return None

    def sync(self,now=None,days=2):
        now=(now or datetime.now(IST)).astimezone(IST)
        holidays=self.holidays()
        if holidays is None:
            return dict(status="BLOCKED — VERIFIED HOLIDAY CALENDAR MISSING")
        imported=self.ingest_local_files()
        target=self._target(now,holidays)
        if target is None:return dict(status="NO VERIFIED TRADING DATE",local_imports=imported)
        saved=[];failed=[]
        scanned=0;d=target
        while scanned<max(1,min(3,int(days))):
            if is_market_session(datetime(d.year,d.month,d.day,10,0,tzinfo=IST),holidays):
                scanned+=1
                for kind in ("bulk","block"):
                    if self.store.has_day(kind,d):continue
                    try:
                        raw,url=self.fetcher(kind,d)
                        count=self.store.ingest(raw,kind,d,url)
                        saved.append(dict(day=d.isoformat(),kind=kind,records=count))
                    except PermissionError as exc:
                        failed.append(str(exc))
                        with self._lock:self._sync=dict(status="NSE ACCESS BLOCKED",
                            checked_at=now.isoformat(),saved=saved,failed=failed)
                        return dict(self._sync)
                    except (ValueError,OSError) as exc:
                        failed.append(d.isoformat()+" "+kind+": "+str(exc)[:85])
            d-=timedelta(days=1)
        out=dict(status="SYNCED — DISCLOSED DEALS ONLY" if saved or imported else
                  "NO NEW DISCLOSED DEALS / REPORTS UNAVAILABLE",
                 checked_at=now.isoformat(),saved=saved,failed=failed,
                 local_imports=imported)
        with self._lock:self._sync=out
        return out

    def start(self,now=None,force=False):
        now=(now or datetime.now(IST)).astimezone(IST)
        if not force:
            if self.holidays() is None:return dict(status="HOLIDAY CALENDAR MISSING")
            if (now.hour,now.minute)<(18,0) or now.hour>=23:
                return dict(status="OUTSIDE EOD DEAL WINDOW")
        key=(now.date().isoformat(),"manual" if force else "auto")
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return dict(status="ALREADY RUNNING")
            if key in self._attempts:return dict(status="ALREADY ATTEMPTED")
            self._attempts.add(key)
            def work():
                try:self.sync(now)
                except Exception:
                    with self._lock:self._sync=dict(status="SOURCE ERROR",
                                      checked_at=now.isoformat())
            self._thread=threading.Thread(target=work,daemon=True,
                                         name="NseFIIDisclosedDeals")
            self._thread.start()
        return dict(status="STARTED")
