"""Official NSE F&O participant snapshots: read-only fetch, validation and trend.

NSE fao_participant_oi/vol are AGGREGATED across instruments and expiries,
not expiry-specific trading records. Cycles mark analysis windows only.
No claim of certainty, actual aggressor flow, or predictive win rate.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import sqlite3
from datetime import date,datetime,timedelta
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

FIELDS=(
    "future_index_long","future_index_short","future_stock_long",
    "future_stock_short","option_index_call_long","option_index_put_long",
    "option_index_call_short","option_index_put_short",
    "option_stock_call_long","option_stock_put_long",
    "option_stock_call_short","option_stock_put_short",
    "total_long_contracts","total_short_contracts")
PARTICIPANTS=("FII","PRO","CLIENT")
ALL_TYPES=("FII","PRO","CLIENT","DII")
SOURCES={
    "oi":"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{day}.csv",
    "vol":"https://archives.nseindia.com/content/nsccl/fao_participant_vol_{day}.csv",
}
TITLE="NSE Participant Positioning"
WEIGHTS={"FII":0.5,"PRO":0.3,"CLIENT":0.2}
VERSION="participant-positioning-v1"


class ParticipantError(ValueError):
    pass


def _norm(x):
    return re.sub(r"[^a-z0-9]","",str(x).strip().lower())


def _participant(x):
    name=_norm(x)
    return {"fii":"FII","pro":"PRO","client":"CLIENT",
            "clients":"CLIENT","dii":"DII"}.get(name)


def parse_csv(data,kind,trade_day):
    """Strict CSV parse. Ignore title/preamble, but never silently remap columns."""
    if kind not in SOURCES:raise ParticipantError("Unsupported report type")
    if not isinstance(data,bytes) or not 80<=len(data)<=131072:
        raise ParticipantError("NSE CSV empty or outside expected size limits")
    try:body=data.decode("utf-8-sig")
    except UnicodeError as exc:raise ParticipantError("NSE CSV is not UTF-8") from exc
    if "<html" in body[:300].lower() or "<!doctype" in body[:300].lower():
        raise ParticipantError("NSE returned HTML, not a participant CSV")
    lines=list(csv.reader(io.StringIO(body)))
    columns=[_norm(x.replace("\t","")) for x in
       ("Client Type","Future Index Long","Future Index Short","Future Stock Long",
        "Future Stock Short","Option Index Call Long","Option Index Put Long",
        "Option Index Call Short","Option Index Put Short","Option Stock Call Long",
        "Option Stock Put Long","Option Stock Call Short","Option Stock Put Short",
        "Total Long Contracts","Total Short Contracts")]
    header=None;offset={}
    for i,line in enumerate(lines[:12]):
        names=[_norm(x) for x in line]
        if all(name in names for name in columns):
            header=i;offset={name:names.index(name) for name in columns};break
    if header is None:raise ParticipantError("NSE participant CSV columns missing")
    # Reject a clear, contradictory 'as on' date in the source title.
    prefix=" ".join(",".join(x) for x in lines[:header])
    m=re.search(r"as\s+on\s+([A-Za-z]{3,9})\s+(\d{1,2})\s*,?\s*(\d{4})",prefix,re.I)
    if m:
        parsed=None
        for pattern in ("%b %d %Y","%B %d %Y"):
            try:parsed=datetime.strptime(" ".join(m.groups()),pattern).date();break
            except ValueError:pass
        if parsed is not None and parsed!=trade_day:
            raise ParticipantError("NSE embedded date differs from requested session")
    result={}
    for line in lines[header+1:]:
        if not line:continue
        who=_participant(line[offset[columns[0]]]) if len(line)>offset[columns[0]] else None
        if who is None:continue
        if who in result:raise ParticipantError("Duplicate participant: "+who)
        values={}
        for key,column in zip(FIELDS,columns[1:]):
            at=offset[column]
            if at>=len(line):raise ParticipantError("Short NSE participant record")
            raw=line[at].strip().replace(",","").replace("\t","")
            if not re.fullmatch(r"\d+(?:\.0+)?",raw):
                raise ParticipantError("Invalid/missing contract counts for "+who)
            number=int(float(raw))
            if number<0 or number>10**12:raise ParticipantError("Impossible contract count")
            values[key]=number
        result[who]=values
    if not all(p in result for p in PARTICIPANTS):
        raise ParticipantError("FII, PRO or CLIENT record missing from "+kind)
    return result


def source_url(kind,trade_day):
    if kind not in SOURCES or not isinstance(trade_day,date):raise ParticipantError("Invalid source")
    return SOURCES[kind].format(day=trade_day.strftime("%d%m%Y"))


def fetch_csv(kind,trade_day,timeout=12):
    url=source_url(kind,trade_day)
    req=Request(url,headers={
        "User-Agent":"BharatSignalResearch/1.0 (read-only NSE public CSV research)",
        "Accept":"text/csv,text/plain,application/octet-stream",
        "Referer":"https://www.nseindia.com/all-reports-derivatives"})
    try:
        with urlopen(req,timeout=timeout) as response:
            final=response.geturl()
            if not final.startswith("https://archives.nseindia.com/content/nsccl/"):
                raise ParticipantError("NSE source redirected outside official archive path")
            data=response.read(131073)
    except (HTTPError,URLError,TimeoutError,OSError) as exc:
        raise ParticipantError("Official NSE "+kind.upper()+" report inaccessible") from exc
    return data


def _ratio(positive,negative):
    total=positive+negative
    return 100*(positive-negative)/total if total>0 else 0.0


def positioning(values):
    fut=_ratio(values["future_index_long"],values["future_index_short"])
    bullish=values["option_index_call_long"]+values["option_index_put_short"]
    bearish=values["option_index_call_short"]+values["option_index_put_long"]
    opt=_ratio(bullish,bearish)
    score=0.6*fut+0.4*opt
    return {"score":round(score,2),"index_futures_score":round(fut,2),
            "index_options_proxy_score":round(opt,2),
            "index_futures_net":values["future_index_long"]-values["future_index_short"],
            "index_options_net_proxy":bullish-bearish}


def direction(score,neutral=8):
    return "UP" if score>neutral else "DOWN" if score< -neutral else "NEUTRAL"


def _date(value):
    if isinstance(value,date) and not isinstance(value,datetime):return value
    return date.fromisoformat(str(value))


class ParticipantStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS participant_reports (
                trade_date TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('oi','vol')),
                participant TEXT NOT NULL,
                values_json TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                PRIMARY KEY(trade_date,kind,participant))""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_participants_date ON participant_reports(trade_date)")
    def _connect(self):
        db=sqlite3.connect(str(self.path),timeout=8)
        db.execute("PRAGMA busy_timeout=8000")
        return db
    def complete(self,trade_day):
        with self._connect() as db:
            cur=db.execute("""SELECT kind,COUNT(*) FROM participant_reports
                WHERE trade_date=? AND participant IN ('FII','PRO','CLIENT')
                GROUP BY kind""",(_date(trade_day).isoformat(),))
            counts=dict(cur.fetchall())
        return counts.get("oi",0)==3 and counts.get("vol",0)==3
    def save(self,trade_day,oi_raw,vol_raw,retrieved_at):
        # Transactional: never persist incomplete/mismatched trading days.
        d=_date(trade_day)
        parsed={"oi":parse_csv(oi_raw,"oi",d),
                "vol":parse_csv(vol_raw,"vol",d)}
        sources={"oi":oi_raw,"vol":vol_raw}
        with self._connect() as db:
            for kind,rows in parsed.items():
                digest=hashlib.sha256(sources[kind]).hexdigest()
                for who,values in rows.items():
                    db.execute("""INSERT INTO participant_reports
                        (trade_date,kind,participant,values_json,source_url,source_hash,retrieved_at)
                        VALUES(?,?,?,?,?,?,?)
                        ON CONFLICT(trade_date,kind,participant)
                        DO UPDATE SET values_json=excluded.values_json,
                        source_url=excluded.source_url,source_hash=excluded.source_hash,
                        retrieved_at=excluded.retrieved_at""",
                        (d.isoformat(),kind,who,json.dumps(values,sort_keys=True),
                         source_url(kind,d),digest,str(retrieved_at)))
        return dict(trade_date=d.isoformat(),saved=True,participants=list(parsed["oi"]))
    def history(self,limit=120):
        with self._connect() as db:
            rows=db.execute("""SELECT trade_date,kind,participant,values_json
                FROM participant_reports WHERE trade_date IN (
                 SELECT trade_date FROM participant_reports
                 GROUP BY trade_date HAVING
                 SUM(CASE WHEN kind='oi' AND participant IN ('FII','PRO','CLIENT') THEN 1 ELSE 0 END)=3
                 AND SUM(CASE WHEN kind='vol' AND participant IN ('FII','PRO','CLIENT') THEN 1 ELSE 0 END)=3
                 ORDER BY trade_date DESC LIMIT ?)
                 ORDER BY trade_date ASC""",(max(1,min(500,int(limit))),)).fetchall()
        result={}
        for day,kind,participant,values in rows:
            result.setdefault(day,{}).setdefault(kind,{})[participant]=json.loads(values)
        return result
    def summary(self,asof=None,expiry_dates=()):
        return summarize(self.history(),asof=asof,expiry_dates=expiry_dates)


def summarize(history,asof=None,expiry_dates=()):
    """Daily EOD OI snapshot, day-on-day Δ and verified-window Δ.

    Expiry dates define WINDOW boundaries only. NSE reports do not specify
    positions by expiry, and daily OI levels MUST NOT be summed.
    """
    today=_date(asof) if asof is not None else date.today()
    complete=sorted(d for d,v in history.items() if d<=today.isoformat()
       and all(x in v.get(kind,{}) for kind in ("oi","vol") for x in PARTICIPANTS))
    empty=dict(version=VERSION,status="UNAVAILABLE — NSE REPORTS NOT LOADED",
       trade_date=None,expiry_date=None,expiry_scope="AGGREGATE ACROSS ALL EXPIRIES",
       cycle_label="NOT VERIFIED",overall_direction="UNAVAILABLE",
       overall_score=None,all_aligned=False,participants={},
       history_days=0,source="NSE F&O participant OI and trading-volume CSV",
       note="OI is an end-of-day snapshot; data unavailable is NOT a neutral position.")
    if not complete:return empty
    current=complete[-1]
    exp=[]
    for d in expiry_dates:
        try:exp.append(_date(d).isoformat())
        except (TypeError,ValueError):continue
    future=sorted({e for e in exp if e>=current})
    expiry=future[0] if future else None
    prior_exp=max((x for x in exp if x<current),default=None)
    if expiry is not None:
        cycle_days=[d for d in complete if prior_exp is None or d>prior_exp]
    else:
        cycle_days=[]
    baseline=cycle_days[0] if cycle_days else None
    previous=complete[-2] if len(complete)>1 else None
    results={}
    for who in PARTICIPANTS:
        spot=positioning(history[current]["oi"][who])
        vscore=positioning(history[current]["vol"][who])
        prev=positioning(history[previous]["oi"][who]) if previous else None
        baseline_score=positioning(history[baseline]["oi"][who]) if baseline else None
        score=spot["score"]
        results[who]=dict(
            label={"FII":"FII","PRO":"PRO","CLIENT":"Retail / Client"}[who],
            direction=direction(score),score=score,
            daily_score_change=round(score-prev["score"],2) if prev else None,
            index_futures_net=spot["index_futures_net"],
            index_futures_net_change=(
                spot["index_futures_net"]-prev["index_futures_net"] if prev else None),
            index_options_net_proxy=spot["index_options_net_proxy"],
            futures_score=spot["index_futures_score"],
            options_score=spot["index_options_proxy_score"],
            volume_participation_score=vscore["score"],
            volume_alignment=("ALIGNED" if direction(score)!="NEUTRAL"
                 and direction(vscore["score"])==direction(score)
                 else "MIXED / INCONCLUSIVE"),
            cycle_futures_net_change=(spot["index_futures_net"]-
                baseline_score["index_futures_net"] if baseline_score else None),
            cycle_score_change=round(score-baseline_score["score"],2) if baseline_score else None)
    score=round(sum(results[k]["score"]*WEIGHTS[k] for k in PARTICIPANTS),2)
    directions=[results[k]["direction"] for k in PARTICIPANTS]
    aligned=len(set(directions))==1 and directions[0]!="NEUTRAL"
    latest_day=_date(current)
    age=(today-latest_day).days
    status=("EOD POSITIONING — STALE" if age>3 else
            "EOD POSITIONING — HISTORICAL / NOT LIVE")
    return dict(version=VERSION,status=status,trade_date=current,
        expiry_date=expiry,expiry_scope="AGGREGATE ALL INDEX EXPIRIES (NOT CONTRACT-EXPIRY POSITIONS)",
        cycle_label=("OBSERVATION WINDOW TO "+expiry if expiry else "EXPIRY WINDOW UNVERIFIED"),
        cycle_start=baseline,cycle_sessions=len(cycle_days),
        overall_score=score,overall_direction=direction(score),
        all_aligned=aligned,participant_weights=WEIGHTS,
        participants=results,history_days=len(complete),
        stale_days=age,source="Official NSE post-close participant OI + trading volume CSV",
        note=("OI is an end-of-day snapshot, not additive daily flow. Cycle changes compare "
              "the current OI with its first observed report. Contracts include ALL index "
              "expiries and index products. VOL is participation, NOT aggressor buy/sell flow. "
              "FII weight is a configurable interpretation, not proof market must follow FIIs."))
