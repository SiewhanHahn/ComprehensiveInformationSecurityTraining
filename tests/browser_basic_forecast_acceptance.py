"""Check the read-only basic forecasts in an isolated revision-pinned deployment."""
import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qa-url', required=True)
    parser.add_argument('--expect-revision', required=True)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    base = args.qa_url.rstrip('/')
    origin = urlsplit(base).netloc
    if urlsplit(base).hostname != '127.0.0.1' or not re.fullmatch(r'[0-9a-f]{40}', args.expect_revision):
        raise SystemExit('Require a loopback QA endpoint and a full candidate SHA')
    outside = []

    def offline(route):
        if urlsplit(route.request.url).netloc != origin:
            outside.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or None)
        context = browser.new_context(viewport={'width': 1360, 'height': 920}, service_workers='block',
                                      reduced_motion='reduce')
        stamp = context.request.get(base + '/build-revision.txt')
        assert stamp.ok and stamp.text().strip() == args.expect_revision, 'Wrong QA revision'
        context.route('**/*', offline)
        page = context.new_page()
        page.set_default_timeout(12000)
        page.goto(base + '/login')
        page.locator('input[autocomplete=username]').fill('viewer_demo')
        page.locator('input[type=password]').fill(os.environ['DEMO_VIEWER_PASSWORD'])
        page.locator('button[type=submit]').click()
        page.wait_for_url(base + '/')

        page.goto(base + '/hazards')
        expect(page.get_by_text('4 类端到端实现 · 1 类基础预测', exact=False)).to_be_visible()
        page.get_by_role('link', name='试算干旱风险').click()
        page.wait_for_url(base + '/basic-forecast')
        forecast = page.get_by_role('region', name='干旱预测结果')
        outcome = forecast.get_by_test_id('drought-outcome')
        streak = forecast.get_by_test_id('drought-streak')
        calculate = page.get_by_role('button', name='计算干旱风险')
        trial = '/api/v1/basic-forecast/drought/assessment'
        warnings = context.request.get(base + '/api/v1/warnings').json()

        def compute():
            with page.expect_response(lambda r: urlsplit(r.url).path == trial and r.request.method == 'POST') as info:
                calculate.click()
            res = info.value
            assert res.ok and res.headers.get('cache-control') == 'no-store', res.status
            return res.json()

        assert compute()['end_dry_days'] == 16
        expect(streak).to_have_text('16 天')
        expect(outcome).to_have_text('少雨持续达到教学阈值')
        expect(forecast.locator('tbody tr')).to_have_count(7)
        expect(forecast.get_by_text('2025-07-07', exact=True)).to_be_visible()
        if args.evidence:
            args.evidence.mkdir(parents=True, exist_ok=True)
            page.evaluate('window.scrollTo(0, 0)')
            page.screenshot(path=args.evidence / 'drought-trial.png', full_page=True)

        fifth_day = page.get_by_label('第 5 天降水')
        fifth_day.fill('1.00')
        expect(forecast).to_have_count(0)
        assert compute()['days'][4]['dry_days'] == 0
        expect(streak).to_have_text('2 天')
        expect(outcome).to_have_text('末日未达持续少雨教学阈值')
        page.get_by_role('button', name='恢复教学示例').click()
        expect(forecast).to_have_count(0)
        page.get_by_label('签发前连续少雨日数').fill('7')
        assert compute()['outcome'] == 'REACHED'
        expect(streak).to_have_text('14 天')

        fifth_day.fill('')
        result = compute()
        assert result['usable_days'] == 6 and result['days'][4]['rain_mm'] is None
        expect(outcome).to_have_text('无法判断')
        expect(streak).to_have_count(0)
        expect(forecast.get_by_text('缺测', exact=True)).to_be_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert forecast.evaluate('(el) => el.scrollWidth <= el.clientWidth'), 'Drought result overflows on mobile'
        assert context.request.get(base + '/api/v1/warnings').json() == warnings
        assert not outside, f'Basic forecasts attempted external requests: {outside!r}'
        browser.close()
    print('PASS: offline drought editable values (16, 2, 14 days), unknown input, mobile, no published warning changes')


if __name__ == '__main__':
    main()
