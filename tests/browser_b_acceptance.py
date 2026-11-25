"""Optional, writes test records. Use ONLY a disposable B QA instance and its DEMO_* env.
Install playwright plus Chromium, or specify an installed browser in CHROMIUM_PATH.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

from verify_offline_qa_target import validate_browser_proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qa-url', required=True)
    parser.add_argument('--expect-revision', required=True)
    parser.add_argument('--qa-proof', required=True, type=Path)
    args = parser.parse_args()
    base = args.qa_url.rstrip('/')
    if urlsplit(base).hostname != '127.0.0.1' or os.getenv('BCHECK_ALLOW_WRITE') != '1':
        raise SystemExit('Require a loopback QA endpoint and BCHECK_ALLOW_WRITE=1')
    try:
        validate_browser_proof(json.loads(args.qa_proof.read_text(encoding='utf-8-sig')), base, args.expect_revision)
    except (OSError, ValueError) as exc:
        raise SystemExit(f'Unsafe QA target: {exc}') from exc
    parsed = urlsplit(base)
    origin = (parsed.scheme, parsed.netloc)
    outside = []

    def offline(route):
        target = urlsplit(route.request.url)
        if (target.scheme, target.netloc) == origin:
            route.continue_()
        else:
            outside.append(route.request.url)
            route.abort()

    key = 'QA-' + uuid4().hex[:10]
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH') or None)
        def login(role):
            ctx = browser.new_context(service_workers='block', reduced_motion='reduce')
            revision = ctx.request.get(base + '/build-revision.txt')
            if not revision.ok or revision.text().strip() != args.expect_revision:
                raise SystemExit('Wrong QA revision; aborted before browser writes')
            ctx.route('**/*', offline)
            page = ctx.new_page()
            page.set_default_timeout(12000)
            page.goto(base + '/login')
            page.locator('input[autocomplete=username]').fill(role.lower() + '_demo')
            page.locator('input[type=password]').fill(os.environ['DEMO_' + role + '_PASSWORD'])
            page.locator('button[type=submit]').click()
            page.wait_for_url(base + '/')
            return page
        def click_write(page, button, suffix, method='POST'):
            with page.expect_response(lambda r: urlsplit(r.url).path.endswith(suffix) and r.request.method == method) as info:
                page.get_by_role('button', name=button, exact=True).click()
            reply = info.value
            assert reply.ok, f'{button} returned {reply.status}'
            return reply.json()
        a, r, admin = (login(role) for role in ('ANALYST', 'REVIEWER', 'ADMIN'))
        a.goto(base + '/warnings?city=CHANGSHA&date=2024-03-27&threshold=HEAVY')
        for sel, value in [('title', key), ('area', '长沙'), ('impact', '低洼路段积水'), ('reason', '归档回放达到 25 mm')]:
            a.locator('#w-' + sel).fill(value)
        created = click_write(a, '创建草稿', '/api/v1/warnings'); ident = created['public_id']
        detail = base + '/warnings/' + ident
        a.wait_for_url(detail)
        assert click_write(a, '提交审核', '/submit')['status'] == 'PENDING_REVIEW'
        # Keep an independent reviewer's unsent opinion open across a real resubmission.
        admin.goto(base + '/review')
        pending_comment = admin.get_by_label('审核意见：' + key, exact=True)
        pending_comment.fill('第一轮尚未提交的意见')
        r.goto(detail); r.get_by_label('审核意见').fill('请补充影响范围')
        assert click_write(r, '驳回', '/review')['decision'] == 'REJECT'
        a.reload(); expect(a.get_by_role('note')).to_contain_text('请补充影响范围')
        a.get_by_role('button', name='编辑草稿').click()
        a.locator('#edit-impact_text').fill('低洼路段及学校周边积水')
        assert click_write(a, '保存修改', '/'+ident, 'PATCH')['version_no'] == 2
        assert click_write(a, '重新提交审核', '/submit')['status'] == 'PENDING_REVIEW'
        admin.get_by_role('button', name='刷新', exact=True).click()
        expect(pending_comment).to_have_value('')
        admin.get_by_role('row').filter(has=pending_comment).get_by_role('button', name='驳回', exact=True).click()
        expect(admin.get_by_role('alert')).to_contain_text('驳回时必须填写审核意见')
        r.reload()
        history = r.locator('details').filter(has=r.locator('summary', has_text='历史版本'))
        history.locator('summary').click()
        choose = history.get_by_label('版本号')
        expect(choose).to_have_value('2')
        expect(history.get_by_text('低洼路段及学校周边积水', exact=True)).to_be_visible()
        choose.select_option('1')
        expect(history.get_by_text('低洼路段积水', exact=True)).to_be_visible()
        expect(history.get_by_text('低洼路段及学校周边积水', exact=True)).to_have_count(0)
        choose.select_option('2')
        expect(history.get_by_text('低洼路段及学校周边积水', exact=True)).to_be_visible()
        r.get_by_label('审核意见').fill('同意')
        assert click_write(r, '批准', '/review')['decision'] == 'APPROVE'
        r.get_by_label('发布或撤回原因').fill(key + '-发布')
        assert click_write(r, '发布', '/publish')['status'] == 'PUBLISHED'
        a.reload(); click_write(a, '接单', '/ack'); a.get_by_placeholder('处置说明（可选）').fill('现场处置完毕')
        assert click_write(a, '完成任务', '/complete')['status'] == 'COMPLETED'
        a.locator('#f-content').fill(key + '-反馈'); click_write(a, '提交反馈', '/feedback')
        r.get_by_label('发布或撤回原因').fill(key + '-撤回'); assert click_write(r, '撤回', '/withdraw')['status'] == 'WITHDRAWN'
        admin.goto(base + '/audit')
        for reason in (key + '-发布', key + '-撤回'):
            row = admin.get_by_role('row').filter(has_text=reason)
            expect(row).to_have_count(1); expect(row).to_contain_text('v2')
        assert not outside, f'Warning lifecycle attempted external requests: {outside!r}'
        browser.close()
        print('PASS browser: create, submit, reject, edit v2, resubmit, compare v1/v2 text, independent approve/publish, ack/complete, feedback, withdraw, audit v2')


if __name__ == '__main__':
    main()
