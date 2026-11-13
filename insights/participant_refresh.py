"""Optional NSE participant report refresh in a separate read-only worker.

The main Dhan scanner must never block waiting on NSE archive network.
Auto attempts at 08:00 for previous session and 18:00/19:30 for today's
published EOD reports, with bounded history backfill and no request floods.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime,date,timedelta

from insights.config import IST,is_market_session
from insights.nse_participants import ParticipantStore,ParticipantError,NSEAccessDenied,fetch_csv

VERSION="participant-fetch-v1"


class ParticipantRefresh:
    def __init__(self,root,holiday_provider,expiry_provider=None,fetcher=None):
        self.store=ParticipantStore(root / "participant_positions.sqlite")
        self.holiday_provider=holiday_provider
        self.expiry_provider=expiry_provider
        self.fetcher=fetcher or fetch_csv
        self._lock=threading.Lock()
        self._thread=None
        self._attempts=set()
        self._last=dict(status="IDLE — NOT YET DOWNLOADED",checked_at=None,
                        saved_count=0,failed_dates=[])
        self.expiry_path=root / "participant_expiry_calendar.json"

    def expiry_dates(self,allow_live=False):
        """Use verified Dhan expiry dates plus durable dates from prior refreshes.

        A verified expiry date labels an observation window. The source
        still combines all index products and all expiries.
        """
        dates=set()
        try:
            obj=json.loads(self.expiry_path.read_text("utf-8"))
            for item in obj.get("index_expiry_dates",[]):
                try:dates.add(date.fromisoformat(item).isoformat())
                except (ValueError,TypeError):pass
        except (OSError,ValueError,TypeError,AttributeError):pass
        if allow_live and callable(self.expiry_provider):
            try:
                for item in self.expiry_provider():
                    try:dates.add(date.fromisoformat(item).isoformat())
                    except (ValueError,TypeError):pass
            except (OSError,ValueError,TypeError,AttributeError):pass
            if dates:
                # Store only official expiry dates already retrieved and/or
                # explicitly reviewed by the user; never guess a calendar.
                try:
                    temp=self.expiry_path.with_suffix(".json.tmp")
                    temp.write_text(json.dumps(dict(index_expiry_dates=sorted(dates)),
                                             indent=2),encoding="utf-8")
                    temp.replace(self.expiry_path)
                except OSError:pass
        return sorted(dates)

    def summary(self,now=None):
        t=(now or datetime.now(IST)).astimezone(IST)
        data=self.store.summary(t,expiry_dates=self.expiry_dates())
        with self._lock:state=dict(self._last)
        data["refresh"]=state
        return data

    def _trading(self,day,calendar):
        now=datetime.combine(day,datetime.min.time(),IST).replace(hour=10)
        return is_market_session(now,calendar)

    def target_day(self,now,calendar):
        """Latest POSSIBLY published report; don't use unfinished session."""
        t=now.astimezone(IST)
        day=t.date()
        if (t.hour,t.minute)<(18,0):
            day-=timedelta(days=1)
        for _ in range(18):
            if self._trading(day,calendar):return day
            day-=timedelta(days=1)
        return None

    def sync(self,now=None,max_dates=6):
        t=(now or datetime.now(IST)).astimezone(IST)
        calendar=self.holiday_provider()
        if calendar is None:
            return dict(status="BLOCKED — HOLIDAY CALENDAR NOT CONFIGURED",
                        checked_at=t.isoformat(),saved_count=0,failed_dates=[])
        target=self.target_day(t,calendar)
        if target is None:
            return dict(status="BLOCKED — NO VERIFIED TRADING DATE",
                        checked_at=t.isoformat(),saved_count=0,failed_dates=[])
        limit=max(1,min(8,int(max_dates)))
        missing=[]
        # Newest-first; backfill most recent ~5 weeks with bounded requests.
        for age in range(36):
            day=target-timedelta(days=age)
            if self._trading(day,calendar) and not self.store.complete(day):
                missing.append(day)
            if len(missing)>=limit:break
        saved=[];failed=[]
        for day in missing:
            try:
                oi=self.fetcher("oi",day)
                vol=self.fetcher("vol",day)
                self.store.save(day,oi,vol,t.isoformat())
                saved.append(day.isoformat())
            except NSEAccessDenied as exc:
                failed.append(dict(day=day.isoformat(),reason=str(exc)[:105]))
                break
            except (ParticipantError,OSError,ValueError,TimeoutError) as exc:
                failed.append(dict(day=day.isoformat(),reason=str(exc)[:105]))
        # When there were no missing sessions the latest already-persisted
        # data remains available. No deleting when archive is offline.
        ready=self.store.complete(target)
        outcome=dict(status=("READY — NSE EOD FILES STORED" if ready else
                             "PARTIAL — TARGET NSE REPORT NOT AVAILABLE"),
                     checked_at=t.isoformat(),target_day=target.isoformat(),
                     saved_count=len(saved),saved_dates=saved,failed_dates=failed,
                     data_scope="EOD participant totals across all expiries")
        self.expiry_dates(allow_live=True)
        with self._lock:self._last=outcome
        return outcome

    def start(self,now=None,force=False):
        now=(now or datetime.now(IST)).astimezone(IST)
        if not force:
            calendar=self.holiday_provider()
            if calendar is None:return dict(status="BLOCKED — CALENDAR UNAVAILABLE")
            if not self._trading(now.date(),calendar):return dict(status="NOT A TRADING DAY")
            clock=(now.hour,now.minute)
            slot=("morning" if (8,0)<=clock<(9,15) else
                  "evening1" if (18,0)<=clock<(19,30) else
                  "evening2" if (19,30)<=clock<=(23,59) else None)
            if not slot:return dict(status="NOT SCHEDULED")
            key=(now.date().isoformat(),slot)
        else:key=(now.date().isoformat(),"manual",now.hour)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return dict(status="REFRESH ALREADY RUNNING")
            if key in self._attempts:
                return dict(status="ALREADY CHECKED IN THIS WINDOW")
            self._attempts.add(key)
            self._last=dict(status="RUNNING — NSE ARCHIVE RETRIEVAL",
                            checked_at=now.isoformat(),saved_count=0,failed_dates=[])
            def job():
                try:self.sync(now)
                except Exception:
                    # Never leak request headers or credentials to the UI.
                    with self._lock:
                        self._last=dict(status="FAILED — NSE INGEST CHECK LOGS",
                          checked_at=now.isoformat(),saved_count=0,failed_dates=[])
            self._thread=threading.Thread(target=job,name="NseParticipantEod",
                                          daemon=True)
            self._thread.start()
            return dict(status="STARTED")
