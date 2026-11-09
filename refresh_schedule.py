"""Fixed start grid, with missed cycles skipped and no catch-up scan storm."""
import math

def next_refresh(started, finished, interval=300):
    if interval <= 0:raise ValueError('Refresh interval must be positive')
    return started + max(1, math.floor(max(0, finished-started)/interval)+1)*interval
