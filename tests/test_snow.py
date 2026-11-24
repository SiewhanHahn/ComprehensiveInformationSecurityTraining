from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest
from pydantic import ValidationError

from conftest import csrf_headers, notifications_for, review_body

POSITIVE = 'jinan-20250302'
CONTROL = 'jinan-20250304'
CASES = '/api/v1/snow/cases'
CREATE = '/api/v1/warnings/snow'


@pytest.fixture
def snow():
    return import_module('backend.app.services.snow')


def draft(case_id=POSITIVE):
    return dict(case_id=case_id, title='济南强降雪演练', area_text='济南站附近',
                impact_text='历史教学案例', reasoning_text='归档预报达到教学阈值')


def test_snow_is_a_distinct_registered_hazard_and_has_case_routes():
    from backend.app.hazards import HAZARDS
    from backend.app.main import app

    hazard = next(item for item in HAZARDS if item['code'] == 'SNOW_DISASTER')
    assert hazard['status'] == 'IMPLEMENTED' and hazard['unit'] == 'cm'
    assert {CASES, CASES + '/{case_id}/assessment', CREATE} <= set(app.openapi()['paths'])


def test_jinan_archive_windows_match_hand_calculation_and_independent_station(snow):
    positive, control = snow.replay(POSITIVE), snow.replay(CONTROL)
    start = datetime(2025, 3, 2, tzinfo=timezone.utc)
    f = positive.forecast
    assert f.case.city.code == 'JINAN' and f.case.forecast_grid.longitude == 117.011795
    assert f.case.initialized_at == start - timedelta(hours=12)
    assert f.case.window_start == start and f.forecast_window_end == start + timedelta(hours=24)
    assert [h.valid_at for h in f.hours] == [start + timedelta(hours=i) for i in range(1, 25)]
    assert f.outcome == 'REACHED' and f.usable_hours == 24
    assert (f.metric.value, f.metric.unit, f.metric.threshold, f.metric.comparison) == (12.74, 'cm', 10.0, '>=')
    assert (f.min_temperature_c, f.snow_period_start, f.snow_period_end) == (
        -4.1, start + timedelta(hours=2), start + timedelta(hours=14))
    assert positive.verification.station_id == '54823099999'
    assert len(positive.verification.observations) == 8
    assert positive.verification.outcome == 'SNOW_REPORTED'
    assert [(o.observed_at.hour, o.code) for o in positive.verification.observations if o.code in {'74', '70'}] == [
        (6, '74'), (9, '70'), (12, '70')]
    assert control.forecast.outcome == 'NOT_REACHED' and control.forecast.metric.value == 0
    assert control.forecast.min_temperature_c == -4.4
    assert control.forecast.snow_period_start is None and control.forecast.snow_period_end is None
    assert control.verification.outcome == 'NO_SNOW_IN_SAMPLES'


def test_snow_assessment_uses_start_exclusive_end_inclusive_and_threshold_is_exact(snow):
    case = snow.get_case(CONTROL)
    hours = case.forecast.hours
    endpoints = (
        hours[-1].model_copy(update={'snowfall_cm': 9.99}),
        hours[-1].model_copy(update={'valid_at': case.info.window_start, 'snowfall_cm': 50}),
        hours[-1].model_copy(update={'valid_at': hours[-1].valid_at + timedelta(hours=1), 'snowfall_cm': 50}),
    )
    forecast = case.forecast.model_copy(update={'hours': tuple(reversed(hours[:-1])) + endpoints})
    result = snow.assess_forecast(case.info, forecast)
    assert result.metric.value == 9.99 and result.outcome == 'NOT_REACHED'
    last = endpoints[0].model_copy(update={'snowfall_cm': 10.0, 'temperature_c': 0.2})
    result = snow.assess_forecast(case.info, forecast.model_copy(update={'hours': hours[:-1] + (last,)}))
    assert result.metric.value == 10 and result.outcome == 'REACHED'
    assert result.snow_period_end == result.forecast_window_end


