from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
import subprocess
import sys
import time

import pytest

from live_demo.metrics import Metrics, DAY
from live_demo.service import Sessions, Unavailable
from live_demo.server import API
from test_live_demo import Bot, begin, callback, request, wait_for


@pytest.fixture
def measured(tmp_path):
    svc = Sessions(tmp_path, Bot(), 'zippergen_demo_bot', metrics_enabled=True)
    svc.healthy = True
    svc.last_poll = svc.last_delivery = time.time()
    yield svc
    svc.close()


def totals(metrics):
    with closing(metrics.connect()) as db:
        return dict(db.execute('SELECT event,SUM(count) FROM metric_totals GROUP BY event'))


def event(api, name='demo_opened', attempt='a'*32, **kwargs):
    return request(api, 'POST', '/api/metrics', body=json.dumps({'event': name, 'attempt': attempt}).encode(), **kwargs)


def test_browser_reloads_and_concurrent_deliveries_count_once(measured):
    api = API(measured, ['https://zippergen.io'])
    with ThreadPoolExecutor(8) as pool:
        assert all(result[0].startswith('200') for result in pool.map(lambda _: event(api), range(8)))
    event(api, 'first_command')
    event(api, attempt='b'*32)
    assert totals(measured.metrics) == {'demo_opened': 2, 'first_command': 1}
    with closing(measured.metrics.connect()) as db:
        receipts = db.execute('SELECT * FROM metric_receipts').fetchall()
    assert len(receipts) == 3
    assert 'a'*32 not in json.dumps(receipts)
    assert 'test-visitor' not in json.dumps(receipts)


def test_metrics_api_rejects_extra_data_and_server_events(measured):
    api = API(measured, ['https://zippergen.io', 'http://localhost:8765'])
    for body in [b'{"event":"demo_opened","attempt":"secret","text":"message"}', b'[]',
                 b'{"event":[],"attempt":"x"}', b'not json']:
        assert request(api, 'POST', '/api/metrics', body=body)[0].startswith('400')
    assert event(api, 'telegram_approved')[0].startswith('400')
    assert event(api, attempt='x')[0].startswith('400')
    assert request(api, 'POST', '/api/metrics', body=b'x'*193)[0].startswith('413')
    assert event(api, origin='https://evil.example')[0].startswith('403')
    assert event(api, origin='http://localhost:8765')[0].startswith('403')
    assert event(api, origin='')[0].startswith('403')
    assert event(api, CONTENT_TYPE='text/plain')[0].startswith('415')
    assert request(api, 'GET', '/api/metrics')[0].startswith('404')
    assert totals(measured.metrics) == {}


@pytest.mark.parametrize('headers', [{'QUERY_STRING':'measurement=off'}, {'HTTP_X_DEMO_MEASUREMENT':'off'}, {'HTTP_DNT':'1'}, {'HTTP_SEC_GPC':'1'}])
def test_opt_out_prevents_browser_and_live_counts(measured, headers):
    api = API(measured, ['https://zippergen.io'])
    assert event(api, **headers)[0].startswith('403')
    assert request(api, 'POST', '/api/sessions', **headers)[0].startswith('201')
    measured.tick()
    assert totals(measured.metrics) == {}


def test_opt_out_suppresses_further_counts_on_existing_live_run(measured):
    session = begin(measured)
    measured.tick()
    api = API(measured, ['https://zippergen.io'])
    request(api, 'GET', '/api/session', token=session['token'], HTTP_X_DEMO_MEASUREMENT='off')
    measured.process_update(callback(measured))
    wait_for(lambda: measured.result(measured.rows()[0]) == 'approved')
    measured.tick()
    assert totals(measured.metrics) == {'telegram_created': 1, 'telegram_connected': 1}


