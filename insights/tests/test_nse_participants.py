"""Offline NSE CSV/OI/VOL ingestion, positioning and cycle regression tests."""
import csv
import io
import tempfile
import unittest
from datetime import date,datetime
from pathlib import Path
from unittest.mock import Mock
from insights.config import IST
from insights import nse_participants as nse
from insights.participant_refresh import ParticipantRefresh


HEADER=[
    "Client Type","Future Index Long","Future Index Short",
    "Future Stock Long","Future Stock Short","Option Index Call Long",
    "Option Index Put Long","Option Index Call Short","Option Index Put Short",
    "Option Stock Call Long","Option Stock Put Long","Option Stock Call Short",
    "Option Stock Put Short","Total Long Contracts","Total Short Contracts"]


def make_csv(day,kind="oi",state=None):
    state=state or {}
    buf=io.StringIO()
    buf.write("Participant wise "+kind.upper()+
              " in Equity Derivatives as on "+day.strftime("%b %d,%Y")+"\n")
    w=csv.writer(buf)
    w.writerow(HEADER)
    for who in ("Client","DII","FII","Pro"):
        spec=state.get(who,{})
        row=[who]
        for name in nse.FIELDS:
            val=spec.get(name,200)
            row.append(val)
        w.writerow(row)
    w.writerow(["TOTAL"]+[800]*len(nse.FIELDS))
    return buf.getvalue().encode("utf-8")


def state(fii="up",pro="down",client="up",delta=0):
    def one(direction):
        return dict(future_index_long=(250+delta if direction=="up" else 80),
                    future_index_short=(80 if direction=="up" else 250+delta),
                    option_index_call_long=(300 if direction=="up" else 75),
                    option_index_call_short=(75 if direction=="up" else 300),
                    option_index_put_long=(75 if direction=="up" else 300),
                    option_index_put_short=(300 if direction=="up" else 75))
    return {"FII":one(fii),"Pro":one(pro),"Client":one(client)}


