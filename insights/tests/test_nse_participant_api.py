"""Dashboard participant NSE routes never place orders or fetch by reading."""
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock
from insights.api import create_app
from insights.service import InsightsService
from insights.config import IST


class MinimalBroker:
    def configured(self):return True


class ParticipantAPITests(unittest.TestCase):
    def test_empty_read_only_state_and_no_implicit_network(self):
        with tempfile.TemporaryDirectory() as directory:
            svc=InsightsService(MinimalBroker(),directory)
            svc.participant_manager.fetcher=Mock()
            c=create_app(svc).test_client()
            res=c.get('/api/v1/market-insights/participant-positioning')
            self.assertEqual(res.status_code,200)
            self.assertEqual(res.json['overall_direction'],'UNAVAILABLE')
            self.assertEqual(res.json['participants'],{})
            svc.participant_manager.fetcher.assert_not_called()
            self.assertFalse(c.get('/api/v1/health').json['orders_enabled'])
    def test_explicit_refresh_returns_start_status_without_order_call(self):
        with tempfile.TemporaryDirectory() as directory:
            svc=InsightsService(MinimalBroker(),directory)
            svc.participant_manager.start=Mock(return_value={'status':'STARTED'})
            c=create_app(svc).test_client()
            r=c.post('/api/v1/market-insights/participant-positioning/refresh')
            self.assertEqual(r.status_code,202)
            self.assertEqual(r.json['status'],'STARTED')
            svc.participant_manager.start.assert_called_once()
            self.assertFalse(svc.health()['orders_enabled'])


if __name__=='__main__':unittest.main()
