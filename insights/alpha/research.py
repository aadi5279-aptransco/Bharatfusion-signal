"""Pure research evaluation. Inputs must be point-in-time, verified closed bars.

All fee rates are decimal fractions, not percentages. No default live tariff is
invented: a caller supplies a dated schedule appropriate to the instrument.
This first stage supports normal round trips, not exercise/physical settlement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import exp, isfinite, sqrt
from typing import Sequence
from zoneinfo import ZoneInfo

from patterns.types import Bar


def finite(*values):
    if any(isinstance(x, bool) or not isfinite(x) for x in values):
        raise ValueError('Expected finite numeric values')


def aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timezone-aware timestamps required')


def money(value, whole=False):
    return float(Decimal(str(value)).quantize(Decimal('1' if whole else '.01'), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class Fees:
    version: str
    source: str
    valid_from: date
    valid_until: date
    brokerage_rate: float
    brokerage_cap: float
    brokerage_flat: float
    stt_buy: float
    stt_sell: float
    exchange: float
    sebi: float
    stamp_buy: float
    ipft: float
    gst: float
    delivery_sell_fee: float = 0.0

    def __post_init__(self):
        rates = (self.brokerage_rate, self.stt_buy, self.stt_sell,
                 self.exchange, self.sebi, self.stamp_buy, self.ipft, self.gst)
        finite(*rates, self.brokerage_cap, self.brokerage_flat, self.delivery_sell_fee)
        if (not self.version or not self.source or self.valid_from > self.valid_until
                or any(not 0 <= x <= 1 for x in rates)
                or min(self.brokerage_cap, self.brokerage_flat, self.delivery_sell_fee) < 0):
            raise ValueError('Invalid explicit fee schedule')

    def leg(self, price, quantity, side, day):
        finite(price, quantity)
        if price <= 0 or type(quantity) is not int or quantity <= 0 or side not in (-1, 1):
            raise ValueError('Invalid fill')
        if not self.valid_from <= day <= self.valid_until:
            raise ValueError('Fee schedule does not cover fill date')
        turnover = price * quantity
        brokerage = money(min(turnover * self.brokerage_rate, self.brokerage_cap) + self.brokerage_flat)
        exchange = money(turnover * self.exchange)
        sebi = money(turnover * self.sebi)
        ipft = money(turnover * self.ipft)
        dp = self.delivery_sell_fee if side == -1 else 0.0
        result = dict(brokerage=brokerage, exchange=exchange, sebi=sebi, ipft=ipft,
                      stt=money(turnover * (self.stt_buy if side == 1 else self.stt_sell), True),
                      stamp=money(turnover * self.stamp_buy, True) if side == 1 else 0.0,
                      dp=money(dp), gst=money((brokerage + exchange + sebi + ipft + dp) * self.gst))
        result['total'] = money(sum(result.values()))
        return result


@dataclass(frozen=True)
class Candidate:
    signal_id: str
    known_at: datetime
    direction: int
    atr: float
    quantity: int
    tick: float
    prior_volume: float
    eligibility_verified: bool
    lot_size: int = 1

    def __post_init__(self):
        aware(self.known_at)
        finite(self.atr, self.tick, self.prior_volume)
        if (not self.signal_id or self.direction not in (-1, 1)
                or type(self.quantity) is not int or type(self.lot_size) is not int
                or min(self.atr, self.tick, self.prior_volume, self.quantity, self.lot_size) <= 0
                or self.quantity % self.lot_size or self.eligibility_verified is not True):
            raise ValueError('Candidate requires valid risk, lots and verified eligibility')


@dataclass(frozen=True)
class LabelConfig:
    stop_atr: float = 1.0
    target_atr: float = 1.5
    horizon: int = 12
    base_slippage_bps: float = 2.0
    impact_bps: float = 20.0
    max_participation: float = .01
    max_bar_gap: timedelta = timedelta(minutes=5)

    def __post_init__(self):
        finite(self.stop_atr, self.target_atr, self.base_slippage_bps, self.impact_bps, self.max_participation)
        if (min(self.stop_atr, self.target_atr) <= 0 or type(self.horizon) is not int
                or self.horizon < 1 or min(self.base_slippage_bps, self.impact_bps) < 0
                or not 0 < self.max_participation <= 1 or self.max_bar_gap <= timedelta(0)):
            raise ValueError('Invalid label configuration')


def label(candidate: Candidate, future: Sequence[Bar], fees: Fees,
          as_of: datetime, cfg: LabelConfig = LabelConfig()):
    """Market entry at first next bar open; ATR barriers anchored to actual fill.

    Missing/illiquid/locked bars quarantine the outcome, not a winning fill.
    Caller must pass the immediate subsequent contiguous bars. This first
    evaluator is intraday-only: missing candles and overnight gaps are rejected.
    """
    aware(as_of)
    if as_of < candidate.known_at:
        raise ValueError('Evaluation predates signal')
    participation = candidate.quantity / candidate.prior_volume
    if participation > cfg.max_participation:
        return dict(status='REJECTED_CAPACITY', signal_id=candidate.signal_id)
    slip = (cfg.base_slippage_bps + cfg.impact_bps * sqrt(participation)) / 10000
    if slip >= 1:
        raise ValueError('Slippage must be below 100 percent')
    def checked_bars():
        previous_end = candidate.known_at
        for b in future[:cfg.horizon]:
            aware(b.time); aware(b.closed_at)
            if b.closed_at > as_of:
                return  # Do not inspect future OHLCV.
            finite(b.open, b.high, b.low, b.close, b.volume)
            if (b.time != previous_end or not b.time < b.closed_at
                    or b.closed_at - b.time > cfg.max_bar_gap
                    or b.low <= 0 or b.low > min(b.open, b.close)
                    or b.high < max(b.open, b.close) or b.low > b.high):
                raise ValueError('Invalid, overlapping or missing bars')
            previous_end = b.closed_at
            yield b
    iterator = checked_bars()
    first = next(iterator, None)
    if first is None:
        return dict(status='PENDING', signal_id=candidate.signal_id)
    # Round execution against the trader, including stop/target fills.
    from decimal import ROUND_CEILING, ROUND_FLOOR
    def fill(price, side):
        raw = Decimal(str(price * (1 + side * slip))) / Decimal(str(candidate.tick))
        return float(raw.to_integral_value(rounding=ROUND_CEILING if side == 1 else ROUND_FLOOR) * Decimal(str(candidate.tick)))
    sign = candidate.direction
    entry = fill(first.open, sign)
    risk = cfg.stop_atr * candidate.atr
    stop = entry - sign * risk
    target = entry + sign * cfg.target_atr * candidate.atr
    if min(entry, stop, target) <= 0:
        raise ValueError('Non-positive price barrier')
    from itertools import chain
    for i, b in enumerate(chain((first,), iterator)):
        if b.circuit_locked or not b.eligible or b.volume < candidate.quantity / cfg.max_participation:
            return dict(status='QUARANTINED_LIQUIDITY', signal_id=candidate.signal_id)
        # Stop at gap-open, target at its limit (no optimistic gap improvement).
        stop_hit = b.low <= stop if sign == 1 else b.high >= stop
        target_hit = b.high >= target if sign == 1 else b.low <= target
        if stop_hit:
            raw_exit = min(b.open, stop) if sign == 1 else max(b.open, stop)
            reason = 'STOP'
        elif target_hit:
            raw_exit, reason = target, 'TARGET'
        elif i == cfg.horizon - 1:
            raw_exit, reason = b.close, 'TIME'
        else:
            continue
        exit_price = fill(raw_exit, -sign)
        if exit_price <= 0:
            raise ValueError('Slippage creates a non-positive fill')
        entry_fee = fees.leg(entry, candidate.quantity, sign, first.time.astimezone(ZoneInfo('Asia/Kolkata')).date())
        exit_fee = fees.leg(exit_price, candidate.quantity, -sign, b.time.astimezone(ZoneInfo('Asia/Kolkata')).date())
        total_fees = entry_fee['total'] + exit_fee['total']
        gross = sign * (exit_price - entry) * candidate.quantity
        return dict(status='RESOLVED', signal_id=candidate.signal_id,
                    start=first.time.isoformat(), end=b.closed_at.isoformat(),
                    outcome=reason, entry=entry, exit=exit_price, stop=stop, target=target,
                    gross_r=gross / (risk * candidate.quantity),
                    costs_r=total_fees / (risk * candidate.quantity),
                    net_r=(gross-total_fees) / (risk*candidate.quantity),
                    fees={'entry': entry_fee, 'exit': exit_fee}, fee_version=fees.version,
                    slippage_bps=slip*10000,
                    success=(gross-total_fees) > 0)
    return dict(status='PENDING', signal_id=candidate.signal_id)


@dataclass(frozen=True)
class Sample:
    known_at: datetime
    end: datetime

    def __post_init__(self):
        aware(self.known_at); aware(self.end)
        if self.end < self.known_at:
            raise ValueError('Label ends before features exist')


def walk_forward(samples: Sequence[Sample], min_train: int, test_size: int,
                 embargo: timedelta):
    """Expanding past-only folds. Purge labels not ended before test minus embargo."""
    if min_train < 1 or test_size < 1 or embargo < timedelta(0):
        raise ValueError('Invalid split configuration')
    if any(a.known_at > b.known_at for a, b in zip(samples, samples[1:])):
        raise ValueError('Samples must be chronological')
    for start in range(min_train, len(samples), test_size):
        cutoff = samples[start].known_at - embargo
        train = tuple(i for i in range(start) if samples[i].end < cutoff)
        test = tuple(range(start, min(start+test_size, len(samples))))
        if len(train) >= min_train:
            yield train, test


def uniqueness_weights(samples: Sequence[Sample], as_of: datetime, half_life_days: float):
    """Continuous-time uniqueness on half-open label intervals, then recency decay.

    Call separately on each training fold, never on validation/holdout samples.
    """
    aware(as_of); finite(half_life_days)
    if half_life_days <= 0 or any(s.end > as_of or s.end <= s.known_at for s in samples):
        raise ValueError('Only fully resolved positive-duration labels allowed')
    edges = sorted({t for s in samples for t in (s.known_at, s.end)})
    weights = []
    for s in samples:
        integral = 0.0
        for a, b in zip(edges, edges[1:]):
            if s.known_at <= a < s.end:
                concurrency = sum(x.known_at <= a < x.end for x in samples)
                integral += (b-a).total_seconds()/concurrency
        uniqueness = integral/(s.end-s.known_at).total_seconds()
        weights.append(uniqueness * exp(-.6931471805599453 * (as_of-s.end).total_seconds()/86400/half_life_days))
    return tuple(weights)


def opportunity_score(p_lower, avg_win_r, avg_loss_r, costs_r, slippage_r,
                      uncertainty_r=0.0, correlation_penalty_r=0.0, regime_fit=1.0):
    """Conservative ranking primitive; inputs must come from out-of-sample evidence.

    avg win/loss are BEFORE costs and slippage to prevent double deductions.
    This helper never creates a probability or authorizes a live signal.
    """
    finite(p_lower, avg_win_r, avg_loss_r, costs_r, slippage_r, uncertainty_r, correlation_penalty_r, regime_fit)
    if not 0 <= p_lower <= 1 or not 0 <= regime_fit <= 1 or min(avg_win_r, avg_loss_r, costs_r, slippage_r, uncertainty_r, correlation_penalty_r) < 0:
        raise ValueError('Invalid expectancy inputs')
    gross = p_lower*avg_win_r - (1-p_lower)*avg_loss_r
    # Poor regime fit may discount gains but never make negative edge less bad.
    return min(gross, gross*regime_fit) - costs_r - slippage_r - uncertainty_r - correlation_penalty_r


def assert_prefix_causal(feature_fn, observations):
    """Test a pure one-output-per-bar feature builder against every input prefix.

    This detects retrospective mutation/centred windows, not leaked source data
    or preprocessing fitted on a holdout. Those need separate provenance gates.
    Outputs must be finite JSON-compatible records; encode warm-up as None.
    """
    import json
    def encode(rows):
        return json.dumps(rows, sort_keys=True, allow_nan=False)
    full = list(feature_fn(tuple(observations)))
    if len(full) != len(observations):
        raise ValueError('Feature builder must return one record per input bar')
    for end in range(1, len(observations)+1):
        prefix = list(feature_fn(tuple(observations[:end])))
        if encode(prefix) != encode(full[:end]):
            raise ValueError(f'Feature leakage or retrospective mutation at prefix {end}')
