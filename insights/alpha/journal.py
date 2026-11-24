"""Append-only research journal, separate from the application's Track Record.

SQLite transactions serialize writers. A hash chain detects accidental edits;
it is not tamper-proof against an administrator rewriting the complete database.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class ResearchJournal:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL)')
        self.db.execute("CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append-only'); END")
        self.db.execute("CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append-only'); END")
        self.db.commit()

    def close(self):
        self.db.close()

    def append(self, event_id, payload):
        if not isinstance(event_id, str) or not event_id.strip() or not isinstance(payload, dict):
            raise ValueError('Event ID and JSON object required')
        encoded = canonical(payload)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            existing = self.db.execute('SELECT payload,digest FROM events WHERE event_id=?', (event_id,)).fetchone()
            if existing:
                if existing[0] != encoded:
                    raise ValueError('Conflicting immutable event')
                self.db.commit()
                return existing[1]
            last = self.db.execute('SELECT seq,digest FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            seq, previous = (last[0]+1, last[1]) if last else (1, '0'*64)
            digest = hashlib.sha256(canonical([seq, event_id, encoded, previous]).encode()).hexdigest()
            self.db.execute('INSERT INTO events VALUES (?,?,?,?,?)', (seq, event_id, encoded, previous, digest))
            self.db.commit()
            return digest
        except Exception:
            self.db.rollback()
            raise

    def verify(self):
        previous, expected = '0'*64, 1
        for seq, event_id, payload, prior, digest in self.db.execute('SELECT * FROM events ORDER BY seq'):
            if seq != expected or prior != previous or digest != hashlib.sha256(canonical([seq, event_id, payload, prior]).encode()).hexdigest():
                return False
            previous, expected = digest, expected+1
        return True
