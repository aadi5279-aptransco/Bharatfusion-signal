import unittest
from datetime import datetime, timedelta
from copy import deepcopy
from insights.config import IST
from insights.alpha.readiness import assess

def fixture(end=None, days=1):
    end = end or datetime(2026,11,24,18,tzinfo=IST)
    opening = datetime(2026,11,24,9,15,tzinfo=IST)
    return {'manifest': {'timeframe':'5m','as_of':end.isoformat(),'requested_days':days,'blockers':[]},
            'rows':[{'time':(opening+timedelta(minutes=5*i)).isoformat()} for i in range(75)],
            'quarantine':[]}

class ReadinessTests(unittest.TestCase):
    def test_complete_grid_never_approves_training(self):
        r=assess(fixture())
        self.assertEqual(r['missing_in_observed_sessions'],0)
        self.assertEqual(r['status'],'PROVENANCE_REVIEW')
        self.assertFalse(r['training_ready'])

    def test_1510_last_bar_exposes_three_missing_closing_bars(self):
        p=fixture();p['rows']=p['rows'][:-3]
        r=assess(p);s=r['sessions'][-1]
        self.assertEqual(r['missing_in_observed_sessions'],3)
        self.assertEqual(s['missing_after_last'],3)
        self.assertIn('15:15:00',s['first_missing'])

    def test_internal_and_opening_gaps(self):
        p=fixture();p['rows']=[r for i,r in enumerate(p['rows']) if i not in (0,1,20)]
        s=assess(p)['sessions'][-1]
        self.assertEqual(s['missing_regular_bars'],3)
        self.assertEqual(s['missing_before_first'],2)

    def test_partial_capture_window_does_not_require_earlier_bars(self):
        p=fixture(datetime(2026,11,24,10,12,tzinfo=IST))
        p['rows']=p['rows'][:11]
        s=assess(p)['sessions'][-1]
        self.assertEqual(s['expected_regular_bars'],11)
        self.assertEqual(s['missing_regular_bars'],0)

    def test_whole_missing_day_is_calendar_unverified(self):
        r=assess(fixture(days=4))
        self.assertIn('2026-11-23',r['weekdays_without_rows'])
        self.assertNotIn('2026-11-22',r['weekdays_without_rows'])
        self.assertEqual(r['missing_in_observed_sessions'],0)

    def test_non_mutating_deterministic_and_quarantine(self):
        p=fixture();p['quarantine']=[{'reason':'ZERO_VOLUME'}]
        before=deepcopy(p);r=assess(p)
        self.assertEqual(p,before);self.assertEqual(r,assess(p))
        self.assertEqual(r['status'],'COVERAGE_REVIEW')

    def test_invalid_contract_rejected(self):
        for key,value in [('timeframe','daily'),('as_of','2026-11-24T18:00:00'),('requested_days',0)]:
            p=fixture();p['manifest'][key]=value
            with self.assertRaises(ValueError):assess(p)
