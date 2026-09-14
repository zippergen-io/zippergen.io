"""Exercise the browser against the real demo API and runtime, with Telegram transport faked."""
import argparse
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, urlsplit
from wsgiref.simple_server import make_server, WSGIRequestHandler
from playwright.sync_api import sync_playwright, expect
from live_demo.service import Sessions
from live_demo.server import API


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class Bot:
    token = 'fake-test-token'
    def __init__(self): self.sent = []
    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))
        return {'result': {'message_id': len(self.sent)}}
    def answer_callback_query(self, *args, **kwargs): pass
    def edit_message_reply_markup(self, **kwargs): pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--browser', required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--screenshots', type=Path, required=True)
    parser.add_argument('--qr-decoder', type=Path, help='Optional local jsQR script for independent image decoding')
    args = parser.parse_args()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    origin = '{0.scheme}://{0.netloc}'.format(urlsplit(args.url))
    service = Sessions(args.state, Bot(), 'zippergen_demo_bot')
    service.healthy = True
    service.last_poll = service.last_delivery = time.time()
    http = make_server('127.0.0.1', 0, API(service, [origin]), handler_class=QuietHandler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.browser, headless=True)
            for index, yes in enumerate([True, False]):
                context = browser.new_context(viewport={'width': 1280 if yes else 390, 'height': 850})
                context.route('**/live-config.json', lambda route: route.fulfill(json={'api_base': f'http://127.0.0.1:{http.server_port}'}))
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(args.url)
                def choose(command): page.locator(f'[data-command="{command}"]').click()
                choose('zg init')
                choose('codex')
                expect(page.locator('#agent-prompt')).to_be_focused()
                page.locator('#agent-prompt').press('Enter')
                choose('zg show')
                choose('zg config')
                page.locator('[data-setup]').click()
                expect(page.get_by_role('dialog')).to_contain_text('set-credential')
                page.get_by_role('button', name='Close', exact=True).click()
                choose('zg deploy')
                choose('zg deploy tasks')
                expect(page.locator('#telegram-preview')).to_be_visible()
                page.screenshot(path=str(args.screenshots / f'preview-{index}.png'))
                page.get_by_role('button', name='Try this step for real on Telegram').click()
                expect(page.locator('#telegram-link')).to_be_visible()
                expect(page.locator('#telegram-qr')).to_be_visible()
                expect(page.locator('#telegram-qr-code')).to_be_hidden()
                page.get_by_text('Scan with your phone', exact=True).click()
                expect(page.locator('#telegram-qr-code')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                if args.qr_decoder:
                    page.add_script_tag(path=str(args.qr_decoder))
                    decoded = page.evaluate("""() => {
                        const canvas = document.querySelector('#telegram-qr-code');
                        const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
                        return jsQR(pixels.data, pixels.width, pixels.height)?.data;
                    }""")
                    assert decoded == page.locator('#telegram-link').get_attribute('href')
                page.screenshot(path=str(args.screenshots / f'qr-{index}.png'))
                start = parse_qs(urlsplit(page.locator('#telegram-link').get_attribute('href')).query)['start'][0]
                reader = parse_qs(urlsplit(page.url).fragment)['live'][0]
                saved_url = page.url
                actor = 100 + index
                service.process_update({'message': {'text': '/start ' + start, 'chat': {'id': actor, 'type': 'private'}, 'from': {'id': actor}}})
                service.tick()
                deadline = time.monotonic() + 8
                while service.status(reader)['state'] != 'waiting' and time.monotonic() < deadline: time.sleep(.02)
                service.tick()
                expect(page.locator('#live-status')).to_contain_text('You can close this page', timeout=15000)
                expect(page.locator('#preview-approve')).to_be_disabled()
                expect(page.locator('#preview-reject')).to_be_disabled()
                expect(page.locator('#telegram-qr')).to_be_hidden()
                assert page.locator('#telegram-qr-code').evaluate('(canvas) => canvas.width') == 0
                page.screenshot(path=str(args.screenshots / f'live-waiting-{index}.png'))
                page.close()
                message = [m for m in service.client.sent if m[0] == str(actor) and m[2]][0]
                data = message[2]['inline_keyboard'][0][0 if yes else 1]['callback_data']
                service.process_update({'callback_query': {'id': 'answer', 'data': data, 'from': {'id': actor}, 'message': {'message_id': 1, 'chat': {'id': actor, 'type': 'private'}}}})
                deadline = time.monotonic() + 8
                expected = 'approved' if yes else 'rejected'
                while service.status(reader)['state'] != expected and time.monotonic() < deadline: time.sleep(.02)
                service.tick()
                page = context.new_page()
                page.goto(saved_url)
                expect(page.locator('#live-status')).to_contain_text('completed', timeout=15000)
                assert page.evaluate("JSON.parse(localStorage.getItem('zippergen-shell-demo-v1')).decision") is None
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(args.screenshots / f'live-complete-{index}.png'))
                page.locator('#live-dialog button[type=submit]').click()
                expect(page.locator('#preview-approve')).to_be_disabled()
                expect(page.locator('#preview-reject')).to_be_disabled()
                expect(page.locator('#preview-message')).to_contain_text('Approved in Telegram' if yes else 'Rejected in Telegram')
                expect(page.locator('[data-milestone="5"]')).to_have_attribute('aria-label', 'Decide: complete')
                page.get_by_role('textbox', name='Shell command').fill('zg deploy approve --task 1 --no')
                page.get_by_role('button', name='Run command', exact=True).click()
                assert page.evaluate("JSON.parse(localStorage.getItem('zippergen-shell-demo-v1')).decision") is None
                assert service.status(reader)['state'] == expected
                page.get_by_role('button', name='Start over', exact=True).click()
                assert page.evaluate("localStorage.getItem('zippergen-live-demo-v1')") is None
                assert not urlsplit(page.url).fragment
                expect(page.locator('#resume-live')).to_be_hidden()
                page.reload()
                choose('zg init')
                choose('claude')
                page.locator('#agent-prompt').press('Enter')
                for command in ['zg show', 'zg config', 'zg deploy', 'zg deploy tasks']:
                    choose(command)
                expect(page.locator('#preview-approve')).to_be_enabled()
                page.get_by_role('button', name='Try this step for real on Telegram').click()
                expect(page.locator('#telegram-link')).to_be_visible()
                new_reader = parse_qs(urlsplit(page.url).fragment)['live'][0]
                assert new_reader != reader
                assert service.status(new_reader)['state'] == 'connecting'
                expect(page.locator('#telegram-qr-code')).to_be_hidden()
                page.get_by_text('Scan with your phone', exact=True).click()
                expect(page.locator('#telegram-qr-code')).to_be_visible()
                if args.qr_decoder:
                    page.add_script_tag(path=str(args.qr_decoder))
                    decoded = page.evaluate('''() => {
                        const c = document.querySelector('#telegram-qr-code');
                        const p = c.getContext('2d').getImageData(0, 0, c.width, c.height);
                        return jsQR(p.data, p.width, p.height)?.data;
                    }''')
                    assert decoded == page.locator('#telegram-link').get_attribute('href')
                    assert parse_qs(urlsplit(decoded).query)['start'][0] != start
                page.route('**/api/session*', lambda route: route.fulfill(status=410, json={'error': 'expired'}))
                page.locator('#live-dialog button[type=submit]').click()
                page.locator('#resume-live').click()
                expect(page.locator('#live-status')).to_contain_text('expired')
                expect(page.locator('#telegram-qr')).to_be_hidden()
                expect(page.locator('#telegram-link')).to_be_hidden()
                assert service.status(reader)['state'] == expected
                context.close()
            browser.close()
        assert not errors, errors
        print('Passed: Telegram preview and setup, live creation through real HTTP API, private-chat association, real persisted workflow, browser closed during both decisions, restored completed runs, disabled web approvals, fresh live sessions after reset and reload, Enter submission for both coding agents, and QR display/decoding, new-session replacement and expiry.')
    finally:
        http.shutdown()
        http.server_close()
        service.close()


if __name__ == '__main__': main()
