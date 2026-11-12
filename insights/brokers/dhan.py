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

    @staticmethod
    def _unwrap_sdk_data(value):
        """Handle both flat Dhan payloads and nested SDK response envelopes.

        The SDK may return {status:success,data:{status:success,data:[...]}}
        from expiry_list. Only unwrap dicts composed of envelope keys so that
        real market payload fields such as oc and last_price stay intact.
        """
        for _ in range(3):
            if not isinstance(value,dict):
                break
            if value.get('status')=='failure':
                raise BrokerUnavailable('Dhan rejected a nested data response')
            if 'data' not in value or not set(value).issubset({'data','status','remarks'}):
                break
            value=value['data']
        return value

    def expiry_list(self,item):
        key=(str(item['segment']),str(item['id']))
        with self._lock:
            v=self._expiry_cache.get(key)
            if v and time.monotonic()-v[0]<3600:return list(v[1])
        data=self._unwrap_sdk_data(self._check(self._sdk().expiry_list(int(item['id']),item['segment'])))
        if not isinstance(data,list) or not data or not all(isinstance(x,str) and len(x)==10 for x in data):
            raise BrokerUnavailable('Invalid expiry list')
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
            data=self._unwrap_sdk_data(self._check(self._sdk().option_chain(int(item['id']),item['segment'],expiry)))
            if not isinstance(data,dict) or not isinstance(data.get('oc'),dict) or not data['oc']:
                raise BrokerUnavailable('Invalid Dhan option chain')
            self._option_cache[key]=(time.monotonic(),data)
            return data

    def market_quotes(self, items, now=None):
        """Single Dhan Market Quote batch for initial gainers/losers discovery.

        Quote volume is session-to-date, not relative volume. Deep 5m candle
        history is separately required before a symbol joins the shortlist.
        """
        from urllib.request import Request,urlopen
        now=(now or datetime.now(IST)).astimezone(IST)
        if not items:return {}
        self._sdk()
        groups={}
        for item in items[:500]:
            if item.get('id') and item.get('segment'):
                try:groups.setdefault(str(item['segment']),[]).append(int(item['id']))
                except (TypeError,ValueError):continue
        if not groups:return {}
        req=Request('https://api.dhan.co/v2/marketfeed/quote',
            data=json.dumps(groups).encode('utf-8'),
            headers={'Content-Type':'application/json','Accept':'application/json',
                     'access-token':self._token,'client-id':str(self.client_id)},
            method='POST')
        try:
            with urlopen(req,timeout=20) as resp:data=json.load(resp)
            raw=self._unwrap_sdk_data(self._check(data))
        except Exception:return {}
        if not isinstance(raw,dict):return {}
        out={}
        for item in items:
            segment=str(item.get('segment',''));key=str(item.get('id',''))
            part=raw.get(segment,{})
            quote=part.get(key,{}) if isinstance(part,dict) else {}
            if not isinstance(quote,dict):continue
            try:
                price=float(quote.get('last_price') or 0)
                session_open=float((quote.get('ohlc') or {}).get('open') or 0)
                volume=float(quote.get('volume') or 0)
                if price<=0 or session_open<=0 or volume<=0:continue
                change_pct=100*(price/session_open-1)
            except (TypeError,ValueError,ZeroDivisionError):continue
            if not -40<=change_pct<=40:continue
            out[key]=dict(change_pct=round(change_pct,3),volume=volume,
                fetched_at=now.isoformat(),source='DHAN SESSION QUOTE')
        return out

    def depth_snapshots(self, items, now=None):
        """One batched Dhan Market Quote read, never an order or trade tape.

        Returned ratios describe resting five-level depth only. They are not
        actual aggressor delta, footprint or institutional execution.
        """
        from urllib.request import Request, urlopen
        now=(now or datetime.now(IST)).astimezone(IST)
        if not items:return {}
        self._sdk()  # verify local token status before network request
        payload={}
        for item in items[:200]:
            if item.get('segment') and item.get('id'):
                payload.setdefault(str(item['segment']),[]).append(int(item['id']))
        if not payload:return {}
        body=json.dumps(payload).encode('utf-8')
        req=Request('https://api.dhan.co/v2/marketfeed/quote',data=body,
                    headers={'Content-Type':'application/json',
                             'Accept':'application/json','access-token':self._token,
                             'client-id':str(self.client_id)},method='POST')
        try:
            with urlopen(req,timeout=20) as resp:
                obj=json.load(resp)
            data=self._unwrap_sdk_data(self._check(obj))
        except Exception:
            return {}  # optional evidence only; never block price-only analysis
        if not isinstance(data,dict):return {}
        results={}
        for item in items:
            raw=(data.get(str(item.get('segment')),{}).get(str(item.get('id')),{})
                 if isinstance(data.get(str(item.get('segment')),{}),dict) else {})
            if not isinstance(raw,dict):continue
            depth=raw.get('depth') or {}
            if not isinstance(depth,dict):continue
            def quantity(name):
                entries=depth.get(name) or []
                if not isinstance(entries,list):return 0
                return sum(max(0,float(x.get('quantity',0) or 0)) for x in entries[:5]
                           if isinstance(x,dict))
            try:bid=quantity('buy');ask=quantity('sell')
            except (ValueError,TypeError):continue
            if bid<=0 or ask<=0:continue
            # A received snapshot is not proof that the exchange last trade
            # timestamp is recent. Fail closed if it cannot be validated.
            last=raw.get('last_trade_time')
            fresh=False
            if last:
                try:
                    t=pd.Timestamp(last)
                    if t.tzinfo is None:t=t.tz_localize(IST)
                    else:t=t.tz_convert(IST)
                    fresh=(t.date()==now.date() and 0<=(now-t.to_pydatetime()).total_seconds()<=120)
                except (ValueError,TypeError,OverflowError):pass
            results[str(item['id'])]=dict(verified=fresh,bid_ask_ratio=round(bid/ask,3),
                observed_at=now.isoformat(),last_trade_time=str(last) if last else None,
                source='DHAN FIVE-LEVEL RESTING MARKET DEPTH — NOT TRADE DELTA')
        return results

    def instruments(self):
        # Official Dhan-hosted detailed master via pre-existing source parser.
        from data import universe
        return universe(reuse=True)
