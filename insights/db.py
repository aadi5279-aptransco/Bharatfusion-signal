"""Dedicated signal journal. No fabricated outcomes, SQLite WAL for concurrent readers."""
from __future__ import annotations
import json, sqlite3, threading
from pathlib import Path

_SCHEMA = '''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS signals (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 signal_key TEXT NOT NULL UNIQUE,
 strategy TEXT NOT NULL, version TEXT NOT NULL,
 symbol TEXT NOT NULL, direction TEXT NOT NULL,
 signal_at TEXT NOT NULL, entry REAL NOT NULL, t1 REAL NOT NULL,
 t2 REAL NOT NULL, sl REAL NOT NULL, rr REAL NOT NULL,
 confidence REAL NOT NULL, reasons TEXT NOT NULL,
 backtest_status TEXT NOT NULL DEFAULT 'UNVALIDATED',
 status TEXT NOT NULL DEFAULT 'OPEN', outcome_at TEXT,
 exit_price REAL, costs REAL NOT NULL DEFAULT 0,
 data_source TEXT NOT NULL DEFAULT 'DHAN',
 instrument_id TEXT, segment TEXT, instrument_type TEXT
);
CREATE INDEX IF NOT EXISTS signals_strategy_time ON signals(strategy, signal_at);
CREATE TABLE IF NOT EXISTS backtests (
 strategy TEXT PRIMARY KEY, version TEXT NOT NULL,
 tested_at TEXT NOT NULL, samples INTEGER NOT NULL,
 win_rate REAL, profit_factor REAL,
 drawdown_pct REAL, avg_r REAL, net_r REAL,
 eligible INTEGER NOT NULL, notes TEXT NOT NULL
);
'''


class Journal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self._connect() as c:
            c.executescript(_SCHEMA)
            # Add-only migration for pre-upgrade local journals.
            old={r[1] for r in c.execute('PRAGMA table_info(signals)')}
            for key in ('instrument_id','segment','instrument_type'):
                if key not in old:c.execute(f'ALTER TABLE signals ADD COLUMN {key} TEXT')

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=20)

    def record(self, signal):
        """Called only for complete, deterministic, market-sourced signals."""
        for n in ('strategy','version','symbol','direction','signal_at','entry','t1','t2','sl','rr','confidence','reasons'):
            if n not in signal: raise ValueError(f'Missing {n}')
        import math
        d=signal['direction']; entry=float(signal['entry']); sl=float(signal['sl']); t1=float(signal['t1']); t2=float(signal['t2'])
        if d not in ('BUY','SELL','CE','PE'): raise ValueError('Invalid direction')
        sign=1 if d in ('BUY','CE','PE') else -1
        if not all(math.isfinite(float(signal[n])) for n in ('entry','t1','t2','sl','rr','confidence')): raise ValueError('Non-finite levels')
        if not sign*(sl-entry)<0 or not 0<sign*(t1-entry)<=sign*(t2-entry): raise ValueError('Invalid level order')
        if not isinstance(signal['reasons'], list) or not signal['reasons']: raise ValueError('Reasons must follow rules')
        key='|'.join(str(signal[n]) for n in ('strategy','version','symbol','direction','signal_at'))
        with self.lock, self._connect() as c:
            c.execute('''INSERT OR IGNORE INTO signals(signal_key,strategy,version,symbol,direction,signal_at,entry,t1,t2,sl,rr,confidence,reasons,backtest_status,instrument_id,segment,instrument_type)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (key,signal['strategy'],signal['version'],signal['symbol'],d,signal['signal_at'],entry,t1,t2,sl,float(signal['rr']),float(signal['confidence']),json.dumps(signal['reasons']),signal.get('backtest_status','UNVALIDATED'),str(signal.get('instrument_id','')) or None,signal.get('segment'),signal.get('instrument_type')))
        return key

    def pending(self,limit=30):
        with self.lock,self._connect() as c:
            c.row_factory=sqlite3.Row
            return [dict(x) for x in c.execute("SELECT * FROM signals WHERE status='OPEN' AND instrument_id IS NOT NULL ORDER BY signal_at ASC LIMIT ?", (limit,))]

    def signals(self, limit=100):
        with self.lock, self._connect() as c:
            c.row_factory=sqlite3.Row
            rows=[dict(x) for x in c.execute('SELECT * FROM signals ORDER BY signal_at DESC LIMIT ?', (min(500,max(1,int(limit))),))]
        for r in rows:r['reasons']=json.loads(r['reasons'])
        return rows

    def outcome(self, signal_id, outcome, outcome_at, exit_price, costs=0):
        """One-way, evidence-backed outcome update. Never overwrite a closed result."""
        if outcome not in ('T1','T2','SL','EXPIRED'): raise ValueError('Invalid outcome')
        with self.lock, self._connect() as c:
            cur=c.execute("UPDATE signals SET status=?,outcome_at=?,exit_price=?,costs=? WHERE id=? AND status='OPEN'",
                (outcome,outcome_at,float(exit_price),float(costs),int(signal_id)))
            return cur.rowcount==1

    def stats(self):
        with self.lock,self._connect() as c:
            c.row_factory=sqlite3.Row
            rows=[dict(r) for r in c.execute('''SELECT strategy,COUNT(*) total, SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) open_count,
             SUM(CASE WHEN status IN ('T1','T2') THEN 1 ELSE 0 END) wins,
             SUM(CASE WHEN status='SL' THEN 1 ELSE 0 END) losses,
             SUM(CASE WHEN status='EXPIRED' THEN 1 ELSE 0 END) expired
             FROM signals GROUP BY strategy''')]
        for x in rows:
            denomin=(x['wins'] or 0)+(x['losses'] or 0)+(x['expired'] or 0)
            x['win_rate']=round((x['wins'] or 0)/denomin*100,2) if denomin else None
        return rows

    def save_backtest(self, result):
        names=('strategy','version','tested_at','samples','win_rate','profit_factor','drawdown_pct','avg_r','net_r','eligible','notes')
        with self.lock,self._connect() as c:
            c.execute('REPLACE INTO backtests VALUES ('+','.join('?' for _ in names)+')', tuple(result.get(k) for k in names))

    def backtests(self):
        with self.lock,self._connect() as c:
            c.row_factory=sqlite3.Row
            return [dict(x) for x in c.execute('SELECT * FROM backtests ORDER BY strategy')]
