import unittest
import numpy as np
import pandas as pd
from insights.dashboard_trend import dashboard_trend
from insights.indicators import index_bias
from insights.tests.test_market_insights import history


class DashboardTrendTests(unittest.TestCase):
    def test_symmetric_direction_and_full_weight_budget(self):
        for direction in (1, -1):
            result = dashboard_trend(history(bias=direction))
            self.assertEqual(result['bias'], 'Uptrend' if direction == 1 else 'Downtrend')
            self.assertEqual(sum(c['maximum'] for c in result['components']), 100)
            self.assertEqual(result['score'], sum(c['points'] for c in result['components']))
            self.assertLessEqual(abs(result['score']), 100)
        self.assertEqual(dashboard_trend(history())['score'], -dashboard_trend(history(bias=-1))['score'])

    def test_volume_independent_and_same_rules_for_all_indices(self):
        frame = history(); expected = dashboard_trend(frame)
        frame['volume'] = 0
        self.assertEqual(expected, dashboard_trend(frame))
        for symbol in ('NIFTY', 'BANKNIFTY', 'SENSEX', 'FINNIFTY'):
            legacy = index_bias(frame, symbol)
            dashboard_trend(frame)
            self.assertEqual(legacy, index_bias(frame, symbol))

    def test_flat_gap_up_does_not_force_uptrend(self):
        frame = history()
        # Latest session is +80 from prior close but has traded flat for 75 bars.
        values = np.r_[np.full(245, 20000.), np.full(75, 20080.)]
        for col in ('open', 'close'): frame[col] = values
        frame['high'] = values + 1; frame['low'] = values - 1
        self.assertGreater(frame.close.iloc[-1]-frame.close.iloc[244], 0)
        self.assertEqual(dashboard_trend(frame)['bias'], 'Sideways')

    def test_fully_flat_neutral(self):
        frame = history()
        for col in ('open', 'high', 'low', 'close'): frame[col] = 20000.
        self.assertEqual(dashboard_trend(frame)['score'], 0)

    def test_unavailable_invalid_or_short_history(self):
        self.assertIsNone(dashboard_trend(history(20))['score'])
        frame = history(); frame.iloc[-1, frame.columns.get_loc('high')] = float('inf')
        self.assertIsNone(dashboard_trend(frame)['score'])

    def test_price_component_survives_mixed_ema_alignment(self):
        frame = history(bias=-1)
        for i in range(1, 9):
            value = 81 + i * .5
            frame.iloc[-9+i] = [value-.1, value, value+.1, value-.2, 2000]
        result = dashboard_trend(frame)
        self.assertEqual(result['components'][0]['points'], 20)
        self.assertEqual(result['components'][3]['points'], 20)

class DashboardIntegrationTests(unittest.TestCase):
    def test_utc_completed_candles_and_each_index_snapshot(self):
        import tempfile
        from unittest.mock import patch
        from insights.service import InsightsService
        from insights.tests.test_service import FakeBroker
        now = pd.Timestamp('2026-11-16 10:00', tz='Asia/Kolkata')
        frame = history()
        frame.index = pd.date_range(end=now, periods=len(frame), freq='5min').tz_convert('UTC')
        class Broker(FakeBroker):
            def instruments(self):
                return [dict(kind='index', symbol=s) for s in ('NIFTY', 'SENSEX', 'BANKNIFTY')]
            def history(self, item, now, **kwargs):
                return frame if item['symbol'] != 'SENSEX' else frame.iloc[:-5]
        with tempfile.TemporaryDirectory() as root, patch('insights.service.is_market_session', return_value=True):
            result = InsightsService(Broker(), root).dashboard(now)
        self.assertEqual(len(result['indices']), 3)
        for row in result['indices']:
            self.assertIn('trend', row)
            self.assertIn('session_points', row)
            self.assertTrue(row['asof'].endswith('+05:30'))
            self.assertLess(pd.Timestamp(row['asof']), now)
            self.assertEqual(row['not_live'], row['symbol'] == 'SENSEX')
        original = frame.iloc[:-1].copy(); original.index = original.index.tz_convert('Asia/Kolkata')
        row = result['indices'][0]
        self.assertEqual(row['score'], index_bias(original, 'NIFTY')['score'])
        self.assertEqual(row['trend'], dashboard_trend(original))

if __name__ == '__main__': unittest.main()
