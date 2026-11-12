"""Ensure NIFTY 18:15 anomaly cannot contaminate cash-session Fib/SMC."""
import unittest
import pandas as pd
from insights.brokers.dhan import _regular_cash_session_bars
from insights.config import IST
from insights.strategies import fib_smc


def cash_frame():
    idx=pd.date_range('2026-11-12 09:15',periods=75,freq='5min',tz=IST)
    extra=pd.DatetimeIndex(['2026-11-12T18:15:00+05:30'])
    index=idx.append(extra)
    return pd.DataFrame({
        'open':[100.]*75+[999.], 'high':[101.]*75+[1000.],
        'low':[99.]*75+[998.], 'close':[100.]*75+[999.],
        'volume':[1000.]*75+[0.]}, index=index)


class SpotTradingHoursTests(unittest.TestCase):
    def test_index_excludes_1815_but_retains_75_valid_5m_candles(self):
        f=_regular_cash_session_bars(cash_frame(),
            {'segment':'IDX_I','kind':'index','symbol':'NIFTY'},5)
        self.assertEqual(len(f),75)
        self.assertEqual(f.index[0].strftime('%H:%M'),'09:15')
        self.assertEqual(f.index[-1].strftime('%H:%M'),'15:25')
        self.assertEqual(f.attrs['out_of_session_discarded'],1)

    def test_cash_equity_uses_same_regular_session_window(self):
        f=_regular_cash_session_bars(cash_frame(),
            {'segment':'NSE_EQ','kind':'stock','symbol':'TEST'},5)
        self.assertEqual(len(f),75)
        self.assertEqual(f.attrs['out_of_session_discarded'],1)

    def test_futures_oi_not_filtered_by_cash_hours(self):
        f=_regular_cash_session_bars(cash_frame(),
            {'segment':'NSE_FNO','instrument':'FUTIDX','kind':'future'},5)
        self.assertEqual(len(f),76)
        self.assertEqual(f.index[-1].strftime('%H:%M'),'18:15')

    def test_15m_spot_grid_and_close_boundary(self):
        idx=pd.DatetimeIndex(['2026-11-12T09:15:00+05:30',
            '2026-11-12T15:15:00+05:30',
            '2026-11-12T15:30:00+05:30',
            '2026-11-12T18:15:00+05:30'])
        f=pd.DataFrame({'close':[1,2,3,4]},index=idx)
        result=_regular_cash_session_bars(f,{'segment':'IDX_I'},15)
        self.assertEqual(list(result.index.strftime('%H:%M')),['09:15','15:15'])
        self.assertEqual(result.attrs['out_of_session_discarded'],2)

    def test_fib_uses_exact_opening_bars_after_spurious_bar_removed(self):
        f=_regular_cash_session_bars(cash_frame(),
              {'segment':'IDX_I','kind':'index'},5)
        # No difference to opening-range reference after late anomaly is rejected.
        result=fib_smc.evaluate(f,pd.Timestamp('2026-11-12T10:05:00+05:30'),'0945')
        self.assertEqual(result['fib']['0'],99)
        self.assertEqual(result['fib']['1'],101)


if __name__=='__main__':unittest.main()