@pytest.mark.parametrize('missing', ['hour', 'snowfall_cm', 'temperature_c'])
def test_missing_snow_input_is_unknown_not_low_risk(snow, missing):
    case = snow.get_case(POSITIVE)
    data = case.forecast.model_dump()
    if missing == 'hour':
        # 24 timestamps alone are not enough: a half-hour stamp cannot replace an expected end.
        data['hours'][0]['valid_at'] += timedelta(minutes=30)
    else:
        data['hours'][0][missing] = None
    series = type(case.forecast).model_validate(data)
    result = snow.assess_forecast(case.info, series)
    assert result.outcome == 'INSUFFICIENT' and result.usable_hours == 23
    assert result.metric is None and result.min_temperature_c is None
    assert result.snow_period_start is None and result.snow_period_end is None


@pytest.mark.parametrize(('field', 'wrong'), [('snowfall_unit', 'mm'), ('temperature_unit', '°F')])
def test_snow_source_rejects_incompatible_units_instead_of_guessing(snow, field, wrong):
    series = snow.get_case(POSITIVE).forecast
    with pytest.raises(ValidationError, match=field):
        type(series).model_validate(series.model_dump() | {field: wrong})


def test_snow_source_rejects_negative_nonfinite_and_duplicate_values(snow):
    series = snow.get_case(POSITIVE).forecast
    data = series.model_dump()
    data['hours'][1]['valid_at'] = data['hours'][0]['valid_at']
    with pytest.raises(ValidationError, match='duplicate'):
        type(series).model_validate(data)
    for field, value in [('snowfall_cm', -0.01), ('snowfall_cm', float('nan')), ('temperature_c', float('inf'))]:
        with pytest.raises(ValidationError, match=field):
            type(series.hours[0]).model_validate(series.hours[0].model_dump() | {field: value})


def test_snow_cannot_set_window_before_availability_allowance(snow):
    info = snow.get_case(POSITIVE).info
    for stamp in (info.window_start - timedelta(hours=1), info.window_start + timedelta(minutes=1)):
        with pytest.raises(ValidationError, match='window'):
            type(info).model_validate(info.model_dump() | {'window_start': stamp})


def test_snow_observations_are_filtered_separately_and_cannot_change_forecast(snow, monkeypatch):
    case = snow.get_case(POSITIVE)
    expected = snow.replay(POSITIVE).forecast
    outside = case.verification.observations[0].model_copy(update={'observed_at': case.info.window_start})
    future = outside.model_copy(update={'observed_at': expected.forecast_window_end + timedelta(hours=1)})
    reference = case.verification.model_copy(update={'observations': (outside, future)})
    monkeypatch.setattr(snow, 'get_case', lambda _: case.model_copy(update={'verification': reference}))
    replay = snow.replay(POSITIVE)
    assert replay.forecast == expected and replay.verification is None
    assert 'verification' not in replay.forecast.model_dump()


@pytest.mark.integration
def test_snow_allows_only_controlled_reached_case_drafts(new_client, login, snow, monkeypatch):
    assert new_client().get(CASES).status_code == 401
    analyst, a = login('analyst_demo')
    viewer, v = login('viewer_demo')
    assert [c['case_id'] for c in viewer.get(CASES).json()['cases']] == [POSITIVE, CONTROL]
    assert 'JINAN' not in {city['code'] for city in viewer.get('/api/v1/cities').json()}
    assert {'code': 'JINAN', 'name': '济南'} in viewer.get('/api/v1/warning-cities').json()
    assert viewer.post(CREATE, json=draft(), headers=csrf_headers(v)).status_code == 403
    assert analyst.post(CREATE, json=draft()).status_code == 403
    assert analyst.get(CASES + '/nonexistent/assessment').status_code == 404
    for field in ('verification', 'city_code', 'snowfall_cm'):
        assert analyst.post(CREATE, json=draft() | {field: None}, headers=csrf_headers(a)).status_code == 422
    no_risk = analyst.get(CASES + f'/{CONTROL}/assessment').json()
    assert no_risk['forecast']['outcome'] == 'NOT_REACHED'
    refused = analyst.post(CREATE, json=draft(CONTROL), headers=csrf_headers(a))
    assert refused.status_code == 409 and refused.json()['error']['code'] == 'THRESHOLD_NOT_REACHED'

    case = snow.get_case(POSITIVE)
    series = case.forecast.model_copy(update={'hours': case.forecast.hours[:-1]})
    monkeypatch.setattr(snow, 'get_case', lambda _: case.model_copy(update={'forecast': series}))
    assert analyst.get(CASES + f'/{POSITIVE}/assessment').json()['forecast']['outcome'] == 'INSUFFICIENT'
    refused = analyst.post(CREATE, json=draft(), headers=csrf_headers(a))
    assert refused.status_code == 409 and refused.json()['error']['code'] == 'PARTIAL_DATA'


