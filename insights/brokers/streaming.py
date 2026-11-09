"""Optional read-only Dhan WebSocket quote collector (not an order feed).

Use in a separate process or thread with verified Dhan entitlement. The scanner
remains REST-snapshot-based until this feed is explicitly configured and tested.
"""
from __future__ import annotations
import threading
from insights.brokers.dhan import DhanReadOnly,BrokerUnavailable

class DhanQuoteStream:
    def __init__(self,broker=None):
        self.broker=broker or DhanReadOnly();self.feed=None;self.worker=None
        self.latest={};self.lock=threading.RLock();self.error=''

    def start(self,items):
        if self.worker and self.worker.is_alive():return
        if not self.broker.configured():raise BrokerUnavailable('Dhan credentials unavailable')
        from dhanhq import DhanContext,MarketFeed
        constants={'NSE_EQ':MarketFeed.NSE,'NSE_FNO':MarketFeed.NSE_FNO,'IDX_I':MarketFeed.IDX,'BSE_FNO':MarketFeed.BSE_FNO,'BSE_EQ':MarketFeed.BSE}
        selected=[(constants[i['segment']],str(i['id']),MarketFeed.Quote) for i in items if i.get('segment') in constants]
        if not selected:raise BrokerUnavailable('No mapped instruments for streaming')
        self.feed=MarketFeed(DhanContext(self.broker.client_id,self.broker._token),selected,'v2')
        def run():
            try:
                self.feed.run_forever()
                while True:
                    msg=self.feed.get_data()
                    if not isinstance(msg,dict):continue
                    key=(msg.get('exchange_segment'),str(msg.get('security_id')))
                    with self.lock:self.latest[key]=msg
            except Exception:
                self.error='Market feed disconnected. Reconnect in controlled worker; no orders sent.'
        self.worker=threading.Thread(target=run,daemon=True,name='DhanQuotes');self.worker.start()

    def stop(self):
        if self.feed:self.feed.close_connection()
