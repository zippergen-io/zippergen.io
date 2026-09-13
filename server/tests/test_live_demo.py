from contextlib import closing
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from zippergen.store import open_store, list_history
from live_demo.service import Sessions, Gone, Unavailable
from live_demo.server import API


class Bot:
    token = 'fake-test-token'

    def __init__(self):
        self.sent = []
        self.answers = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        return {'result': {'message_id': len(self.sent)}}

    def answer_callback_query(self, callback_query_id, text=None):
        self.answers.append(text)

    def edit_message_reply_markup(self, **kwargs):
        pass


@pytest.fixture
def service(tmp_path):
    svc = Sessions(tmp_path, Bot(), 'zippergen_demo_bot')
    svc.healthy = True
    svc.last_poll = svc.last_delivery = time.time()
    yield svc
    svc.close()


def wait_for(predicate, timeout=8):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        value = predicate()
        if value:
            return value
        time.sleep(.02)
    raise AssertionError('Timed out waiting for workflow state')


def begin(svc, source='visitor', actor=123):
    session = svc.create(source)
    start = session['telegram_url'].split('start=')[1]
    svc.process_update({'message': {'text': '/start ' + start, 'chat': {'id': actor, 'type': 'private'}, 'from': {'id': actor}}})
    svc.tick()
    wait_for(lambda: svc.status(session['token'])['state'] == 'waiting')
    svc.tick()
    return session


def callback(svc, *, actor=123, yes=True, chat=None, index=-1):
    message = [item for item in svc.client.sent if item[2]][index]
    data = message[2]['inline_keyboard'][0][0 if yes else 1]['callback_data']
    return {'callback_query': {'id': 'callback', 'data': data, 'from': {'id': actor},
            'message': {'message_id': 1, 'chat': {'id': actor if chat is None else chat, 'type': 'private'}}}}


@pytest.mark.parametrize('yes,expected', [(True, 'approved'), (False, 'rejected')])
def test_real_runner_decisions_and_duplicate_callbacks(service, yes, expected):
    session = begin(service)
    update = callback(service, yes=yes)
    service.process_update(update)
    wait_for(lambda: service.status(session['token'])['state'] == expected)
    service.tick()
    sent = len(service.client.sent)
    service.process_update(callback(service, yes=not yes))
    service.tick()
    assert service.status(session['token'])['state'] == expected
    assert len(service.client.sent) == sent
    row = service.rows()[0]
    with closing(open_store(str(service.path(row)))) as db:
        assert db.execute("SELECT count(*) FROM human_tasks WHERE status='done'").fetchone()[0] == 1
        events = list_history(db)
        text = json.dumps(events)
        assert ('release_reply' if yes else 'discard_reply') in text
    assert 'No email was sent' in service.client.sent[-1][1]


def test_private_chat_binding_and_actor_isolation(service):
    first = begin(service)
    second = begin(service, 'second', actor=456)
    start = first['telegram_url'].split('start=')[1]
    service.process_update({'message': {'text': '/start ' + start, 'chat': {'id': 456, 'type': 'private'}, 'from': {'id': 456}}})
    service.process_update(callback(service, actor=456, chat=123, index=0))
    service.process_update(callback(service, actor=123, chat=456, index=0))
    assert service.status(first['token'])['state'] == 'waiting'
    assert service.status(second['token'])['state'] == 'waiting'
    service.process_update(callback(service, actor=123, index=0))
    wait_for(lambda: service.status(first['token'])['state'] == 'approved')
    assert service.status(second['token'])['state'] == 'waiting'


def test_group_start_does_not_bind(service):
    s = service.create('a')
    start = s['telegram_url'].split('start=')[1]
    service.process_update({'message': {'text': '/start ' + start, 'chat': {'id': 123, 'type': 'group'}, 'from': {'id': 123}}})
    assert service.status(s['token'])['state'] == 'connecting'


def test_expiry_deletes_state_and_rejects_saved_buttons(service):
    session = begin(service)
    stale = callback(service)
    path = service.path(service.rows()[0])
    service.clock = lambda: session['expires_at'] + 1
    with pytest.raises(Gone):
        service.status(session['token'])
    service.process_update(stale)
    service.tick()
    assert not path.parent.exists()
    assert not service.rows()


def test_limits_and_credentials_do_not_leak(service):
    for _ in range(5):
        service.create('same-address')
    with pytest.raises(Unavailable):
        service.create('same-address')
    raw = (service.directory / 'sessions.sqlite').read_bytes()
    assert b'same-address' not in raw
    assert b'fake-test-token' not in raw
    with pytest.raises(Gone):
        service.status('../../etc/passwd')
    service.limit = 5
    with pytest.raises(Unavailable):
        service.create('another-address')


def test_single_process_owner(service):
    with pytest.raises(RuntimeError, match='Only one'):
        Sessions(service.directory, Bot(), 'zippergen_demo_bot')