@pytest.mark.integration
def test_snow_publishes_forecast_only_and_uses_shared_lifecycle(login, created_warnings, subscriber, created_subscriptions):
    from sqlalchemy import select
    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, Warning

    analyst, a = login('analyst_demo')
    reviewer, r = login('reviewer_demo')
    viewer, v = subscriber
    sub = viewer.post('/api/v1/subscriptions', json={'hazard_type': 'SNOW_DISASTER', 'city_code': 'JINAN'}, headers=csrf_headers(v))
    assert sub.status_code == 200, sub.text
    created_subscriptions.append(sub.json()['id'])
    replay = analyst.get(CASES + f'/{POSITIVE}/assessment').json()
    assert replay['verification']['outcome'] == 'SNOW_REPORTED'
    response = analyst.post(CREATE, json=draft(), headers=csrf_headers(a))
    assert response.status_code == 200, response.text
    saved = response.json()
    ident = saved['public_id']
    created_warnings.append(ident)
    assert (saved['hazard_type'], saved['status'], saved['fused_mm']) == ('SNOW_DISASTER', 'DRAFT', None)
    assert saved['city_name'] == '济南' and saved['valid_date'] == '2025-03-02' and saved['metric']['value'] == 12.74
    path = f'/api/v1/warnings/{ident}'
    assert viewer.get(path).status_code == 404 and not notifications_for(viewer, ident)
    evidence = analyst.get(path).json()['snow_assessment']
    assert evidence == replay['forecast'] and 'verification' not in evidence
    assert analyst.post(path + '/submit', headers=csrf_headers(a)).status_code == 200
    assert reviewer.post(path + '/publish', headers=csrf_headers(r)).status_code == 409
    assert reviewer.post(path + '/review', json=review_body(reviewer, ident, 'APPROVE', '核对预报'), headers=csrf_headers(r)).status_code == 200
    assert reviewer.post(path + '/publish', json={'reason': '教学演练'}, headers=csrf_headers(r)).json()['status'] == 'PUBLISHED'
    visible = viewer.get(path).json()
    assert visible['snow_assessment'] == evidence and visible['models'] == [] and visible['proxy_label_mm'] is None
    published = notifications_for(viewer, ident)
    assert len(published) == 1 and '12.74 cm' in published[0]['body'] and '四模式融合' not in published[0]['body']
    tasks = analyst.get('/api/v1/response-tasks', params={'warning': ident}).json()
    assert len(tasks) == 1 and tasks[0]['status'] == 'PENDING'
    task_path = f"/api/v1/response-tasks/{tasks[0]['id']}"
    assert analyst.post(task_path + '/ack', headers=csrf_headers(a)).status_code == 200
    assert analyst.post(task_path + '/complete', json={'note': '演练处置完成'}, headers=csrf_headers(a)).status_code == 200
    assert analyst.post(path + '/feedback', json={'response_status': 'COMPLETED', 'content': '演练完成'}, headers=csrf_headers(a)).status_code == 200
    assert reviewer.post(path + '/withdraw', json={'reason': '演练结束'}, headers=csrf_headers(r)).json()['status'] == 'WITHDRAWN'
    assert viewer.get(path).status_code == 404
    with SessionLocal() as db:
        stored = db.scalar(select(Warning).where(Warning.public_id == ident)).warning_result
        assert stored.fusion_run_id is None and stored.threshold_id is None and stored.fused_mm is None
        assert stored.assessment_json == evidence
        check = select(AuditLog).where(AuditLog.resource_id == ident, AuditLog.action.in_(['WARNING_PUBLISH', 'WARNING_WITHDRAW']))
        assert {row.action: (row.reason, row.resource_version) for row in db.scalars(check)} == {
            'WARNING_PUBLISH': ('教学演练', 1), 'WARNING_WITHDRAW': ('演练结束', 1),
        }
