"""Offline contract mapping and daily payload regressions; no live credentials."""
import unittest
from unittest.mock import Mock
from datetime import datetime
import pandas as pd
from insights.config import IST
from insights.data_layer.contracts import resolve_index_future
from insights.data_layer.client import Client

NOW=datetime(2026,11,23,10,0,tzinfo=IST)
ITEM=dict(id='25',symbol='BANKNIFTY',segment='IDX_I',instrument='INDEX')
def row(**changes):
    result=dict(EXCH_ID='NSE',INSTRUMENT='FUTIDX',SECURITY_ID='12345',
        UNDERLYING_SECURITY_ID='25',UNDERLYING_SYMBOL='BANKNIFTY',
        SM_EXPIRY_DATE='2026-11-24',SYMBOL_NAME='BANKNIFTY-NOV-FUT',TICK_SIZE='0.05')
    result.update(changes)
    return result
def resolve(*rows):
    return resolve_index_future(pd.DataFrame(rows),ITEM,NOW)

class ContractFixTests(unittest.TestCase):
    def test_id_mapping(self):
        self.assertEqual(resolve(row())['mapping_method'],'UNDERLYING_SECURITY_ID')
    def test_missing_id_uses_exact_underlying_alias(self):
        result=resolve(row(UNDERLYING_SECURITY_ID='0',UNDERLYING_SYMBOL='NIFTY BANK'))
        self.assertEqual(result['id'],'12345')
        self.assertEqual(result['mapping_method'],'EXACT_UNDERLYING_SYMBOL')
    def test_conflicting_id_is_not_overridden(self):
        self.assertIsNone(resolve(row(UNDERLYING_SECURITY_ID='13')))
    def test_contract_display_name_is_never_a_fallback(self):
        self.assertIsNone(resolve(row(UNDERLYING_SECURITY_ID='',UNDERLYING_SYMBOL='')))
    def test_conflicting_symbol_and_wrong_exchange_rejected(self):
        self.assertIsNone(resolve(row(UNDERLYING_SYMBOL='NIFTY')))
        self.assertIsNone(resolve(row(EXCH_ID='BSE')))
    def test_expired_excluded_and_expiry_day_retained(self):
        result=resolve(row(SM_EXPIRY_DATE='2026-11-22'),
            row(SECURITY_ID='54321',SM_EXPIRY_DATE='2026-11-23'))
        self.assertEqual(result['id'],'54321')
    def test_ambiguous_same_expiry_rejected(self):
        self.assertIsNone(resolve(row(),row(SECURITY_ID='54321')))
    def test_decimal_id_normalization(self):
        self.assertEqual(resolve(row(UNDERLYING_SECURITY_ID='25.0'))['id'],'12345')
    def test_option_payload_omits_expiry_code(self):
        client=Client.__new__(Client);client.history=Mock()
        client.historical_daily_data('123','NSE_FNO','OPTIDX','2026-11-01','2026-11-23',oi=True)
        payload=client.history.fetch.call_args.args[1]
        self.assertNotIn('expiryCode',payload)
        self.assertTrue(payload['oi'])
        self.assertEqual(payload['securityId'],'123')
    def test_future_payload_preserves_expiry_code(self):
        client=Client.__new__(Client);client.history=Mock()
        client.historical_daily_data('123','NSE_FNO','FUTIDX','2026-11-01','2026-11-23',expiry_code=1)
        self.assertEqual(client.history.fetch.call_args.args[1]['expiryCode'],1)

if __name__=='__main__':
    unittest.main()
