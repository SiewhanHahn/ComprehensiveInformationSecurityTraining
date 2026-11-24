"""Write-workflow check for an isolated QA deployment; requires playwright and local Chromium/Edge."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qa-url', required=True)
    parser.add_argument('--expect-revision', required=True)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    base = args.qa_url.rstrip('/')
    origin = urlsplit(base).netloc
    if urlsplit(base).hostname != '127.0.0.1' or os.getenv('BCHECK_ALLOW_WRITE') != '1':
        raise SystemExit('Require a loopback QA endpoint and BCHECK_ALLOW_WRITE=1')
    outside = []
    key = 'SN-QA-' + uuid4().hex[:8]

    def local_only(route):
        if urlsplit(route.request.url).netloc != origin:
            outside.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or None)

        def login(role):
            context = browser.new_context(viewport={'width': 1360, 'height': 920}, service_workers='block', reduced_motion='reduce')
            stamp = context.request.get(base + '/build-revision.txt')
            assert stamp.ok and stamp.text().strip() == args.expect_revision, 'Wrong QA revision; refusing to log in'
            context.route('**/*', local_only)
            page = context.new_page()
            page.set_default_timeout(12000)
            page.goto(base + '/login')
            page.locator('input[autocomplete=username]').fill(role.lower() + '_demo')
            page.locator('input[type=password]').fill(os.environ['DEMO_' + role + '_PASSWORD'])
            page.locator('button[type=submit]').click()
            page.wait_for_url(base + '/')
            return page

        def click_write(page, button, suffix):
            with page.expect_response(lambda r: urlsplit(r.url).path.endswith(suffix) and r.request.method == 'POST') as info:
                page.get_by_role('button', name=button, exact=True).click()
            assert info.value.ok, f'{button} returned {info.value.status}'
            return info.value.json()

        a = login('ANALYST')
        a.goto(base + '/snow')
        evidence = a.get_by_role('region', name='雪灾预报判定')
        expect(evidence.get_by_test_id('snow-total')).to_have_text('12.74 cm')
        expect(evidence.get_by_text('达到强降雪教学阈值', exact=True)).to_be_visible()
        reference = a.get_by_role('region', name='独立事后核验')
        expect(reference.get_by_test_id('snow-verification')).to_have_text('站点记录到降雪')
        reference.locator('summary').click()
        expect(reference.get_by_text('2025-03-02 06:00 · 74 间歇性强降雪')).to_be_visible()
        if args.evidence:
            args.evidence.mkdir(parents=True, exist_ok=True)
            a.locator('main').screenshot(path=args.evidence / 'snow-forecast.png')
        a.set_viewport_size({'width': 390, 'height': 844})
        expect(evidence.get_by_test_id('snow-total')).to_be_visible()
        assert evidence.evaluate('(el) => el.scrollWidth <= el.clientWidth'), 'Snow evidence overflows on mobile'
        a.set_viewport_size({'width': 1360, 'height': 920})
        evidence.locator('summary').click()
        expect(evidence.locator('tbody tr')).to_have_count(24)
        expect(evidence.get_by_text('2025-03-03 00:00 UTC', exact=True)).to_be_visible()

        a.locator('#snow-case').select_option('jinan-20250304')
        expect(evidence.get_by_test_id('snow-total')).to_have_text('0.00 cm')
        expect(evidence.get_by_text('未达到强降雪教学阈值', exact=True)).to_be_visible()
        expect(reference.get_by_test_id('snow-verification')).to_have_text('抽样时次未报告降雪')
        expect(a.get_by_role('button', name='填写雪灾演练草稿', exact=True)).to_have_count(0)
        a.locator('#snow-case').select_option('jinan-20250302')
        a.get_by_role('button', name='填写雪灾演练草稿', exact=True).click()
        a.locator('#snow-title').fill(key + ' · 雪灾历史演练')
        created = click_write(a, '保存雪灾演练草稿', '/warnings/snow')
        assert created['hazard_type'] == 'SNOW_DISASTER' and created['status'] == 'DRAFT'
        assert created['city_name'] == '济南' and created['fused_mm'] is None
        detail = base + '/warnings/' + created['public_id']
        a.wait_for_url(detail)
        expect(a.get_by_role('region', name='雪灾预报判定')).to_be_visible()
        expect(a.get_by_role('region', name='独立事后核验')).to_have_count(0)
        expect(a.get_by_text('融合累计', exact=True)).to_have_count(0)
        assert click_write(a, '提交审核', '/submit')['status'] == 'PENDING_REVIEW'
        r = login('REVIEWER')
        r.goto(detail)
        expect(r.get_by_role('region', name='雪灾预报判定')).to_be_visible()
        r.get_by_label('审核意见').fill('核对济南归档降雪预报')
        assert click_write(r, '批准', '/review')['decision'] == 'APPROVE'
        r.get_by_label('发布或撤回原因').fill(key + '-演练发布')
        assert click_write(r, '发布', '/publish')['status'] == 'PUBLISHED'
        a.reload()
        click_write(a, '接单', '/ack')
        a.get_by_placeholder('处置说明（可选）').fill('历史案例复核完成')
        assert click_write(a, '完成任务', '/complete')['status'] == 'COMPLETED'
        a.locator('#f-content').fill('演练反馈：不作为实况预警')
        click_write(a, '提交反馈', '/feedback')
        r.get_by_label('发布或撤回原因').fill(key + '-演练撤回')
        assert click_write(r, '撤回', '/withdraw')['status'] == 'WITHDRAWN'
        admin = login('ADMIN')
        admin.goto(base + '/audit')
        for reason in (key + '-演练发布', key + '-演练撤回'):
            row = admin.get_by_role('row').filter(has_text=reason)
            expect(row).to_have_count(1)
            expect(row).to_contain_text('v1')
        assert not outside, f'Replay attempted external requests: {outside!r}'
        browser.close()
    print('PASS: offline snowfall and no-snow windows with independent station reference, draft from forecast only, publish, task, feedback, withdrawal and audit')


if __name__ == '__main__':
    main()
