"""Check completion UI with mocked API responses, without contacting Telegram."""
import argparse
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='http://127.0.0.1:8765/demo/')
parser.add_argument('--browser')
args = parser.parse_args()
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=args.browser, headless=True)
    for index, (outcome, motion, width) in enumerate([
        ('approved', 'no-preference', 1280),
        ('approved', 'reduce', 390),
        ('rejected', 'no-preference', 390),
    ]):
        context = browser.new_context(viewport={'width': width, 'height': 850}, reduced_motion=motion)
        context.add_init_script('''
            window.confettiPieces = 0;
            new MutationObserver(records => {
                for (const record of records) {
                    if (record.target.id === 'live-confetti') window.confettiPieces += record.addedNodes.length;
                }
            }).observe(document, {subtree: true, childList: true});
        ''')
        context.route('**/live-config.json', lambda route: route.fulfill(json={'api_base': 'https://completion-test.invalid'}))
        context.route('https://completion-test.invalid/api/session', lambda route: route.fulfill(json={
            'state': outcome, 'expires_at': 2000000000, 'available': True,
        }))
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        token = str(index) * 32
        url = args.url + '#live=' + token
        page.goto(url)
        expect(page.locator('#live-title')).to_have_text('Your workflow is complete.')
        expect(page.locator('#live-status')).to_contain_text('completed the workflow')
        expect(page.get_by_role('link', name='Try it with your own workflow')).to_be_visible()
        assert page.locator('#live-next-step').get_attribute('href') == './approval-example.zip'
        pieces = 24 if outcome == 'approved' and motion == 'no-preference' else 0
        assert page.evaluate('window.confettiPieces') == pieces
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.locator('#live-dialog button[type=submit]').click()
        expect(page.locator('#live-confetti i')).to_have_count(0)
        page.locator('#resume-live').click()
        expect(page.locator('#live-title')).to_have_text('Your workflow is complete.')
        assert page.evaluate('window.confettiPieces') == pieces
        page.reload()
        expect(page.locator('#live-title')).to_have_text('Your workflow is complete.')
        assert page.evaluate('window.confettiPieces') == 0
        page.locator('#live-dialog button[type=submit]').click()
        page.get_by_role('button', name='Start over').click()
        expect(page.locator('#live-next-step')).to_be_hidden()
        expect(page.locator('#live-title')).to_have_text('Live on our demo server')
        assert not errors, errors
        context.close()
    browser.close()
print('Passed: completion links, approved-only confetti, no replay on reopen/refresh, reduced motion, reset, desktop and mobile.')