def test_restart_in_fresh_process_keeps_task_and_result(service, tmp_path):
    session = begin(service)
    update = callback(service, yes=False)
    row = service.rows()[0]
    with closing(open_store(str(service.path(row)))) as db:
        old_task = db.execute('SELECT task_id FROM human_tasks').fetchone()[0]
    service.close()
    code = '''
import json, sys, time
from contextlib import closing
from live_demo.service import Sessions
from zippergen.store import open_store
class Bot:
    token='fake-test-token'
    def send_message(self, *a, **kw): return {'result': {'message_id': 2}}
    def answer_callback_query(self, *a, **kw): pass
    def edit_message_reply_markup(self, **kw): pass
svc=Sessions(sys.argv[1], Bot(), 'zippergen_demo_bot')
svc.process_update(json.loads(sys.argv[3]))
svc.tick()
end=time.monotonic()+8
while time.monotonic()<end and svc.status(sys.argv[2])['state'] != 'rejected': time.sleep(.02)
assert svc.status(sys.argv[2])['state']=='rejected'
with closing(open_store(str(svc.path(svc.rows()[0])))) as db:
    assert db.execute('SELECT task_id FROM human_tasks').fetchone()[0]==sys.argv[4]
svc.close()
'''
    subprocess.run([sys.executable, '-c', code, str(service.directory), session['token'], json.dumps(update), old_task], check=True, timeout=20)


def request(api, method, path, *, token=None, origin='https://zippergen.io', body=b'{}', **overrides):
    env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'HTTP_ORIGIN': origin,
           'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(body)),
           'wsgi.input': BytesIO(body), 'REMOTE_ADDR': 'test-visitor'}
    if token:
        env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
    env.update(overrides)
    response = []
    payload = b''.join(api(env, lambda status, headers: response.extend([status, dict(headers)])))
    return response[0], response[1], json.loads(payload)


def test_api_boundaries_and_read_only_live_status(service):
    api = API(service, ['https://zippergen.io'])
    assert request(api, 'POST', '/api/sessions', origin='https://evil.example')[0].startswith('403')
    assert request(api, 'POST', '/api/sessions', origin='')[0].startswith('403')
    assert request(api, 'POST', '/api/sessions', body=b'x' * 65)[0].startswith('413')
    assert request(api, 'POST', '/api/sessions', body=b'{"draft":"custom"}')[0].startswith('400')
    status, headers, session = request(api, 'POST', '/api/sessions')
    assert status.startswith('201') and headers['Cache-Control'] == 'no-store'
    assert headers['Access-Control-Allow-Origin'] == 'https://zippergen.io'
    assert request(api, 'GET', '/api/session')[0].startswith('401')
    assert request(api, 'POST', '/api/session', token=session['token'])[0].startswith('404')
    assert request(api, 'GET', '/api/session', token='x' * 32)[0].startswith('410')
    assert request(api, 'GET', '/api/session', token=session['token'])[2]['state'] == 'connecting'
    assert 'telegram_url' not in request(api, 'GET', '/api/session', token=session['token'])[2]


def test_twelve_pending_runs(service):
    sessions = [begin(service, source=f'visitor-{i}', actor=i+1000) for i in range(12)]
    assert len(service.workers) == 12
    assert all(service.status(s['token'])['state'] == 'waiting' for s in sessions)
    with pytest.raises(Unavailable):
        service.create('one-more')


def test_broken_chat_does_not_block_other_deliveries(service):
    first = begin(service)
    original = service.client.send_message
    def send(chat_id, text, reply_markup=None):
        if chat_id == '123':
            raise OSError('fake delivery failure')
        return original(chat_id, text, reply_markup)
    service.client.send_message = send
    service.process_update(callback(service))
    wait_for(lambda: service.status(first['token'])['state'] == 'approved')
    second = begin(service, source='another', actor=456)
    assert service.status(second['token'])['state'] == 'waiting'
    assert any(m[0] == '456' and m[2] for m in service.client.sent)
    assert not service.status(first['token'])['available']


def test_abrupt_process_death_resumes_pending_run(tmp_path):
    code = '''
import json, sys, time
from live_demo.service import Sessions
class Bot:
    token='fake-test-token'
    def send_message(self,*a,**k): return {'result':{'message_id':1}}
svc=Sessions(sys.argv[1],Bot(),'zippergen_demo_bot')
svc.healthy=True
svc.last_poll=svc.last_delivery=time.time()
s=svc.create('visitor')
svc.process_update({'message': {'text':'/start '+s['telegram_url'].split('start=')[1], 'chat':{'id':123,'type':'private'},'from':{'id':123}}})
svc.tick()
while svc.status(s['token'])['state']!='waiting': time.sleep(.02)
print(json.dumps(s),flush=True)
time.sleep(60)
'''
    process = subprocess.Popen([sys.executable, '-c', code, str(tmp_path)], stdout=subprocess.PIPE, text=True)
    try:
        import selectors
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=10), 'Worker did not reach pending approval'
        session = json.loads(process.stdout.readline())
        selector.close()
    finally:
        process.kill()
        process.wait(timeout=5)
    svc = Sessions(tmp_path, Bot(), 'zippergen_demo_bot')
    try:
        assert svc.status(session['token'])['state'] == 'waiting'
        svc.tick()
        svc.process_update(callback(svc))
        wait_for(lambda: svc.status(session['token'])['state'] == 'approved')
        with closing(open_store(str(svc.path(svc.rows()[0])))) as db:
            assert db.execute('SELECT count(*) FROM human_tasks').fetchone()[0] == 1
    finally:
        svc.close()
