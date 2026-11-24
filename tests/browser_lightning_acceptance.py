"""Exercise the lightning replay and common lifecycle in a revision-pinned, writable QA instance."""
import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright


POSITIVE = 'kstl-20250315-00z'
CONTROL = 'kstl-20250315-06z'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qa-url', required=True)
    parser.add_argument('--expect-revision', required=True)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    base = args.qa_url.rstrip('/')
    origin = urlsplit(base).netloc
    if (urlsplit(base).hostname != '127.0.0.1' or os.getenv('BCHECK_ALLOW_WRITE') != '1'
            or not re.fullmatch(r'[0-9a-f]{40}', args.expect_revision)):
        raise SystemExit('Require a loopback QA endpoint, full candidate SHA and BCHECK_ALLOW_WRITE=1')
    outside = []
    key = 'LTNG-QA-' + uuid4().hex[:8]

    def local_only(route):
        if urlsplit(route.request.url).netloc != origin:
            outside.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or None)

        def login(role):
            context = browser.new_context(viewport={'width': 1360, 'height': 920}, service_workers='block',
                                          reduced_motion='reduce')
            stamp = context.request.get(base + '/build-revision.txt')
            assert stamp.ok and stamp.text().strip() == args.expect_revision, 'Wrong QA revision; stop before login'
            context.route('**/*', local_only)
            page = context.new_page()
            page.set_default_timeout(12000)
            page.goto(base + '/login')
            page.locator('input[autocomplete=username]').fill(role.lower() + '_demo')
            page.locator('input[type=password]').fill(os.environ[f'DEMO_{role}_PASSWORD'])
            page.locator('button[type=submit]').click()
            page.wait_for_url(base + '/')
            return page

        def click_write(page, button, suffix):
            def matches(response):
                return urlsplit(response.url).path.endswith(suffix) and response.request.method == 'POST'

            with page.expect_response(matches) as info:
                page.get_by_role('button', name=button, exact=True).click()
            assert info.value.ok, f'{button} returned {info.value.status}'
            return info.value.json()

        analyst = login('ANALYST')
        analyst.goto(base + '/hazards')
        analyst.get_by_role('link', name='查看雷电历史案例').click()
        analyst.wait_for_url(base + '/lightning')
        evidence = analyst.get_by_role('region', name='雷电预报判定')
        reference = analyst.get_by_role('region', name='独立事后核验')
        slots = evidence.locator('.lightning-slots li')
        draft_button = analyst.get_by_role('button', name='填写雷电演练草稿')
        select = analyst.get_by_label('预报窗口')
        expect(evidence.get_by_test_id('lightning-outcome')).to_have_text('达到教学阈值')
        expect(evidence.get_by_test_id('lightning-ltng')).to_have_text('0.09')
        expect(evidence.get_by_text('2025-03-14 19:08:29 UTC', exact=False)).to_be_visible()
        expect(slots.locator('strong')).to_have_text(['0.00', '0.06', '0.08', '0.09', '0.00', '0.00'])
        expect(evidence.locator('.slot-hit time')).to_have_text(['02:00 UTC', '03:00 UTC', '04:00 UTC'])
        expect(reference.get_by_test_id('lightning-verification')).to_have_text('站点报告雷暴及闪电备注')
        reference.locator('summary').click()
        expect(reference.get_by_text('01:46 · TS · LTGCCCG', exact=False)).to_be_visible()
        expect(reference.get_by_text('02:33 · +TSRA · LTGICCCCGCA', exact=False)).to_be_visible()
        reference.locator('summary').click()
        if args.evidence:
            args.evidence.mkdir(parents=True, exist_ok=True)
            analyst.evaluate('window.scrollTo(0, 0)')
            analyst.screenshot(path=args.evidence / 'lightning-forecast.png', full_page=True)
        analyst.set_viewport_size({'width': 390, 'height': 844})
        expect(slots).to_have_count(6)
        assert evidence.evaluate('(node) => node.scrollWidth <= node.clientWidth'), 'Forecast card overflows on mobile'
        analyst.set_viewport_size({'width': 1360, 'height': 920})

        select.select_option(CONTROL)
        expect(evidence.get_by_test_id('lightning-outcome')).to_have_text('未达教学阈值')
        expect(slots.locator('strong')).to_have_text(['0.00'] * 6)
        expect(reference.get_by_test_id('lightning-verification')).to_have_text('抽样时次未报告新的雷暴或闪电')
        reference.locator('summary').click()
        expect(reference.get_by_text('06:12 · 无新的雷暴天气码 · TSE06（上一轮雷暴结束）', exact=False)).to_be_visible()
        expect(draft_button).to_have_count(0)

        # Fault injection in the browser only: backend incomplete-case semantics are tested by pytest.
        positive_path = base + f'/api/v1/lightning/cases/{POSITIVE}/assessment'

        def inject_missing_hour(route):
            response = route.fetch()
            replay = response.json()
            forecast = replay['forecast']
            forecast['hours'][0]['ltng'] = None
            forecast.update(outcome='INSUFFICIENT', metric=None, reached_times=[], usable_hours=5)
            route.fulfill(response=response, json=replay)

        analyst.route(positive_path, inject_missing_hour, times=1)
        select.select_option(POSITIVE)
        expect(evidence.get_by_test_id('lightning-outcome')).to_have_text('无法判断')
        expect(slots.first.get_by_text('缺测')).to_be_visible()
        expect(draft_button).to_have_count(0)
        select.select_option(CONTROL)
        expect(evidence.get_by_test_id('lightning-outcome')).to_have_text('未达教学阈值')
        select.select_option(POSITIVE)
        draft_button.click()
        analyst.get_by_label('草稿标题').fill(key + ' · 雷电历史演练')
        created = click_write(analyst, '保存雷电演练草稿', '/warnings/lightning')
        assert (created['hazard_type'], created['status'], created['city_name'], created['fused_mm']) == (
            'THUNDERSTORM', 'DRAFT', '圣路易斯', None)
        detail = base + '/warnings/' + created['public_id']
        analyst.wait_for_url(detail)
        expect(evidence.get_by_test_id('lightning-ltng')).to_have_text('0.09')
        expect(reference).to_have_count(0)
        expect(analyst.get_by_text('融合累计', exact=True)).to_have_count(0)
        assert click_write(analyst, '提交审核', '/submit')['status'] == 'PENDING_REVIEW'

        reviewer = login('REVIEWER')
        reviewer.goto(detail)
        expect(reviewer.get_by_role('region', name='雷电预报判定')).to_be_visible()
        reviewer.get_by_label('审核意见').fill('核对六个 HRRR 有效预报时次')
        assert click_write(reviewer, '批准', '/review')['decision'] == 'APPROVE'
        reviewer.get_by_label('发布或撤回原因').fill(key + '-演练发布')
        assert click_write(reviewer, '发布', '/publish')['status'] == 'PUBLISHED'

        analyst.reload()
        click_write(analyst, '接单', '/ack')
        analyst.get_by_placeholder('处置说明（可选）').fill('完成历史档案复核')
        assert click_write(analyst, '完成任务', '/complete')['status'] == 'COMPLETED'
        analyst.locator('#f-content').fill('演练反馈：不作为实况预警')
        click_write(analyst, '提交反馈', '/feedback')
        reviewer.get_by_label('发布或撤回原因').fill(key + '-演练撤回')
        assert click_write(reviewer, '撤回', '/withdraw')['status'] == 'WITHDRAWN'
        admin = login('ADMIN')
        admin.goto(base + '/audit')
        for reason in (key + '-演练发布', key + '-演练撤回'):
            row = admin.get_by_role('row').filter(has_text=reason)
            expect(row).to_have_count(1)
            expect(row).to_contain_text('v1')
        assert not outside, f'Replay attempted external requests: {outside!r}'
        browser.close()
    print('PASS: six offline lightning instants, quiet/missing cases, forecast-only draft, independent publication, response, feedback, withdrawal and audit')


if __name__ == '__main__':
    main()
