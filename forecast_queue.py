"""Bounded, coalescing work queue: update pending snapshots without starving symbols."""
from collections import OrderedDict
from threading import Condition

class ForecastQueue:
    def __init__(self,capacity=40):self.jobs=OrderedDict();self.cv=Condition();self.capacity=capacity
    def put(self,job):
        r,_=job;key=(r['mode'],r['symbol'])
        with self.cv:
            if key not in self.jobs and len(self.jobs)>=self.capacity:return False
            self.jobs[key]=job;self.cv.notify();return True
    def get(self):
        with self.cv:
            while not self.jobs:self.cv.wait()
            return self.jobs.popitem(last=False)[1]
    def clear(self):
        with self.cv:self.jobs.clear()
    def size(self):
        with self.cv:return len(self.jobs)
