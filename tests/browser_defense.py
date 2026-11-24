"""Browser acceptance: install playwright and `python -m playwright install chromium`,
or point CHROMIUM_PATH at an installed Chromium/Edge. Then run this script.
"""
import argparse
import os
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def verify(page, base, evidence=None):
    outside = []
    origin = urlsplit(base).netloc

    def permit_local(route):
        if urlsplit(route.request.url).netloc != origin:
            outside.append(route.request.url)
            return route.abort()
        route.continue_()

    page.context.route('**/*', permit_local)
    page.goto(base + '/metrics')
    expect(page.get_by_role('heading', name='数据来源与时间')).to_be_visible()
    expect(page.get_by_text('2024-02-01 至 2026-09-30')).to_be_visible()
    for label, a, b in [('误报次数', 130, 104), ('漏报次数', 87, 73)]:
        row = page.get_by_role('row').filter(has_text=label)
        expect(row.get_by_role('cell').nth(1)).to_have_text(str(a))
        expect(row.get_by_role('cell').nth(2)).to_have_text(str(b))
    if evidence:
        page.locator('.page').screenshot(path=evidence / 'metrics.png', style='header { visibility: hidden !important }')
    page.locator('#m-version').select_option('25mm')
    expect(page.get_by_text('融合召回率下降', exact=False)).to_be_visible()
    page.goto(base + '/replay')
    page.get_by_role('button', name='回放', exact=True).click()
    expect(page.get_by_text('÷ 4 = 29.625 mm', exact=False)).to_be_visible()
    section = page.get_by_role('region', name='外部城市降水试算')
    for label, name in [('南京样例', 'nanjing'), ('缺一列示例', 'missing-model')]:
        with page.expect_download() as dl:
            section.get_by_role('link', name=label, exact=False).click()
        assert dl.value.suggested_filename == name + '.json'
        section.locator('input[type=file]').set_input_files({
            'name': name + '.json', 'mimeType': 'application/json', 'buffer': dl.value.path().read_bytes()})
        section.get_by_role('button', name='运行试算').click()
        if name == 'nanjing':
            expect(section.locator('tbody tr')).to_have_count(7)
            day = section.get_by_role('row').filter(has_text='2026-10-03')
            expect(day.get_by_text('5.9 · 未达')).to_be_visible()
            expect(day.get_by_text('5.4 · 未达（ERA5 再分析）')).to_be_visible()
            if evidence:
                section.screenshot(path=evidence / 'nanjing.png')
        else:
            expect(section.get_by_role('alert')).to_contain_text('第 1 行 models.gem_global')
            expect(section.locator('tbody tr')).to_have_count(0)
    assert not outside, 'Page attempted external network access'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18281')
    parser.add_argument('--expect-revision', help='verify the Git archive SHA before signing in')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    base = args.url.rstrip('/')
    if args.evidence:
        args.evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH'))
        ctx = browser.new_context(viewport={'width': 1360, 'height': 920}, service_workers='block', reduced_motion='reduce')
        if args.expect_revision:
            stamp = ctx.request.get(base + '/build-revision.txt')
            if not stamp.ok or stamp.text().strip() != args.expect_revision:
                raise SystemExit('QA endpoint revision mismatch; refusing to sign in')
        page = ctx.new_page()
        page.goto(base + '/login')
        page.locator('input[autocomplete=username]').fill('analyst_demo')
        page.locator('input[type=password]').fill(os.getenv('DEMO_ANALYST_PASSWORD') or getpass('Demo analyst password: '))
        page.locator('button[type=submit]').click()
        page.wait_for_url(base + '/')
        verify(page, base, args.evidence)
        browser.close()
    print('PASS: source dates, both thresholds, Changsha replay, offline sample, error row and network isolation')


if __name__ == '__main__':
    main()
