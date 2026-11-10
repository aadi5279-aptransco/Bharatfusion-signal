"""Regression tests: Dhan SDK may nest success envelopes in option responses."""
import unittest
from unittest.mock import Mock, patch
from insights.brokers.dhan import DhanReadOnly, BrokerUnavailable


class DhanOptionPayloadTests(unittest.TestCase):
    def setUp(self):
        self.broker = DhanReadOnly('test-client', 'test-token')
        self.item = {'id': '13', 'segment': 'IDX_I', 'symbol': 'NIFTY'}
        self.expiry = '2026-11-17'

    def _sdk(self, **responses):
        sdk = Mock()
        for name, response in responses.items():
            getattr(sdk, name).return_value = response
        return patch.object(self.broker, '_sdk', return_value=sdk), sdk

    def test_expiry_list_double_wrapped_success(self):
        raw = {'status':'success', 'remarks':'',
               'data':{'status':'success', 'data':['2026-11-17','2026-11-23']}}
        manager, sdk = self._sdk(expiry_list=raw)
        with manager:
            self.assertEqual(self.broker.expiry_list(self.item), ['2026-11-17','2026-11-23'])
        sdk.expiry_list.assert_called_once_with(13,'IDX_I')

    def test_expiry_list_flat_success(self):
        manager, _ = self._sdk(expiry_list={'status':'success', 'data':['2026-11-17']})
        with manager:
            self.assertEqual(self.broker.expiry_list(self.item), ['2026-11-17'])

    def test_expiry_list_nested_failure_is_not_accepted(self):
        manager, _ = self._sdk(expiry_list={'status':'success', 'data':{'status':'failure', 'data':[]}})
        with manager, self.assertRaises(BrokerUnavailable):
            self.broker.expiry_list(self.item)

    def test_option_chain_double_wrapped_success(self):
        chain = {'last_price': 26000, 'oc':{'26000': {'ce':{'oi':1},'pe':{'oi':2}}}}
        raw = {'status':'success','data':{'status':'success','data':chain}}
        manager, sdk = self._sdk(option_chain=raw)
        with manager:
            self.assertEqual(self.broker.option_chain(self.item, self.expiry), chain)
        sdk.option_chain.assert_called_once_with(13,'IDX_I',self.expiry)

    def test_option_chain_flat_success(self):
        chain = {'last_price': 26000, 'oc':{'26000': {'ce':{'oi':1},'pe':{'oi':2}}}}
        manager, _ = self._sdk(option_chain={'status':'success', 'data':chain})
        with manager:
            self.assertEqual(self.broker.option_chain(self.item, self.expiry), chain)

    def test_option_chain_invalid_payload_rejected(self):
        manager, _ = self._sdk(option_chain={'status':'success', 'data':{'data':{'status':'success'}}})
        with manager, self.assertRaises(BrokerUnavailable):
            self.broker.option_chain(self.item, self.expiry)


if __name__=='__main__': unittest.main()
