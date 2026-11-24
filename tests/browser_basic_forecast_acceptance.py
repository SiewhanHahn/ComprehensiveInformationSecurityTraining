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
        expect(page.get_by_text('4 类端到端实现 · 4 类基础预测', exact=False)).to_be_visible()
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
        # Native badInput can leave the Vue model already empty; the visible result must still clear.
        fifth_day.press('-')
        assert fifth_day.evaluate('(el) => el.validity.badInput')
        expect(forecast).to_have_count(0)
        fifth_day.press('Backspace')
        page.set_viewport_size({'width': 1360, 'height': 920})
        page.get_by_role('link', name='查看灾种覆盖').click()
        page.get_by_role('link', name='试算高温风险').click()
        page.wait_for_url(base + '/basic-forecast?hazard=heat')
        heat = page.get_by_role('region', name='高温试算输入')
        expect(heat.get_by_role('spinbutton')).to_have_count(24)
        expect(page.get_by_role('link', name='高温', exact=True)).to_have_attribute('aria-current', 'page')
        forecast = page.get_by_role('region', name='高温预测结果')
        outcome = forecast.get_by_test_id('temperature-outcome')
        peak = forecast.get_by_test_id('temperature-extreme')
        qualifying = forecast.get_by_test_id('temperature-qualifying')
        calculate = heat.get_by_role('button', name='计算高温风险')
        trial = '/api/v1/basic-forecast/heat/assessment'
        heat.get_by_label('地点', exact=True).fill('现场教学点')
        heat.get_by_label('预测起点（UTC 整点）').fill('2025-07-01T18:00')
        boundary = heat.get_by_label('第 14 小时气温', exact=False)
        expect(heat.get_by_text('2025-07-02 07:00', exact=True)).to_be_visible()
        result = compute()
        assert result['outcome'] == 'NOT_REACHED' and result['extreme_c'] == 34.9
        expect(outcome).to_have_text('未达高温教学阈值')
        expect(peak).to_have_text('34.9 °C')

        boundary.fill('35.0')
        expect(forecast).to_have_count(0)
        result = compute()
        assert result['location'] == '现场教学点' and result['outcome'] == 'REACHED'
        assert result['qualifying_hours'] == ['2025-07-02T07:00:00Z']
        expect(outcome).to_have_text('达到高温教学阈值')
        expect(peak).to_have_text('35 °C')
        expect(qualifying).to_contain_text('2025-07-02 07:00')
        expect(forecast.get_by_text('此结果不是官方高温预警', exact=False)).to_be_visible()
        if args.evidence:
            forecast.screenshot(path=args.evidence / 'heat-boundary.png')

        boundary.fill('')
        result = compute()
        assert result['usable_hours'] == 23 and result['extreme_c'] is None and result['qualifying_hours'] == []
        expect(outcome).to_have_text('无法判断')
        expect(peak).to_have_count(0)
        expect(qualifying).to_have_count(0)
        page.set_viewport_size({'width': 390, 'height': 844})
        for region in (heat, forecast):
            assert region.evaluate('(el) => el.scrollWidth <= el.clientWidth'), 'Heat trial overflows on mobile'
        # Hold a real heat result while switching the keyed form to cold.
        pending = []

        def hold_response(route):
            pending.append(route)

        late_endpoint = '**/api/v1/basic-forecast/heat/assessment'
        page.route(late_endpoint, hold_response)
        with page.expect_request(lambda r: urlsplit(r.url).path == trial and r.method == 'POST'):
            calculate.click()
        expect(heat.get_by_role('button', name='正在试算…')).to_be_disabled()
        page.get_by_role('link', name='低温', exact=True).click()
        expect(forecast).to_have_count(0)
        page.wait_for_url(base + '/basic-forecast?hazard=cold')
        cold = page.get_by_role('region', name='低温试算输入')
        expect(cold.get_by_role('spinbutton')).to_have_count(24)
        forecast = page.get_by_role('region', name='低温预测结果')
        outcome = forecast.get_by_test_id('temperature-outcome')
        minimum = forecast.get_by_test_id('temperature-extreme')
        qualifying = forecast.get_by_test_id('temperature-qualifying')
        calculate = cold.get_by_role('button', name='计算低温风险')
        trial = '/api/v1/basic-forecast/cold/assessment'
        location = cold.get_by_label('地点', exact=True)
        location.fill('A' * 80)
        assert compute()['extreme_c'] == 0.1
        assert len(pending) == 1, 'The heat request must still be held after switching mode'
        old_route = pending[0]
        response = old_route.fetch()
        assert response.ok
        with page.expect_response(lambda r: urlsplit(r.url).path == '/api/v1/basic-forecast/heat/assessment') as old_reply:
            old_route.fulfill(response=response)
        assert old_reply.value.ok
        old_reply.value.finished()
        page.unroute(late_endpoint, hold_response)
        expect(page.get_by_role('region', name='高温预测结果')).to_have_count(0)
        expect(calculate).to_be_enabled()
        expect(outcome).to_have_text('未达低温教学阈值')
        expect(minimum).to_have_text('0.1 °C')
        assert forecast.evaluate('(el) => el.scrollWidth <= el.clientWidth'), 'Long location overflows on mobile'

        boundary = cold.get_by_label('第 5 小时气温', exact=False)
        boundary.fill('0.0')
        expect(forecast).to_have_count(0)
        location.fill('现场教学点')
        result = compute()
        assert result['outcome'] == 'REACHED' and result['qualifying_hours'] == ['2025-01-12T04:00:00Z']
        expect(outcome).to_have_text('达到低温教学阈值')
        expect(minimum).to_have_text('0 °C')
        expect(qualifying).to_contain_text('2025-01-12 04:00')
        expect(forecast.get_by_text('不是寒潮预报', exact=False)).to_be_visible()
        if args.evidence:
            page.set_viewport_size({'width': 1360, 'height': 920})
            forecast.screenshot(path=args.evidence / 'cold-boundary.png')

        boundary.fill('')
        result = compute()
        assert result['usable_hours'] == 23 and result['extreme_c'] is None and result['qualifying_hours'] == []
        expect(outcome).to_have_text('无法判断')
        expect(minimum).to_have_count(0)
        expect(qualifying).to_have_count(0)
        page.get_by_role('link', name='干旱', exact=True).click()
        expect(forecast).to_have_count(0)
        expect(page.get_by_role('region', name='干旱试算输入')).to_be_visible()
        page.get_by_role('link', name='查看灾种覆盖').click()
        expect(page.get_by_text('标记「基础预测」的灾种可输入数据做教学试算', exact=False)).to_be_visible()
        page.get_by_role('link', name='试算风雹风险').click()
        page.wait_for_url(base + '/basic-forecast?hazard=wind-hail')
        wind = page.get_by_role('region', name='风雹试算输入')
        expect(wind.get_by_role('spinbutton')).to_have_count(6)
        expect(wind.get_by_role('combobox')).to_have_count(6)
        forecast = page.get_by_role('region', name='风雹预测结果')
        gust_outcome = forecast.get_by_test_id('gust-outcome')
        gust_peak = forecast.get_by_test_id('gust-peak')
        hail_outcome = forecast.get_by_test_id('hail-outcome')
        hail_qualifying = forecast.get_by_test_id('hail-qualifying')
        calculate = wind.get_by_role('button', name='计算风雹风险')
        trial = '/api/v1/basic-forecast/wind-hail/assessment'
        gust = wind.get_by_label('第 6 小时阵风（m/s）')
        hail_signal = wind.get_by_label('第 6 小时冰雹信号')

        gust.fill('16.9')
        result = compute()
        assert result['gust']['max_gust_mps'] == 16.9 and result['hail']['usable_hours'] == 6
        expect(gust_outcome).to_have_text('阵风未达教学阈值')
        expect(hail_outcome).to_have_text('明确无雹信号')
        gust.fill('17.0')
        expect(forecast).to_have_count(0)
        result = compute()
        assert result['gust']['qualifying_hours'] == ['2025-07-02T02:00:00Z']
        expect(gust_outcome).to_have_text('阵风达到教学阈值')
        expect(gust_peak).to_have_text('17 m/s')
        expect(hail_outcome).to_have_text('明确无雹信号')

        hail_signal.select_option(label='有明确雹信号')
        result = compute()
        assert result['hail']['qualifying_hours'] == ['2025-07-02T02:00:00Z']
        expect(gust_outcome).to_have_text('阵风达到教学阈值')
        expect(hail_outcome).to_have_text('有明确雹信号')
        expect(hail_qualifying).to_contain_text('2025-07-02 02:00')
        if args.evidence:
            forecast.screenshot(path=args.evidence / 'wind-hail-joint.png')

        hail_signal.select_option(label='缺测')
        result = compute()
        assert result['hail']['usable_hours'] == 5 and result['hail']['qualifying_hours'] == []
        expect(gust_outcome).to_have_text('阵风达到教学阈值')
        expect(hail_outcome).to_have_text('雹信号缺测，无法判断')
        expect(hail_qualifying).to_have_count(0)
        if args.evidence:
            forecast.screenshot(path=args.evidence / 'wind-hail-missing.png')

        hail_signal.select_option(label='有明确雹信号')
        gust.fill('')
        result = compute()
        assert result['gust']['usable_hours'] == 5 and result['gust']['max_gust_mps'] is None
        expect(gust_outcome).to_have_text('阵风缺测，无法判断')
        expect(gust_peak).to_have_count(0)
        expect(hail_outcome).to_have_text('有明确雹信号')
        page.set_viewport_size({'width': 390, 'height': 844})
        for region in (wind, forecast):
            assert region.evaluate('(el) => el.scrollWidth <= el.clientWidth'), 'Wind-hail trial overflows on mobile'
        assert context.request.get(base + '/api/v1/warnings').json() == warnings
        assert not outside, f'Basic forecasts attempted external requests: {outside!r}'
        browser.close()
    print('PASS: offline drought (16 / 2 / 14 days), heat (34.9 / 35.0 °C), cold (0.1 / 0.0 °C), wind-hail (17.0 m/s; false/true/unknown independent), missing input, mobile, no warning changes')


if __name__ == '__main__':
    main()