class NSEParticipantTests(unittest.TestCase):
    def setUp(self):
        self.day=date(2026,11,12)
        self.now=datetime(2026,11,13,20,0,tzinfo=IST)
    def test_exact_archive_url_and_field_map(self):
        self.assertEqual(nse.source_url("oi",self.day),
         "https://archives.nseindia.com/content/nsccl/fao_participant_oi_12112026.csv")
        rows=nse.parse_csv(make_csv(self.day,"oi",state()),"oi",self.day)
        self.assertEqual(set(rows),{"FII","PRO","CLIENT","DII"})
        self.assertEqual(rows["FII"]["future_index_long"],250)
    def test_bad_html_header_missing_participant_or_date_mismatch_fail_closed(self):
        with self.assertRaises(nse.ParticipantError):
            nse.parse_csv(b"<html>Access Denied</html>","oi",self.day)
        with self.assertRaises(nse.ParticipantError):
            nse.parse_csv(make_csv(self.day),"oi",date(2026,11,13))
        csv_data=make_csv(self.day).replace(b"FII,",b"UNIDENTIFIED,")
        with self.assertRaises(nse.ParticipantError):
            nse.parse_csv(csv_data,"oi",self.day)
    def test_atomic_oi_and_vol_and_restart_persistence(self):
        with tempfile.TemporaryDirectory() as p:
            path=Path(p)/"positions.sqlite"
            store=nse.ParticipantStore(path)
            raw=make_csv(self.day,"oi",state())
            with self.assertRaises(nse.ParticipantError):
                store.save(self.day,raw,b"not a valid vol file",self.now.isoformat())
            self.assertFalse(store.complete(self.day))
            store.save(self.day,raw,make_csv(self.day,"vol",state()),self.now.isoformat())
            again=nse.ParticipantStore(path)
            self.assertTrue(again.complete(self.day))
            again.save(self.day,raw,make_csv(self.day,"vol",state()),self.now.isoformat())
            self.assertEqual(len(again.history()),1)
    def test_bias_mixed_alignment_and_real_net_delta(self):
        previous=date(2026,11,11)
        with tempfile.TemporaryDirectory() as p:
            store=nse.ParticipantStore(Path(p)/"positions.sqlite")
            for day,shift in ((previous,0),(self.day,30)):
                raw=make_csv(day,"oi",state(delta=shift))
                store.save(day,raw,make_csv(day,"vol",state()),self.now.isoformat())
            x=store.summary(self.now,expiry_dates=["2026-11-10","2026-11-17"])
            self.assertEqual(x["participants"]["FII"]["direction"],"UP")
            self.assertEqual(x["participants"]["PRO"]["direction"],"DOWN")
            self.assertFalse(x["all_aligned"])
            self.assertEqual(x["participants"]["FII"]["index_futures_net_change"],30)
            self.assertEqual(x["participants"]["FII"]["cycle_futures_net_change"],30)
            self.assertEqual(x["expiry_date"],"2026-11-17")
            self.assertEqual(x["cycle_start"],"2026-11-11")
            self.assertEqual(x["cycle_sessions"],2)
            self.assertIn("AGGREGATE",x["expiry_scope"])
    def test_still_negative_net_can_improve_day_on_day(self):
        prior=state("down","down","down",delta=20)
        current=state("down","down","down",delta=0)
        with tempfile.TemporaryDirectory() as p:
            store=nse.ParticipantStore(Path(p)/"positions.sqlite")
            for day,st in ((date(2026,11,11),prior),(self.day,current)):
                store.save(day,make_csv(day,"oi",st),
                         make_csv(day,"vol",st),self.now.isoformat())
            x=store.summary(self.now,expiry_dates=["2026-11-17"])
            self.assertEqual(x["participants"]["FII"]["direction"],"DOWN")
            self.assertGreater(x["participants"]["FII"]["index_futures_net_change"],0)
            self.assertTrue(x["all_aligned"])
    def test_unverified_expiry_does_not_invent_cycle(self):
        history={"2026-11-12":dict(oi=nse.parse_csv(make_csv(self.day),"oi",self.day),
              vol=nse.parse_csv(make_csv(self.day,"vol"),"vol",self.day))}
        result=nse.summarize(history,asof=self.now)
        self.assertIsNone(result["expiry_date"])
        self.assertIsNone(result["participants"]["FII"]["cycle_futures_net_change"])
        self.assertIn("UNVERIFIED",result["cycle_label"])
    def test_no_market_data_stays_unavailable_not_neutral(self):
        x=nse.summarize({},asof=self.now)
        self.assertEqual(x["overall_direction"],"UNAVAILABLE")
        self.assertEqual(x["participants"],{})
    def test_sync_bounded_and_skip_persisted_reports(self):
        with tempfile.TemporaryDirectory() as p:
            calls=[]
            def get(kind,day):
                calls.append((kind,day.isoformat()))
                return make_csv(day,kind,state())
            worker=ParticipantRefresh(Path(p),lambda:set(),
                                      expiry_provider=lambda:["2026-11-17"],
                                      fetcher=get)
            run=worker.sync(self.now,max_dates=2)
            self.assertEqual(run["saved_count"],2)
            self.assertTrue(worker.store.complete(date(2026,11,13)))
            self.assertTrue(worker.store.complete(date(2026,11,12)))
            worker.sync(self.now,max_dates=1)
            self.assertEqual(len(calls),6)
            self.assertEqual(worker.summary(self.now)["expiry_date"],"2026-11-17")
    def test_unavailable_source_preserves_previous_records(self):
        with tempfile.TemporaryDirectory() as p:
            worker=ParticipantRefresh(Path(p),lambda:set(),
                                      fetcher=lambda kind,day: (_ for _ in ()).throw(
                                          nse.ParticipantError("Report not published")))
            worker.store.save(self.day,make_csv(self.day,"oi",state()),
                    make_csv(self.day,"vol",state()),self.now.isoformat())
            failure=worker.sync(self.now,max_dates=1)
            self.assertEqual(failure["status"],"PARTIAL — TARGET NSE REPORT NOT AVAILABLE")
            self.assertTrue(worker.store.complete(self.day))
            self.assertEqual(worker.summary(self.now)["trade_date"],self.day.isoformat())
    def test_no_holiday_calendar_fails_closed_without_network(self):
        with tempfile.TemporaryDirectory() as p:
            fetcher=Mock()
            worker=ParticipantRefresh(Path(p),lambda:None,fetcher=fetcher)
            self.assertIn("BLOCKED",worker.sync(self.now)["status"])
            fetcher.assert_not_called()
    def test_auto_time_windows_do_not_start_market_hours_downloads(self):
        with tempfile.TemporaryDirectory() as p:
            worker=ParticipantRefresh(Path(p),lambda:set(),
                 fetcher=lambda kind,day:make_csv(day,kind,state()))
            morning=datetime(2026,11,13,8,0,tzinfo=IST)
            self.assertEqual(worker.start(datetime(2026,11,13,10,0,tzinfo=IST))["status"],"NOT SCHEDULED")
            self.assertEqual(worker.start(morning)["status"],"STARTED")
            worker._thread.join(timeout=5)
            self.assertFalse(worker._thread.is_alive())
            self.assertTrue(worker.store.complete(self.day))


if __name__=="__main__":unittest.main()
