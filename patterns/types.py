"""Immutable, broker-independent inputs and serializable pattern evidence."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

Timeframe = Literal['5m', '15m', '1h', 'daily', 'weekly', 'monthly']
Direction = Literal['BUY', 'SELL', 'NEUTRAL']

@dataclass(frozen=True)
class Bar:
    time: datetime
    closed_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    circuit_locked: bool = False
    eligible: bool = True

@dataclass(frozen=True)
class Pivot:
    index: int
    price: float
    kind: Literal['HIGH', 'LOW']
    confirmed_index: int

@dataclass(frozen=True)
class Context:
    tick_size: float = .05
    levels: tuple[tuple[str, float], ...] = ()
    # External evidence must be available no later than the scan clock.
    known_at: datetime | None = None
    all_time_history: bool = False
    source: str = 'caller-supplied closed bars'

@dataclass(frozen=True)
class Pattern:
    pattern: str
    direction: Direction
    score: float
    bar_index: int
    time: datetime
    confirmed: bool
    context: tuple[str, ...]
    entry: float | None
    stop: float | None
    target: float | None
    invalidation: str
    start: datetime
    end: datetime
    levels: tuple[tuple[str, float], ...]
    trendlines: tuple[tuple[str, float, float], ...]
    timeframe: Timeframe
    available_at: datetime
    version: str = 'patterns-v1'
    score_type: str = 'DETERMINISTIC RULE SCORE; NOT WIN PROBABILITY'

    def to_dict(self) -> dict:
        out = asdict(self)
        for key in ('time', 'start', 'end', 'available_at'):
            out[key] = out[key].isoformat()
        out['context'] = list(self.context)
        out['levels'] = dict(self.levels)
        out['trendlines'] = [dict(name=n, slope=s, intercept=b) for n,s,b in self.trendlines]
        out['status'] = 'confirmed' if self.confirmed else 'forming'
        return out
