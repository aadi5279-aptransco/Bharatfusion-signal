"""Versioned definitions, not universal or profitability-optimized thresholds."""
from dataclasses import dataclass, fields
import math

@dataclass(frozen=True)
class PatternConfig:
    atr_period: int = 14
    volume_period: int = 20
    trend_period: int = 10
    trend_atr: float = .5
    location_atr: float = 1.0
    min_volume: float = 1
    min_turnover: float = 100000
    doji_body: float = .10
    small_body: float = .30
    long_body: float = .60
    marubozu_body: float = .90
    wick_body: float = 2.0
    short_wick: float = .10
    min_range_atr: float = .20
    max_range_atr: float = 4.0
    tweezer_atr: float = .10
    star_body_ratio: float = .30
    penetration: float = .50
    gap_atr: float = .05
    require_gaps: bool = False
    require_confirmation: bool = True
    require_volume: bool = True
    volume_multiple: float = 1.3
    breakout_volume: float = 1.5
    ignore_opening_bars: int = 2
    pivot_right: int = 3
    pivot_left: int = 3
    zigzag_atr: float = 1.0
    equal_atr: float = .5
    min_pattern_bars: int = 8
    max_pattern_bars: int = 100
    breakout_atr: float = .05
    stop_atr: float = .10
    candle_reward_risk: float = 2.0
    flat_slope_atr: float = .04
    parallel_slope_atr: float = .08
    min_contraction: float = .15
    pole_atr: float = 3.0
    max_flag_retrace: float = .50
    cup_min_bars: int = 30
    cup_handle_max: float = .33
    rounded_depth_atr: float = 2.0
    high52_bars: int = 252
    darvas_bars: int = 10
    range_bars: int = 20
    opening_range_minutes: int = 15

    def __post_init__(self):
        for name in ('require_gaps','require_confirmation','require_volume'):
            if type(getattr(self,name)) is not bool:raise ValueError(f'{name} must be boolean')
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bool):
                continue
            if not math.isfinite(value) or value < 0:
                raise ValueError(f'Invalid threshold: {f.name}')
        for name in ('atr_period','volume_period','trend_period','pivot_left','pivot_right',
                     'min_pattern_bars','max_pattern_bars','cup_min_bars','high52_bars',
                     'darvas_bars','range_bars','opening_range_minutes'):
            if type(getattr(self,name)) is not int or getattr(self,name)<1:
                raise ValueError(f'{name} must be a positive integer')
        if type(self.ignore_opening_bars) is not int:
            raise ValueError('ignore_opening_bars must be an integer')
        if not 0 < self.doji_body < self.small_body < self.long_body < self.marubozu_body <= 1:
            raise ValueError('Body thresholds must be strictly ordered')
        if any(not 0 < getattr(self,name) < 1 for name in ('short_wick','star_body_ratio','max_flag_retrace','cup_handle_max')):
            raise ValueError('Invalid morphology fraction')
        if self.min_range_atr>=self.max_range_atr:raise ValueError('Invalid ATR range')
        if not 0 < self.penetration < 1 or not 0 < self.min_contraction < 1:
            raise ValueError('Invalid fraction')
        if self.min_pattern_bars >= self.max_pattern_bars or self.atr_period<2:
            raise ValueError('Invalid lookbacks')
        if min(self.zigzag_atr,self.candle_reward_risk,self.volume_multiple,self.breakout_volume)<=0:
            raise ValueError('Positive confirmation/risk thresholds required')
