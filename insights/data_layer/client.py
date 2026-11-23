"""Read-only compatibility facade for the existing Insights adapter."""
from .history import HistoryStore
from .transport import ReadOnlyViolation
class Client:
    def __init__(self,transport):self.transport=transport;self.history=HistoryStore(transport)
    def __getattr__(self,name):raise ReadOnlyViolation('Unsupported Dhan method blocked')
    def intraday_minute_data(self,security_id,exchange_segment,instrument_type,from_date,to_date,interval=5,oi=False):
        return self.history.fetch('/charts/intraday',dict(securityId=security_id,exchangeSegment=exchange_segment,instrument=instrument_type,fromDate=from_date,toDate=to_date,interval=str(interval),oi=oi))
    def historical_daily_data(self,security_id,exchange_segment,instrument_type,from_date,to_date,expiry_code=0,oi=False):
        payload=dict(securityId=security_id,exchangeSegment=exchange_segment,instrument=instrument_type,fromDate=from_date,toDate=to_date,oi=oi)
        # expiryCode is optional and describes futures, not option expiry dates.
        if expiry_code is not None and instrument_type not in ('OPTIDX','OPTSTK'):
            payload['expiryCode']=expiry_code
        return self.history.fetch('/charts/historical',payload)
    def expiry_list(self,underlying_scrip,underlying_seg):
        return self.transport.request('POST','/optionchain/expirylist',dict(UnderlyingScrip=underlying_scrip,UnderlyingSeg=underlying_seg))
    def option_chain(self,underlying_scrip,underlying_seg,expiry):
        return self.transport.request('POST','/optionchain',dict(UnderlyingScrip=underlying_scrip,UnderlyingSeg=underlying_seg,Expiry=expiry))