@pytest.mark.parametrize('yes, outcome', [(True, 'approved'), (False, 'rejected')])
def test_telegram_completion_counted_without_browser_and_survives_restart(measured, yes, outcome):
    begin(measured)
    measured.process_update(callback(measured, yes=yes))
    wait_for(lambda: measured.result(measured.rows()[0]) == outcome)
    # No status polling by a browser is involved in counting the terminal state.
    measured.tick()
    measured.tick()
    expected = {'telegram_created': 1, 'telegram_connected': 1, 'telegram_'+outcome: 1}
    assert totals(measured.metrics) == expected
    measured.close()
    resumed = Sessions(measured.directory, Bot(), 'zippergen_demo_bot', metrics_enabled=True)
    try:
        resumed.tick()
        assert totals(resumed.metrics) == expected
        resumed.clock = lambda: time.time() + 4000
        resumed.tick()
        assert resumed.rows() == []
        assert totals(resumed.metrics) == expected
    finally:
        resumed.close()


def test_old_schema_migrates_without_retroactive_counts(tmp_path):
    path = tmp_path / 'sessions.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY, reader TEXT, start TEXT, created REAL, expires REAL, '
                   'chat TEXT, actor TEXT, notified INTEGER DEFAULT 0, failed INTEGER DEFAULT 0)')
        db.execute('INSERT INTO sessions(id,reader,start,created,expires) VALUES(?,?,?,?,?)',
                   ('a'*32, 'reader', 'start', time.time(), time.time()+1800))
    svc = Sessions(tmp_path, Bot(), 'zippergen_demo_bot', metrics_enabled=True)
    try:
        svc.tick()
        assert svc.rows()[0]['measured'] == 0
        assert totals(svc.metrics) == {}
    finally:
        svc.close()


def test_disabled_service_records_nothing_and_local_requests_are_excluded(measured):
    api = API(measured, ['https://zippergen.io', 'http://localhost:8765'])
    assert request(api, 'POST', '/api/sessions', origin='http://localhost:8765')[0].startswith('201')
    measured.tick()
    assert totals(measured.metrics) == {}
    measured.metrics = None
    assert event(api)[0].startswith('403')
    assert request(api, 'GET', '/api/config')[2]['metrics_enabled'] is False


def test_distinct_capacity_rate_and_unavailable_counts(measured):
    measured.limit = 1
    measured.starts_per_hour = 1
    measured.create('same')
    with pytest.raises(Unavailable): measured.create('same')
    with pytest.raises(Unavailable): measured.create('other')
    measured.healthy = False
    with pytest.raises(Unavailable): measured.create('third')
    counts = totals(measured.metrics)
    assert counts['live_rate_refused'] == counts['live_capacity_refused'] == counts['live_unavailable'] == 1


def test_retention_and_rate_limit_are_bounded(tmp_path):
    now = [time.time()]
    metrics = Metrics(tmp_path / 'usage.sqlite', clock=lambda: now[0])
    for _ in range(120):
        assert metrics.browser('demo_opened', 'a'*32, 'source')
    assert not metrics.browser('demo_opened', 'b'*32, 'source')
    now[0] += 61
    metrics.prune()
    assert metrics.sources == {}
    assert metrics.browser('demo_opened', 'b'*32, 'source')
    now[0] += DAY + 1
    metrics.prune()
    with closing(metrics.connect()) as db:
        assert db.execute('SELECT count(*) FROM metric_receipts').fetchone()[0] == 0
    assert totals(metrics) == {'demo_opened': 2}
    now[0] += 90*DAY
    metrics.prune()
    assert totals(metrics) == {}


def test_full_metrics_database_does_not_break_live_session(measured, monkeypatch):
    def broken(): raise sqlite3.OperationalError('disk full')
    monkeypatch.setattr(measured.metrics, 'connect', broken)
    assert measured.create('visitor')['state'] == 'connecting'
    measured.tick()


def test_report_contains_only_aggregate_counts(measured):
    measured.metrics.browser('demo_opened', 'a'*32, 'private-address')
    result = subprocess.run([sys.executable, '-m', 'live_demo.metrics', '--state', str(measured.directory), '--json'],
                            capture_output=True, text=True, check=True)
    value = json.loads(result.stdout)
    assert value['totals']['demo_opened'] == 1
    assert set(value) == {'since_utc', 'totals', 'daily'}
    assert 'a'*32 not in result.stdout and 'private-address' not in result.stdout
