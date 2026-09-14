"""Check the simulated shell with Playwright against a served website build."""
import argparse
import re
from pathlib import Path
from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8765/demo/')
    parser.add_argument('--browser')
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser, headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 850}, reduced_motion='reduce')
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        expect(page.locator('[data-command="zg init"]')).to_be_visible()
        page.evaluate('document.fonts.ready')
        assert page.evaluate('document.fonts.check(\'14px "JetBrains Mono"\')')

        command_positions = {}

        def geometry():
            box = page.locator('#command-form').bounding_box()
            width = page.viewport_size['width']
            command_positions.setdefault(width, box['y'])
            assert abs(box['y'] - command_positions[width]) < 1, (width, box)
            assert page.locator('.entry').count() <= 1
            buttons = page.locator('#suggestions button, #suggestions a')
            if buttons.count() and page.locator('#suggestions').is_visible():
                first = buttons.first.bounding_box()
                assert 0 <= first['y'] - (box['y'] + box['height']) <= 25
                bottom = max(button.bounding_box()['y'] + button.bounding_box()['height'] for button in buttons.all())
                assert bottom < page.locator('.output-heading').bounding_box()['y']

            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

        def last():
            return page.locator('.entry').last

        def run(command):
            page.get_by_role('textbox', name='Shell command').fill(command)
            page.get_by_role('button', name='Run command', exact=True).click()
            geometry()

        def choose(command):
            page.locator(f'[data-command="{command}"]').click()
            geometry()

        def shot(name):
            if args.screenshots:
                page.screenshot(path=str(args.screenshots / f'{name}.png'), full_page=True)

        def create(agent='codex'):
            choose('zg init')
            choose(agent)
            expect(page.get_by_role('textbox', name='Example request to the coding agent')).to_have_value(re.compile('Watch .txt files'))
            page.get_by_role('button', name='Send this request').click()
            expect(last()).to_contain_text('Validated the workflow')

        geometry()
        expect(page.locator('[data-milestone="0"]')).to_have_attribute('aria-current', 'step')
        shot('01-start')
        run('zg show')
        expect(last()).to_contain_text('Create the workflow')
        page.get_by_role('button', name='Start over').click()
        choose('zg init')
        choose('codex')
        expect(page.locator('#output')).to_be_hidden()
        page.get_by_role('button', name='About', exact=True).click()
        expect(page.get_by_role('dialog')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('#agent-form')).to_be_visible()
        page.get_by_role('button', name='Commands', exact=True).click()
        expect(page.get_by_role('dialog')).to_contain_text('Send the example request')
        page.get_by_role('button', name='Close', exact=True).click()
        shot('02-agent-prompt')
        page.get_by_role('button', name='Send this request').click()
        choose('zg show')
        expect(last()).to_contain_text('if approved @ Mailbox')
        shot('03-global-code')
        choose('zg show --agent Writer')
        expect(last()).to_contain_text("recv_decision('Mailbox')")
        expect(last()).not_to_contain_text('approve_reply')
        shot('04-writer')
        choose('zg show --agent Mailbox')
        expect(last()).to_contain_text('approve_reply')
        run('zg show --communications')
        expect(last()).to_contain_text('Mailbox(message) >> Writer(message)')
        run('zg show --detail full')
        expect(last()).to_contain_text('@human')
        run('zg validate')
        expect(last()).to_contain_text('valid')
        run('zg config')
        expect(last()).to_contain_text('Fixed example draft')
        choose('zg deploy')
        expect(page.locator('[data-milestone="4"]')).to_have_class('milestone done')
        expect(page.locator('[data-milestone="5"]')).to_have_attribute('aria-current', 'step')
        expect(last()).to_contain_text('Saved the pending approval')
        choose('zg deploy tasks')
        expect(last()).to_contain_text('Send this reply?')
        shot('05-approval')
        choose('zg deploy stop')
        expect(last()).to_contain_text('Service stopped')
        page.reload()
        expect(page.locator('[data-command="zg deploy start"]')).to_be_visible()
        run('zg deploy approve --task 1 --yes')
        expect(last()).to_contain_text('Restart the simulated service')
        choose('zg deploy start')
        expect(last()).to_contain_text('Same saved draft')
        shot('06-restarted')
        choose('zg deploy approve --task 1 --no')
        expect(last()).to_contain_text('Rejected. No reply sent.')
        expect(page.locator('.milestone.done')).to_have_count(6)
        run('zg deploy status')
        expect(last()).to_contain_text('Simulated sends    0')
        page.get_by_role('button', name='Try the other decision').click()
        choose('zg deploy approve --task 1 --yes')
        expect(last()).to_contain_text('Approved. Reply sent (simulated).')
        run('zg deploy approve --task 1 --yes')
        expect(last()).to_contain_text('No additional send')
        run('zg deploy stop')
        run('zg deploy status')
        expect(last()).to_contain_text('stopped')
        expect(last()).to_contain_text('Simulated sends    1')
        run('zg deploy start')
        expect(last()).to_contain_text('Waiting for the next request')
        run('zg deploy tasks')
        expect(last()).to_contain_text('No pending approvals')
        run('zg deploy logs')
        expect(last()).to_contain_text('Simulated send completed')
        shot('07-outcome')
        expect(page.get_by_role('link', name='View the example on GitHub', exact=True)).to_have_attribute('href', 'https://github.com/zippergen-io/zippergen/blob/main/examples/email_approval.py')
        run('clear')
        expect(page.locator('.entry')).to_have_count(0)
        run('zg deploy status')
        expect(last()).to_contain_text('Simulated sends    1')
        page.get_by_role('textbox', name='Shell command').press('ArrowUp')
        expect(page.get_by_role('textbox', name='Shell command')).to_have_value('zg deploy status')
        run('<img src=x onerror=alert(1)>')
        expect(last()).to_contain_text('not part of the simulation')
        assert page.locator('#output img').count() == 0
        page.reload()
        run('zg deploy status')
        expect(last()).to_contain_text('Simulated sends    1')
        page.get_by_role('button', name='About', exact=True).click()
        expect(page.get_by_role('dialog')).to_contain_text('The Python code and participant views are real')
        page.get_by_role('button', name='Close', exact=True).click()
        page.get_by_role('button', name='Commands', exact=True).click()
        expect(last()).to_contain_text('zg show --agent Mailbox')

        for width in [820, 390, 320]:
            page.set_viewport_size({'width': width, 'height': 844})
            page.get_by_role('button', name='Start over').click()
            shot(f'mobile-{width}-start')
            create('claude')
            run('zg show')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            shot(f'mobile-{width}-code')
            run('zg deploy')
            run('zg deploy tasks')
            shot(f'mobile-{width}-approval')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#command-form').is_visible()
            choose('zg deploy stop')
            choose('zg deploy start')
            choose('zg deploy approve --task 1 --yes')

        page.get_by_role('button', name='Start over').click()
        create()
        run('zg deploy')
        expect(page.locator('[data-milestone="2"]')).to_contain_text('Not explored')
        expect(page.locator('[data-milestone="4"]')).to_have_class('milestone done')
        run('zg show --agent Writer')
        expect(page.locator('[data-milestone="2"]')).to_have_class('milestone done')
        page.reload()
        expect(page.locator('[data-milestone="4"]')).to_have_class('milestone done')
        geometry()

        for width in [1280, 390]:
            page.set_viewport_size({'width': width, 'height': 844})
            for agent in ['codex', 'claude']:
                for submit in ['click', 'enter']:
                    page.get_by_role('button', name='Start over').click()
                    choose('zg init')
                    choose(agent)
                    if submit == 'click':
                        page.get_by_role('button', name='Send this request').click()
                    else:
                        page.locator('#agent-prompt').press('Enter')
                    expect(page.locator('#command')).to_have_value('zg show')
                    page.keyboard.press('Enter')
                    expect(page.locator('pre.code')).to_be_visible()
                    expect(last()).to_contain_text('if approved @ Mailbox')

        for width, height in [(390, 667), (320, 568), (1280, 720), (844, 390)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.get_by_role('button', name='Start over').click()
            create()
            run('zg show')
            lines = page.locator('#output').evaluate('(e) => e.clientHeight / parseFloat(getComputedStyle(e).lineHeight)')
            assert lines >= 12, (width, height, lines)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')

        fallback = context.new_page()
        fallback.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new Error('blocked')}})")
        fallback.goto(args.url)
        fallback.locator('[data-command="zg init"]').click()
        fallback.locator('[data-command="claude"]').click()
        fallback.get_by_role('button', name='Send this request').click()
        expect(fallback.locator('.entry').last).to_contain_text('Validated the workflow')
        broken = context.new_page()
        broken.route('**/content.json', lambda route: route.fulfill(status=503, body='unavailable'))
        broken.goto(args.url)
        expect(broken.get_by_text('The example could not load.', exact=False)).to_be_visible()
        assert not errors, errors
        browser.close()
    print('Passed: fixed command position, one output at a time, truthful milestones including skipped inspection,  both coding agents with click/Enter continuation, global/local views, configuration, deployment, both decisions, stop/restart before and after completion, duplicate approval, persistence, command history, safe unsupported input, GitHub example link, reset, mobile layouts, local font, and unavailable storage/content.')


if __name__ == '__main__':
    main()
