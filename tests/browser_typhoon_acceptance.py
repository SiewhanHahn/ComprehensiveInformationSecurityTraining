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
    key = 'TY-QA-' + uuid4().hex[:8]

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
        a.goto(base + '/typhoon')
        evidence = a.get_by_role('region', name='台风预报判定')
        expect(evidence.get_by_test_id('typhoon-distance')).to_have_text('144.3 km')
        expect(evidence.get_by_text('2017-08-22 10:30', exact=True)).to_be_visible()
        verify = evidence.get_by_label('事后核对')
        expect(verify).to_contain_text('112°E')
        expect(verify).to_contain_text('10.3 km')
        if args.evidence:
            args.evidence.mkdir(parents=True, exist_ok=True)
            a.locator('.page').screenshot(path=args.evidence / 'typhoon-forecast.png')
        a.locator('#typhoon-city').select_option('SHANGHAI')
        expect(evidence.get_by_test_id('typhoon-distance')).to_have_text('1351.3 km')
        expect(evidence.get_by_text('供比较的预报点未达到阈值')).to_be_visible()
        expect(a.get_by_role('button', name='填写演练草稿')).to_have_count(0)
        a.locator('#typhoon-city').select_option('GUANGZHOU')
        a.get_by_role('button', name='填写演练草稿').click()
        a.locator('#typhoon-title').fill(key + ' · 台风历史演练')
        created = click_write(a, '保存台风演练草稿', '/warnings/typhoon')
        assert created['hazard_type'] == 'TYPHOON' and created['status'] == 'DRAFT'
        detail = base + '/warnings/' + created['public_id']
        a.wait_for_url(detail)
        expect(a.get_by_role('region', name='台风预报判定')).to_be_visible()
        expect(a.get_by_label('事后核对')).to_have_count(0)
        expect(a.get_by_text('融合累计', exact=True)).to_have_count(0)
        assert click_write(a, '提交审核', '/submit')['status'] == 'PENDING_REVIEW'
        r = login('REVIEWER')
        r.goto(detail)
        expect(r.get_by_role('region', name='台风预报判定')).to_be_visible()
        r.get_by_label('审核意见').fill('核对天鸽航运公报')
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
    print('PASS: offline Hato near/far and verification, draft from forecast only, publish, task, feedback, withdrawal and audit')


if __name__ == '__main__':
    main()
