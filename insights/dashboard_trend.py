"""Dashboard-only trend model; does not change strategy eligibility."""
import math
from insights.indicators import add_features


def dashboard_trend(frame):
    try:
        f = add_features(frame)
        if not all(math.isfinite(value) for value in f[['open', 'high', 'low', 'close']].to_numpy().flat):
            raise ValueError('Non-finite prices')
        x = f.iloc[-1]
        tolerance = max(float(x.atr) * .10, float(x.close) * .00001)
        if not math.isfinite(tolerance):
            raise ValueError('ATR unavailable')
    except (ValueError, TypeError) as exc:
        return dict(bias='UNAVAILABLE', score=None, components=[], reasons=[], warnings=[str(exc)])
    components = []
    def direction(value):
        return 1 if value > tolerance else -1 if value < -tolerance else 0
    def add(name, weight, sign, detail):
        components.append(dict(name=name, maximum=weight, points=weight * sign, detail=detail))
    add('Price vs EMA20', 20, direction(x.close-x.ema20), f'Close {x.close:.2f}; EMA20 {x.ema20:.2f}')
    add('EMA20 vs EMA50', 20, direction(x.ema20-x.ema50), f'EMA50 {x.ema50:.2f}')
    add('EMA50 vs EMA200', 10, direction(x.ema50-x.ema200), f'EMA200 {x.ema200:.2f}')
    slope = direction(x.ema20-f.ema20.iloc[-4])
    add('EMA20 slope over 3 bars', 20, slope, f'Change {x.ema20-f.ema20.iloc[-4]:+.2f}')
    up = f.high.diff(); down = -f.low.diff()
    plus = up.where((up > down) & (up > 0), 0).ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1]
    minus = down.where((down > up) & (down > 0), 0).ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1]
    dm = 1 if plus > minus else -1 if minus > plus else 0
    strong = math.isfinite(x.adx) and x.adx >= 22 and dm == slope
    add('ADX with directional movement', 15, dm if strong else 0,
        f'ADX {x.adx:.1f}; requires >=22 and direction agreeing with EMA slope' if math.isfinite(x.adx) else 'No measurable directional strength; neutral')
    breakout = 1 if x.close > x.resistance+tolerance else -1 if x.close < x.support-tolerance else 0
    add('Previous 20-bar breakout', 15, breakout, f'Range {x.support:.2f}–{x.resistance:.2f}')
    score = sum(c['points'] for c in components)
    return dict(version='dashboard-price-v1', bias='Uptrend' if score >= 40 else 'Downtrend' if score <= -40 else 'Sideways',
                score=score, components=components,
                reasons=[f"{c['name']}: {c['points']:+d}/{c['maximum']} · {c['detail']}" for c in components],
                warnings=['5-minute technical trend; not day change or a probability. Volume/VWAP is not required for cash indices.'])
