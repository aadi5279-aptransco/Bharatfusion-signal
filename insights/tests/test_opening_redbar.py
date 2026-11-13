"""First 5m range and first red candle options: deterministic no-lookahead tests."""
import unittest
import pandas as pd
from insights.config import IST
from insights.strategies import opening_redbar


def sample(reds=False,down=False):
    idx=pd.date_range('2026-11-12 09:15',periods=12,freq='5min',tz=IST)
    oo=[100.] * 12;hh=[101.] * 12;ll=[99.] * 12;cc=[100.]*12
    if reds:
        oo[1]=101;cc[1]=100;hh[1]=102;ll[1]=98
        # red candle Fib: high 102, low 98; .44=100.24, .56=99.76
        for j in range(2,12):
            oo[j]=100.4 if not down else 99.5
            cc[j]=101.4 if not down else 98.5
            hh[j]=102 if not down else 100
            ll[j]=100 if not down else 98
    else:
        for j in range(1,12):
            oo[j]=101 if not down else 99
            cc[j]=102 if not down else 98
            hh[j]=103 if not down else 100
            ll[j]=100 if not down else 97
    return pd.DataFrame(dict(open=oo,high=hh,low=ll,close=cc,
                        volume=[1000]*12),index=idx)


class OpeningRedbarTests(unittest.TestCase):
    def at(self,clock):
        return pd.Timestamp('2026-11-12 '+clock,tz=IST)
    def test_first5_requires_two_completed_closes(self):
        f=sample()
        before=opening_redbar.evaluate(f,self.at('09:25'))[0]
        after=opening_redbar.evaluate(f,self.at('09:30'))[0]
        self.assertEqual(before['state'],'WAITING')
        self.assertEqual(after['state'],'DIRECTION_READY')
        self.assertEqual(after['side'],'CE')
        self.assertEqual(after['fib']['0'],99)
        self.assertEqual(after['fib']['1'],101)
    def test_first5_pe_below_low(self):
        f=sample(down=True)
        x=opening_redbar.evaluate(f,self.at('09:30'))[0]
        self.assertEqual(x['side'],'PE')
        self.assertEqual(x['state'],'DIRECTION_READY')
    def test_first_red_skips_first_5m_candle(self):
        f=sample(reds=True)
        x=opening_redbar.evaluate(f,self.at('09:35'))[1]
        self.assertEqual(x['reference_at'][11:16],'09:20')
        self.assertEqual(x['fib']['0.44'],100.24)
        self.assertEqual(x['fib']['0.56'],99.76)
        self.assertGreater(x['trigger_ce'],x['trigger_pe'])
        self.assertEqual(x['side'],'CE')
    def test_first_red_pe_below_lower_056(self):
        f=sample(reds=True,down=True)
        x=opening_redbar.evaluate(f,self.at('09:35'))[1]
        self.assertEqual(x['side'],'PE')
        self.assertEqual(x['state'],'DIRECTION_READY')
    def test_no_red_candle_waits(self):
        f=sample(reds=False)
        result=opening_redbar.evaluate(f,self.at('09:40'))[1]
        self.assertEqual(result['state'],'WAITING')
    def test_gap_missing_first5_fails_closed(self):
        f=sample().drop(pd.Timestamp('2026-11-12 09:20',tz=IST))
        first,red=opening_redbar.evaluate(f,self.at('09:40'))
        self.assertEqual(first['state'],'WAITING')
        self.assertEqual(red['state'],'WAITING')
    def test_outside_session_bar_not_used(self):
        f=sample()
        extra=f.iloc[-1:].copy()
        extra.index=pd.DatetimeIndex([self.at('18:15')])
        combined=pd.concat([f,extra])
        result=opening_redbar.evaluate(combined,self.at('18:30'))[0]
        self.assertEqual(result['state'],'DIRECTION_READY')
        self.assertEqual(result['signal_at'][11:16],'10:10')
    def test_previous_session_only_fails_closed(self):
        f=sample()
        x=opening_redbar.evaluate(f,self.at('2026-11-13 10:00') if False else
                                  pd.Timestamp('2026-11-13 10:00',tz=IST))[0]
        self.assertEqual(x['state'],'WAITING')


if __name__=='__main__':unittest.main()
