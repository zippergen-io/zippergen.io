"""Bounded sessions around ZipperGen's durable runner and Telegram notifier."""
from __future__ import annotations

from contextlib import closing
import fcntl
import hashlib
import logging
import math
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
import time

from zippergen import LocalSupervisor
from zippergen.store import load_workflow_result, open_store
from zippergen.telegram_inbox import SETTLED, RETRY, bot_fingerprint, consume_once, fetch_once
from zippergen.telegram_notify import TelegramNotifier
from .workflow import telegram_approval, REQUEST, DRAFT

log = logging.getLogger(__name__)
TOKEN = re.compile(r"[A-Za-z0-9_-]{32}\Z")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Unavailable(Exception):
    pass


class Gone(Exception):
    pass


class Sessions:
    def __init__(self, directory, client, bot_name, *, lifetime=1800, limit=12, starts_per_hour=5, clock=time.time, metrics_enabled=False):
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", bot_name):
            raise ValueError("Invalid bot username")
        if not 60 <= lifetime <= 3600 or not 1 <= limit <= 32:
            raise ValueError("Expected a lifetime of 60–3600 seconds and 1–32 sessions")
        if not 1 <= starts_per_hour <= 1000:
            raise ValueError("Expected 1–1000 starts per IP address per hour")
        self.starts_per_hour = starts_per_hour
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.client, self.bot_name = client, bot_name
        self.lifetime, self.limit, self.clock = lifetime, limit, clock
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.workers = {}
        self.poller = None
        self.delivery_retries = {}
        self.healthy = False
        self.last_poll = 0.0
        self.last_delivery = 0.0
        self.owner = (self.directory / 'service.lock').open('a')
        try:
            fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.owner.close()
            raise RuntimeError("Only one demo backend may use this state directory") from None
        with closing(self.connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, reader TEXT UNIQUE NOT NULL,
                    start TEXT UNIQUE NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
                    chat TEXT, actor TEXT, notified INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS starts (
                    source TEXT NOT NULL, at REAL NOT NULL
                );
            ''')

        with closing(self.connect()) as db:
            columns = {row[1] for row in db.execute('PRAGMA table_info(sessions)')}
            for column in ('measured', 'metrics_mask'):
                if column not in columns:
                    db.execute(f'ALTER TABLE sessions ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0')
        self.metrics = None
        if metrics_enabled:
            from .metrics import Metrics
            try:
                self.metrics = Metrics(self.directory / 'sessions.sqlite', clock=self.clock)
            except sqlite3.Error:
                log.warning('Usage counts could not be initialized. The demo will continue without them.')

    def connect(self):
        db = sqlite3.connect(self.directory / 'sessions.sqlite', timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA secure_delete=ON')
        return db

    def path(self, session):
        return self.directory / session['id'] / 'workflow.sqlite'

    def rows(self):
        with closing(self.connect()) as db:
            return db.execute('SELECT * FROM sessions ORDER BY created').fetchall()

    def create(self, source, *, measure=True):
        with self.lock, closing(self.connect()) as db:
            if not self.available():
                if measure and self.metrics:
                    self.metrics.increment('live_unavailable')
                raise Unavailable('The live demo is temporarily unavailable. Please use the preview.')
            now = self.clock()
            db.execute('DELETE FROM starts WHERE at <= ?', (now - 3600,))
            source = digest(source)
            count = db.execute('SELECT count(*) FROM sessions').fetchone()[0]
            recent = db.execute('SELECT count(*) FROM starts WHERE source=?', (source,)).fetchone()[0]
            if recent >= self.starts_per_hour:
                if measure and self.metrics:
                    self.metrics.increment('live_rate_refused')
                oldest = db.execute('SELECT at FROM starts WHERE source=? ORDER BY at LIMIT 1 OFFSET ?',
                                    (source, recent - self.starts_per_hour)).fetchone()[0]
                minutes = max(1, math.ceil((oldest + 3600 - now) / 60))
                raise Unavailable(f'This network has reached the limit of {self.starts_per_hour} new sessions per hour. '
                                  f'Try again in about {minutes} minute(s), or use the preview.')
            if count >= self.limit:
                if measure and self.metrics:
                    self.metrics.increment('live_capacity_refused')
                expiry = db.execute('SELECT expires FROM sessions ORDER BY expires LIMIT 1 OFFSET ?',
                                    (count - self.limit,)).fetchone()[0]
                minutes = max(1, math.ceil((expiry - now) / 60))
                raise Unavailable(f'All {self.limit} demo session slots are occupied. '
                                  f'The next slot should open in about {minutes} minute(s). You can use the preview meanwhile.')
            sid, reader, start = (secrets.token_urlsafe(24) for _ in range(3))
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('INSERT INTO sessions(id,reader,start,created,expires,measured) VALUES(?,?,?,?,?,?)',
                           (sid, digest(reader), digest(start), now, now + self.lifetime, int(measure and self.metrics is not None)))
                db.execute('INSERT INTO starts VALUES(?,?)', (source, now))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise
            if self.metrics:
                self.metrics.session(sid, 'telegram_created', 1)
            return {'token': reader, 'telegram_url': f'https://t.me/{self.bot_name}?start={start}',
                    'expires_at': now + self.lifetime, 'state': 'connecting'}

    def available(self):
        now = self.clock()
        return self.healthy and now - self.last_poll < 60 and now - self.last_delivery < 60

    def result(self, row):
        if not self.path(row).exists():
            return None
        with closing(open_store(str(self.path(row)))) as db:
            return load_workflow_result(db, telegram_approval.name)

    def status(self, reader, *, suppress_metrics=False):
        if not TOKEN.fullmatch(reader):
            raise Gone()
        with self.lock, closing(self.connect()) as db:
            row = db.execute('SELECT * FROM sessions WHERE reader=?', (digest(reader),)).fetchone()
            if row is None or row['expires'] <= self.clock():
                raise Gone()
            if suppress_metrics:
                db.execute('UPDATE sessions SET measured=0 WHERE id=?', (row['id'],))
            result = self.result(row)
            state = result if result is not None else 'error' if row['failed'] else 'connecting'
            if result is None and not row['failed'] and row['chat']:
                state = 'starting'
                if self.path(row).exists():
                    with closing(open_store(str(self.path(row)))) as store:
                        task = store.execute('SELECT status FROM human_tasks LIMIT 1').fetchone()
                        if task:
                            state = 'continuing' if task[0] == 'done' else 'waiting'
            return {'state': state, 'expires_at': row['expires'], 'draft': DRAFT,
                    'available': self.available() and row['id'] not in self.delivery_retries}

    def notifier(self, row):
        return TelegramNotifier(str(self.path(row)), self.client, row['chat'], allowed_user_id=row['actor'])

    def process_update(self, update):
        # Only a dedicated demo bot uses this service. Unknown updates are discarded.
        with self.lock:
            message = update.get('message') or {}
            chat, actor = message.get('chat') or {}, message.get('from') or {}
            match = re.fullmatch(r'/start(?:@[A-Za-z0-9_]+)? ([A-Za-z0-9_-]{32})', message.get('text', ''))
            if match and chat.get('type') == 'private' and str(chat.get('id')) == str(actor.get('id')) and not actor.get('is_bot'):
                with closing(self.connect()) as db:
                    row = db.execute('SELECT * FROM sessions WHERE start=? AND expires>?',
                                     (digest(match[1]), self.clock())).fetchone()
                    if row and (not row['chat'] or row['chat'] == str(chat['id'])):
                        db.execute('UPDATE sessions SET chat=?,actor=? WHERE id=? AND chat IS NULL',
                                   (str(chat['id']), str(actor['id']), row['id']))
                return SETTLED
            if update.get('callback_query'):
                for row in self.rows():
                    if row['chat'] and row['expires'] > self.clock() and self.path(row).exists():
                        outcome = self.notifier(row).process_update(update)
                        if outcome in (SETTLED, RETRY):
                            return outcome
                # No current run owns it, including expired sessions.
                callback_id = update['callback_query'].get('id')
                if callback_id:
                    try:
                        self.client.answer_callback_query(str(callback_id), 'This demo session is no longer available.')
                    except Exception:
                        pass
            return SETTLED

    def launch(self, row):
        if row['id'] in self.workers or row['failed'] or self.result(row) is not None:
            return
        self.path(row).parent.mkdir(mode=0o700, exist_ok=True)
        supervisor = LocalSupervisor(telegram_approval, None, {'Mailbox': {'message': REQUEST}},
                                     store_path=str(self.path(row)), timeout=0)

        def run():
            try:
                supervisor.run()
            except Exception:
                if not self.stop.is_set():
                    log.error('A demo workflow failed. Inspect its private workflow store.')
                    with closing(self.connect()) as db:
                        db.execute('UPDATE sessions SET failed=1 WHERE id=?', (row['id'],))
        worker = threading.Thread(target=run, name='demo-workflow', daemon=True)
        self.workers[row['id']] = (supervisor, worker)
        worker.start()

    def record_usage(self, row):
        if not self.metrics or not row['measured']:
            return
        if not row['metrics_mask'] & 1:
            self.metrics.session(row['id'], 'telegram_created', 1)
        if row['chat'] and not row['metrics_mask'] & 2:
            self.metrics.session(row['id'], 'telegram_connected', 2)
        result = self.result(row)
        if result in ('approved', 'rejected') and not row['metrics_mask'] & 4:
            self.metrics.session(row['id'], 'telegram_' + result, 4)

    def tick(self):
        now = self.clock()
        for row in self.rows():
            with self.lock:
                self.record_usage(row)
                if row['expires'] <= now:
                    worker = self.workers.get(row['id'])
                    if worker:
                        worker[0].stop.set()
                        worker[1].join(timeout=2)
                        if worker[1].is_alive():
                            continue
                        del self.workers[row['id']]
                    self.record_usage(row)
                    if self.path(row).parent.exists():
                        shutil.rmtree(self.path(row).parent)
                    with closing(self.connect()) as db:
                        db.execute('DELETE FROM sessions WHERE id=?', (row['id'],))
                    self.delivery_retries.pop(row['id'], None)
                    continue
                if not row['chat']:
                    continue
                self.launch(row)
            # Network I/O must not hold the session lock or block status requests.
            if self.delivery_retries.get(row['id'], 0) > now:
                continue
            try:
                if self.path(row).exists() and not row['failed']:
                    self.notifier(row).send_pending_once()
                result = self.result(row)
                if result is not None and not row['notified']:
                    text = ('Approved. The workflow released the example reply.' if result == 'approved'
                            else 'Rejected. The workflow discarded the example reply.')
                    self.client.send_message(row['chat'], text + '\n\nThe run is complete. No email was sent. You can return to the demo page.')
                    with closing(self.connect()) as db:
                        db.execute('UPDATE sessions SET notified=1 WHERE id=?', (row['id'],))
                self.delivery_retries.pop(row['id'], None)
            except Exception:
                self.delivery_retries[row['id']] = self.clock() + 30
                log.warning('A demo notification could not be delivered. Retrying in 30 seconds.')
        with closing(self.connect()) as db:
            db.execute('DELETE FROM starts WHERE at <= ?', (now - 3600,))
        if self.metrics:
            self.metrics.prune()
        self.last_delivery = self.clock()

    def start(self):
        def poll():
            fingerprint = bot_fingerprint(self.client.token)
            while not self.stop.is_set():
                try:
                    fetch_once(self.client, fingerprint, timeout=5)
                    consume_once(fingerprint, self.process_update)
                    self.last_poll = self.clock()
                except Exception:
                    self.healthy = False
                    log.warning('Telegram polling is unavailable. Retrying shortly.')
                    self.stop.wait(5)
        self.poller = threading.Thread(target=poll, name='demo-telegram', daemon=True)
        self.poller.start()

        def maintain():
            while not self.stop.is_set():
                try:
                    self.tick()
                    self.healthy = True
                except Exception:
                    self.healthy = False
                    log.warning('Demo maintenance is unavailable. Retrying shortly.')
                self.stop.wait(1)
        self.maintenance = threading.Thread(target=maintain, name='demo-maintenance', daemon=True)
        self.maintenance.start()

    def close(self):
        self.stop.set()
        if self.poller:
            self.poller.join(timeout=20)
            self.maintenance.join(timeout=25)
        with self.lock:
            for supervisor, worker in self.workers.values():
                supervisor.stop.set()
            for supervisor, worker in self.workers.values():
                worker.join(timeout=3)
        self.owner.close()
