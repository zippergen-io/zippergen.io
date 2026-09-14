"""Bounded daily usage totals. No public report endpoint or raw event log."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import argparse
import hashlib
import json
import logging
from pathlib import Path
import re
import sqlite3
import threading
import time

BROWSER_EVENTS = frozenset({
    'demo_opened', 'first_command', 'deployment_reached', 'simulation_completed',
    'telegram_requested', 'github_clicked',
})
SERVER_EVENTS = frozenset({
    'telegram_created', 'telegram_connected', 'telegram_approved', 'telegram_rejected',
    'live_capacity_refused', 'live_rate_refused', 'live_unavailable',
})
EVENTS = tuple(sorted(BROWSER_EVENTS | SERVER_EVENTS))
ATTEMPT = re.compile(r'[a-f0-9]{32}\Z')
DAY = 86400


class Metrics:
    def __init__(self, path, *, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.lock = threading.Lock()
        self.sources = {}
        with closing(self.connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metric_totals (
                    day TEXT NOT NULL, event TEXT NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(day,event)
                );
                CREATE TABLE IF NOT EXISTS metric_receipts (
                    receipt TEXT PRIMARY KEY, expires REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS metric_receipt_expiry ON metric_receipts(expires);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        db.execute('PRAGMA secure_delete=ON')
        return db

    def _increment(self, db, event):
        day = datetime.fromtimestamp(self.clock(), timezone.utc).date().isoformat()
        db.execute('INSERT INTO metric_totals VALUES(?,?,1) '
                   'ON CONFLICT(day,event) DO UPDATE SET count=count+1', (day, event))

    def _prune(self, db):
        now = self.clock()
        cutoff = (datetime.fromtimestamp(now, timezone.utc).date() - timedelta(days=89)).isoformat()
        db.execute('DELETE FROM metric_receipts WHERE expires<=?', (now,))
        db.execute('DELETE FROM metric_totals WHERE day<?', (cutoff,))

    def prune(self):
        with self.lock:
            self.sources = {key: value for key, value in self.sources.items() if value[0] > self.clock()}
        try:
            with closing(self.connect()) as db:
                self._prune(db)
        except sqlite3.Error:
            logging.warning('Usage count cleanup is unavailable.')

    def browser(self, event, attempt, source):
        if event not in BROWSER_EVENTS or not isinstance(attempt, str) or not ATTEMPT.fullmatch(attempt):
            raise ValueError('Invalid usage event')
        # Only a short-lived abuse counter uses the source address. No address
        # reaches SQLite, and the in-memory map is bounded against random sources.
        now = self.clock()
        with self.lock:
            self.sources = {key: value for key, value in self.sources.items() if value[0] > now}
            key = hashlib.sha256(source.encode()).digest()
            if key not in self.sources and len(self.sources) >= 1024:
                return False
            expires, count = self.sources.get(key, (now + 60, 0))
            if count >= 120:
                return False
            self.sources[key] = (expires, count + 1)
        receipt = hashlib.sha256((event + ':' + attempt).encode()).hexdigest()
        try:
            with closing(self.connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                self._prune(db)
                # Six fixed milestone types and a fixed bound on retained receipts.
                if db.execute('SELECT count(*) FROM metric_receipts').fetchone()[0] >= 60000:
                    db.rollback()
                    return False
                inserted = db.execute('INSERT OR IGNORE INTO metric_receipts VALUES(?,?)',
                                      (receipt, now + DAY)).rowcount
                if inserted:
                    self._increment(db, event)
                db.commit()
            return True
        except sqlite3.Error:
            logging.warning('Usage counts are unavailable.')
            return False

    def increment(self, event):
        if event not in SERVER_EVENTS:
            raise ValueError('Invalid server usage event')
        try:
            with closing(self.connect()) as db:
                self._increment(db, event)
        except sqlite3.Error:
            logging.warning('Usage counts are unavailable.')

    def session(self, sid, event, bit):
        """Count a server transition and its receipt in one transaction.

        The receipt stays on the existing short-lived operational session, not
        in the analytics report. Old sessions default to measurement disabled.
        """
        if event not in SERVER_EVENTS:
            raise ValueError('Invalid server usage event')
        try:
            with closing(self.connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                updated = db.execute('UPDATE sessions SET metrics_mask=metrics_mask|? '
                                     'WHERE id=? AND measured=1 AND (metrics_mask & ?)=0',
                                     (bit, sid, bit)).rowcount
                if updated:
                    self._increment(db, event)
                db.commit()
        except sqlite3.Error:
            logging.warning('Usage counts are unavailable.')


def main():
    parser = argparse.ArgumentParser(description='Read aggregate demo usage counts. No session identities are displayed.')
    parser.add_argument('--state', default='/var/lib/zippergen-demo')
    parser.add_argument('--days', type=int, choices=range(1, 91), default=7, metavar='1-90')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    path = Path(args.state).resolve() / 'sessions.sqlite'
    if not path.exists():
        parser.exit(1, 'No demo state database found.\n')
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=args.days - 1)).isoformat()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='metric_totals'").fetchone():
            parser.exit(1, 'Usage counting has not been enabled yet.\n')
        rows = db.execute('SELECT day,event,count FROM metric_totals WHERE day>=? ORDER BY day,event', (cutoff,)).fetchall()
    totals = {event: sum(n for _, e, n in rows if e == event) for event in EVENTS}
    if args.json:
        print(json.dumps({'since_utc': cutoff, 'totals': totals,
                          'daily': [dict(day=d, event=e, count=n) for d, e, n in rows]}, indent=2))
    else:
        print(f'Demo usage since {cutoff} (UTC, including today)')
        print('Browser counts are attempts. Telegram counts are sessions. Refusals are requests.\n')
        for event, count in totals.items():
            print(f'{event:26} {count:8d}')
        print('\nNo exact visitor count or cross-day conversion rate is implied.')


if __name__ == '__main__':
    main()
