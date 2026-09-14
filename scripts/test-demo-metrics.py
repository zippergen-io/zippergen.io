"""Browser measurement checks against local files and a fake API, never production."""
import argparse
from collections import Counter
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / 'public'
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser, headless=True)
        for width in (1280, 390):
            context = browser.new_context(viewport={'width': width, 'height': 850})
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
            events = []
            requests = []
            def route(request):
                url = urlsplit(request.request.url)
                if url.hostname == 'zippergen.io':
                    name = url.path.lstrip('/')
                    if name.endswith('/'): name += 'index.html'
                    file = root / name
                    if file.is_file(): request.fulfill(path=str(file))
                    else: request.fulfill(status=404, body='not found')
                else:
                    requests.append(request.request.url)
                    if url.path == '/api/config': request.fulfill(json={'available':True,'metrics_enabled':True})
                    elif url.path == '/api/metrics':
                        value = request.request.post_data_json
                        assert set(value) == {'event', 'attempt'}
                        assert len(value['attempt']) == 32
                        assert 'live' not in value['attempt']
                        events.append(value)
                        request.fulfill(json={'accepted':True})
                    elif url.path == '/api/sessions': request.fulfill(status=429, json={'error':'busy'})
                    else: request.fulfill(status=404, json={})
            context.route('**/*', route)
            page = context.new_page()
            page.goto('https://zippergen.io/demo/')
            expect(page.locator('#usage-counts')).to_have_text('Usage counts: on')
            page.wait_for_function("JSON.parse(sessionStorage.getItem('zippergen-demo-counts-v1')).sent.includes('demo_opened')")
            first = events[0]['attempt']
            page.reload()
            expect(page.locator('#usage-counts')).to_be_visible()
            page.locator('[data-command="zg init"]').click()
            page.locator('[data-command="codex"]').click()
            page.get_by_role('button', name='Send this request').click()
            def run(command):
                page.locator('#command').fill(command)
                page.locator('#command-form button').click()
            run('zg deploy')
            run('zg deploy tasks')
            page.locator('#try-live').click()
            expect(page.locator('#new-live-session')).to_be_visible()
            page.locator('#live-dialog button[type=submit]').click()
            page.locator('#preview-reject').click()
            expect(page.locator('#completion')).to_be_visible()
            page.locator('#live-next-step').click()
            page.wait_for_function("JSON.parse(sessionStorage.getItem('zippergen-demo-counts-v1')).sent.length === 6")
            assert Counter(e['event'] for e in events) == Counter({e:1 for e in (
                'demo_opened','first_command','deployment_reached','simulation_completed','telegram_requested','github_clicked')})
            assert all(e['attempt'] == first for e in events)
            page.reload()
            expect(page.locator('#usage-counts')).to_be_visible()
            page.locator('#usage-counts').click()
            expect(page.locator('#usage-counts')).to_have_text('Usage counts: off')
            count = len(events)
            page.locator('#reset').click()
            page.locator('[data-command="zg init"]').click()
            page.reload()
            expect(page.locator('#usage-counts')).to_have_text('Usage counts: off')
            assert len(events) == count
            page.locator('#usage-counts').click()
            page.wait_for_function("JSON.parse(sessionStorage.getItem('zippergen-demo-counts-v1')).sent.includes('demo_opened')")
            assert events[-1]['attempt'] != first
            page.locator('#reset').click()
            page.wait_for_function("JSON.parse(sessionStorage.getItem('zippergen-demo-counts-v1')).sent.includes('demo_opened')")
            assert events[-1]['attempt'] != events[-2]['attempt']
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            context.close()
        # The normal automation flag and browser privacy signals suppress reporting.
        for script in ('', "Object.defineProperty(navigator, 'webdriver', {get: () => false}); Object.defineProperty(navigator, 'doNotTrack', {get: () => '1'});",
                       "Object.defineProperty(navigator, 'webdriver', {get: () => false}); Object.defineProperty(navigator, 'globalPrivacyControl', {get: () => true});"):
            context = browser.new_context()
            if script: context.add_init_script(script)
            forbidden = []
            def blocked_route(route):
                url = urlsplit(route.request.url)
                if url.hostname == 'zippergen.io':
                    file = root / (url.path.lstrip('/') + ('index.html' if url.path.endswith('/') else ''))
                    route.fulfill(path=str(file))
                elif url.path == '/api/metrics':
                    forbidden.append(url.path)
                    route.fulfill(json={})
                else: route.fulfill(json={'available':True, 'metrics_enabled':True})
            context.route('**/*', blocked_route)
            page = context.new_page()
            page.goto('https://zippergen.io/demo/')
            page.locator('[data-command="zg init"]').click()
            page.wait_for_timeout(150)
            assert forbidden == []
            context.close()
        browser.close()
    print('Passed: all milestones, reload deduplication, reset, opt-out, automation exclusion and privacy signals, desktop and mobile. No production requests.')


if __name__ == '__main__': main()
