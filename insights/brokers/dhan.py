"""Read-only DhanHQ v2 SDK adapter. No order APIs or website scraping.

Dhan tokens can only be renewed automatically while active and eligible
(Web-generated tokens). A failed renewal explicitly requires reauthentication.
"""
from __future__ import annotations
import base64,json,os,threading,time
from datetime import datetime,timedelta
from datetime import timezone
import pandas as pd
from insights.config import IST

class BrokerUnavailable(RuntimeError):pass


def _expires_at(token):
    """JWT exp is a renewal scheduling hint, NOT an authentication check."""
    try:
        segment=token.split('.')[1]
        payload=json.loads(base64.urlsafe_b64decode(segment+'='*(-len(segment)%4)))
        return int(payload['exp'])
    except (IndexError,ValueError,KeyError,TypeError):return None


class DhanReadOnly:
    name='DHAN'
    def __init__(self,client_id=None,token=None):
        self.client_id=client_id or os.getenv('DHAN_CLIENT_ID','')
        self._token=token or os.getenv('DHAN_ACCESS_TOKEN','')
        self._client=None
        self._lock=threading.RLock()
        self._option_last=0.0
        self._option_cache={}
        self._expiry_cache={}
        self._history_cache={}
        self._renewal_error=''
        self._last_ok=None

    def configured(self):return bool(self.client_id and self._token)

    def _sdk(self):
        if not self.configured():raise BrokerUnavailable('Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN locally')
        with self._lock:
            expiry=_expires_at(self._token)
            if expiry and expiry-time.time()<1800 and os.getenv('DHAN_WEB_GENERATED_TOKEN','false').lower()=='true':
                self._renew_token()
            elif expiry and expiry<=time.time():raise BrokerUnavailable('Dhan token expired; renew it in Dhan Web')
            if self._client is None:
                try:from dhanhq import DhanContext,dhanhq
                except ImportError:raise BrokerUnavailable('Install the official dhanhq package') from None
                self._client=dhanhq(DhanContext(self.client_id,self._token))
            return self._client

    def _renew_token(self):
        try:
            from dhanhq import DhanLogin
            response=DhanLogin(self.client_id).renew_token(self._token)
            data=response.get('data',response) if isinstance(response,dict) else {}
            token=data.get('accessToken') or data.get('access_token')
            if not token:raise ValueError('No replacement token')
            self._token=token;self._client=None;self._renewal_error=''
        except Exception:
            self._renewal_error='Automatic token renewal failed. Reauthenticate in Dhan Web.'
            raise BrokerUnavailable(self._renewal_error) from None

    def _check(self,result):
        if not isinstance(result,dict) or result.get('status')=='failure':
            raise BrokerUnavailable('Dhan rejected a data request or entitlement; no signal generated')
        self._last_ok=time.monotonic()
        return result.get('data',result)

    def history(self,item,now=None,minutes=5,lookback_days=6,oi=False):
        now=(now or datetime.now(IST)).astimezone(IST)
        key=(str(item['segment']),str(item['id']),minutes,lookback_days,oi)
        with self._lock:
            existing=self._history_cache.get(key)
            if existing and time.monotonic()-existing[0]<180:return existing[1].copy()
        start=now-timedelta(days=lookback_days)
        raw=self._check(self._sdk().intraday_minute_data(
            security_id=str(item['id']),exchange_segment=item['segment'],instrument_type=item['instrument'],
            from_date=start.strftime('%Y-%m-%d %H:%M:%S'),to_date=now.strftime('%Y-%m-%d %H:%M:%S'),interval=minutes,oi=oi))
        # Dhan v2 timestamps are Unix seconds. Candles starting at/after the current bar are ignored.
        try:
            frame=pd.DataFrame({k:raw[k] for k in ('open','high','low','close','volume')},
                  index=pd.to_datetime(raw['timestamp'],unit='s',utc=True).tz_convert(IST))
            if oi:
                if 'open_interest' not in raw:raise ValueError('Futures OI unavailable')
                frame['oi']=raw['open_interest']
            frame=frame.astype(float).sort_index()
            frame=frame[frame.index+pd.Timedelta(minutes=minutes)<=pd.Timestamp(now)]
            if frame.empty:raise ValueError('No completed candles')
        except (KeyError,TypeError,ValueError) as exc:raise BrokerUnavailable('Invalid Dhan OHLCV') from exc
        with self._lock:self._history_cache[key]=(time.monotonic(),frame.copy())
        return frame

    def daily(self,item,now=None,days=450,oi=False):
        now=(now or datetime.now(IST)).astimezone(IST)
        start=now-timedelta(days=days)
        raw=self._check(self._sdk().historical_daily_data(
            security_id=str(item['id']),exchange_segment=item['segment'],instrument_type=item['instrument'],
            from_date=start.strftime('%Y-%m-%d'),to_date=now.strftime('%Y-%m-%d'),expiry_code=0,oi=oi))
        try:
            cols=['open','high','low','close','volume']
            frame=pd.DataFrame({k:raw[k] for k in cols},
                index=pd.to_datetime(raw['timestamp'],unit='s',utc=True).tz_convert(IST).normalize()).astype(float)
            if oi:
                frame['oi']=raw['open_interest']
            # Current partial daily candle cannot be used for historical strategy gates.
            return frame[frame.index.date<now.date()].sort_index()
        except (ValueError,KeyError,TypeError):raise BrokerUnavailable('Invalid Dhan daily candles') from None

    def expiry_list(self,item):
        key=(str(item['segment']),str(item['id']))
        with self._lock:
            v=self._expiry_cache.get(key)
            if v and time.monotonic()-v[0]<3600:return list(v[1])
        data=self._check(self._sdk().expiry_list(int(item['id']),item['segment']))
        if not isinstance(data,list):raise BrokerUnavailable('Invalid expiry list')
        with self._lock:self._expiry_cache[key]=(time.monotonic(),list(data))
        return data

    def option_chain(self,item,expiry):
        key=(str(item['segment']),str(item['id']),str(expiry))
        # Global serialization is deliberately more conservative than Dhan's unique-request limit.
        with self._lock:
            cached=self._option_cache.get(key)
            if cached and time.monotonic()-cached[0]<30:return cached[1]
            wait=max(0.0,3.1-(time.monotonic()-self._option_last))
            if wait:time.sleep(wait)
            self._option_last=time.monotonic()
            data=self._check(self._sdk().option_chain(int(item['id']),item['segment'],expiry))
            if not isinstance(data,dict) or not isinstance(data.get('oc'),dict):raise BrokerUnavailable('Invalid Dhan option chain')
            self._option_cache[key]=(time.monotonic(),data)
            return data

    def instruments(self):
        # Official Dhan-hosted detailed master via pre-existing source parser.
        from data import universe
        return universe(reuse=True)
