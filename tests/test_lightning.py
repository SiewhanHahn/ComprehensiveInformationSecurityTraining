from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest
from pydantic import ValidationError

from conftest import csrf_headers, notifications_for, review_body

POSITIVE = 'kstl-20250315-00z'
CONTROL = 'kstl-20250315-06z'
CASES = '/api/v1/lightning/cases'
CREATE = '/api/v1/warnings/lightning'
START = datetime(2025, 3, 15, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


@pytest.fixture
def lightning():
    return import_module('backend.app.services.lightning')


def draft(case_id=POSITIVE):
    return dict(case_id=case_id, title='雷电档案演练', area_text='KSTL 附近',
                impact_text='历史教学案例', reasoning_text='复核 HRRR 档案的有效预报时次')


def test_lightning_routes_and_hazard_are_registered_without_expanding_rainfall_cities():
    from backend.app.cities import CITIES, WARNING_CITIES
    from backend.app.hazards import HAZARDS
    from backend.app.main import app

    hazard = next(item for item in HAZARDS if item['code'] == 'THUNDERSTORM')
    assert hazard['status'] == 'IMPLEMENTED' and hazard['unit'] == '无量纲'
    assert {CASES, CASES + '/{case_id}/assessment', CREATE} <= set(app.openapi()['paths'])
    assert 'ST_LOUIS' not in CITIES and WARNING_CITIES['ST_LOUIS'] == '圣路易斯'


def test_archived_run_has_six_utc_valid_times_and_exact_values(lightning):
    forecast = lightning.assess_case(POSITIVE)
    case = forecast.case
    assert (case.city.code, case.station_id, case.forecast_grid.latitude) == ('ST_LOUIS', 'KSTL', 38.740802)
    assert case.initialized_at == START - 6 * HOUR and case.window_start == START
    assert case.archive_latest_modified_at == datetime(2025, 3, 14, 19, 8, 29, tzinfo=timezone.utc)
    assert case.initialized_at < case.archive_latest_modified_at < case.window_start
    assert forecast.forecast_window_end == START + 6 * HOUR
    assert [h.valid_at for h in forecast.hours] == [START + i * HOUR for i in range(1, 7)]
    assert [h.ltng for h in forecast.hours] == [0, 0.06, 0.08, 0.09, 0, 0]
    assert forecast.usable_hours == 6 and forecast.outcome == 'REACHED'
    assert forecast.reached_times == tuple(START + i * HOUR for i in (2, 3, 4))
    m = forecast.metric
    assert (m.value, m.threshold, m.unit, m.comparison) == (0.09, 0.05, '无量纲', '>=')


def test_later_window_is_a_zero_control_not_a_missing_forecast(lightning):
    f = lightning.assess_case(CONTROL)
    assert (f.case.initialized_at, f.case.window_start, f.forecast_window_end) == (START, START + 6 * HOUR, START + 12 * HOUR)
    assert f.case.archive_latest_modified_at == START.replace(hour=1, minute=6, second=24)
    assert all(h.ltng == 0 for h in f.hours) and f.usable_hours == 6
    assert f.outcome == 'NOT_REACHED' and f.metric.value == 0 and not f.reached_times


@pytest.mark.parametrize(('value', 'outcome'), [(0.049, 'NOT_REACHED'), (0.05, 'REACHED')])
def test_threshold_includes_exact_equality_and_end_but_excludes_start_and_outside(lightning, value, outcome):
    case = lightning.get_case(CONTROL)
    hours = case.forecast.hours
    last = hours[-1].model_copy(update={'ltng': value})
    before = last.model_copy(update={'valid_at': case.info.window_start, 'ltng': 1})
    after = last.model_copy(update={'valid_at': last.valid_at + HOUR, 'ltng': 1})
    reordered = case.forecast.model_copy(update={'hours': (after, last, *reversed(hours[:-1]), before)})
    f = lightning.assess_forecast(case.info, reordered)
    assert f.metric.value == value and f.outcome == outcome
    assert f.reached_times == ((last.valid_at,) if outcome == 'REACHED' else ())


@pytest.mark.parametrize('missing', ['absent', 'null', 'wrong_time'])
def test_missing_valid_hour_is_unknown_even_with_a_high_signal_at_another_hour(lightning, missing):
    case = lightning.get_case(POSITIVE)
    hours = list(case.forecast.hours)
    if missing == 'absent':
        hours.pop(0)
    elif missing == 'null':
        hours[0] = hours[0].model_copy(update={'ltng': None})
    else:
        hours[0] = hours[0].model_copy(update={'valid_at': hours[0].valid_at + timedelta(minutes=30)})
    f = lightning.assess_forecast(case.info, case.forecast.model_copy(update={'hours': tuple(hours)}))
    assert (f.usable_hours, f.outcome, f.metric, f.reached_times) == (5, 'INSUFFICIENT', None, ())
    assert len(f.hours) == 6 and f.hours[0].valid_at == START + HOUR and f.hours[0].ltng is None


@pytest.mark.parametrize('invalid', [-0.01, float('nan'), float('inf'), '0.09', True])
def test_ltng_rejects_invalid_numeric_inputs(lightning, invalid):
    hour = lightning.get_case(POSITIVE).forecast.hours[0]
    with pytest.raises(ValidationError, match='ltng'):
        type(hour).model_validate(hour.model_dump() | {'ltng': invalid})


def test_source_rejects_wrong_units_and_duplicate_equivalent_valid_times(lightning):
    series = lightning.get_case(POSITIVE).forecast
    with pytest.raises(ValidationError, match='unit'):
        type(series).model_validate(series.model_dump() | {'unit': '%'})
    data = series.model_dump()
    data['hours'][1]['valid_at'] = data['hours'][0]['valid_at'].astimezone(timezone(timedelta(hours=-6)))
    with pytest.raises(ValidationError, match='duplicate'):
        type(series).model_validate(data)


def test_forecast_timing_rejects_unproven_archive_clock_and_non_utc_window(lightning):
    info = lightning.get_case(POSITIVE).info
    for invalid in (info.initialized_at, info.window_start, info.window_start + HOUR):
        with pytest.raises(ValidationError, match='archive'):
            type(info).model_validate(info.model_dump() | {'archive_latest_modified_at': invalid})
    for invalid in (info.window_start + HOUR, info.window_start.astimezone(timezone(-HOUR))):
        with pytest.raises(ValidationError, match='window'):
            type(info).model_validate(info.model_dump() | {'window_start': invalid})


def test_station_records_are_independent_and_previous_storm_end_is_not_a_fresh_event(lightning):
    positive, quiet = lightning.replay(POSITIVE), lightning.replay(CONTROL)
    assert 'verification' not in positive.forecast.model_dump()
    assert positive.verification.station_id == 'KSTL'
    assert positive.verification.outcome == 'THUNDER_AND_LIGHTNING_REPORTED'
    reports = {r.observed_at.strftime('%H:%M'): r for r in positive.verification.observations}
    assert (reports['01:46'].thunder_code, reports['01:46'].lightning_remark) == ('TS', 'LTGCCCG')
    assert (reports['02:33'].thunder_code, reports['02:33'].lightning_remark) == ('+TSRA', 'LTGICCCCGCA')
    assert quiet.verification.outcome == 'NO_EVENT_IN_SAMPLES'
    first = quiet.verification.observations[0]
    assert first.observed_at == START.replace(hour=6, minute=12)
    assert first.end_remark == 'TSE06' and first.thunder_code is None and first.lightning_remark is None


@pytest.mark.parametrize('problem', ['missing', 'malformed', 'different_station', 'outside_window'])
def test_unavailable_station_evidence_does_not_mutate_the_forecast(lightning, monkeypatch, tmp_path, problem):
    case = lightning.get_case(POSITIVE)
    expected = lightning.assess_case(POSITIVE)
    reports = lightning._read_station_reports(POSITIVE)
    monkeypatch.setattr(lightning, 'get_case', lambda _: case)
    monkeypatch.setattr(lightning, '_DATA_DIR', tmp_path)
    target = tmp_path / f'{POSITIVE}-station.json'
    if problem == 'malformed':
        target.write_text('{"observations":"broken"}', encoding='utf-8')
    if problem == 'different_station':
        target.write_text(reports.model_copy(update={'station_id': 'KORD'}).model_dump_json(), encoding='utf-8')
    if problem == 'outside_window':
        row = reports.observations[1]
        observations = (row.model_copy(update={'observed_at': START}),
                        row.model_copy(update={'observed_at': START + 7 * HOUR}))
        target.write_text(reports.model_copy(update={'observations': observations}).model_dump_json(), encoding='utf-8')
    assert lightning.catalog().cases[0] == case.info
    replay = lightning.replay(POSITIVE)
    assert replay.verification is None and replay.forecast == expected


@pytest.mark.integration
def test_lightning_warning_rejects_unapproved_inputs_and_unavailable_forecasts(new_client, login, lightning, monkeypatch):
    assert new_client().get(CASES).status_code == 401
    analyst, a = login('analyst_demo')
    viewer, v = login('viewer_demo')
    assert [c['case_id'] for c in viewer.get(CASES).json()['cases']] == [POSITIVE, CONTROL]
    assert viewer.post(CREATE, json=draft(), headers=csrf_headers(v)).status_code == 403
    assert analyst.post(CREATE, json=draft()).status_code == 403
    assert analyst.get(CASES + '/not-a-case/assessment').status_code == 404
    assert analyst.post(CREATE, json=draft('not-a-case'), headers=csrf_headers(a)).status_code == 404
    for field in ('verification', 'city_code', 'ltng', 'forecast'):
        assert analyst.post(CREATE, json=draft() | {field: None}, headers=csrf_headers(a)).status_code == 422

    def assert_refused(case_id, code):
        response = analyst.post(CREATE, json=draft(case_id), headers=csrf_headers(a))
        assert response.status_code == 409 and response.json()['error']['code'] == code

    assert_refused(CONTROL, 'THRESHOLD_NOT_REACHED')
    case = lightning.get_case(POSITIVE)
    missing = case.forecast.model_copy(update={'hours': case.forecast.hours[:-1]})
    with monkeypatch.context() as mp:
        mp.setattr(lightning, 'get_case', lambda _: case.model_copy(update={'forecast': missing}))
        assert_refused(POSITIVE, 'PARTIAL_DATA')
    undated = case.info.model_copy(update={'archive_latest_modified_at': None})
    monkeypatch.setattr(lightning, 'get_case', lambda _: case.model_copy(update={'info': undated}))
    assert_refused(POSITIVE, 'SOURCE_NOT_VERIFIED')


@pytest.mark.integration
def test_lightning_stores_forecast_only_and_keeps_existing_lifecycle(login, lightning, monkeypatch,
                                                            created_warnings, created_subscriptions):
    analyst, a = login('analyst_demo')
    reviewer, r = login('reviewer_demo')
    viewer, v = login('viewer_demo')
    sub = viewer.post('/api/v1/subscriptions', json={'hazard_type': 'THUNDERSTORM', 'city_code': 'ST_LOUIS'},
                      headers=csrf_headers(v))
    assert sub.status_code in (200, 201), sub.text
    created_subscriptions.append(sub.json()['id'])
    expected = lightning.assess_case(POSITIVE).model_dump(mode='json')

    def unexpected_station_read(*args):
        pytest.fail('writing a lightning draft must not read verification')

    monkeypatch.setattr(lightning, '_read_station_reports', unexpected_station_read)
    response = analyst.post(CREATE, json=draft(), headers=csrf_headers(a))
    assert response.status_code == 200, response.text
    row = response.json()
    created_warnings.append(row['public_id'])
    assert (row['hazard_type'], row['city_name'], row['valid_date'], row['fused_mm'], row['status']) == (
        'THUNDERSTORM', '圣路易斯', '2025-03-15', None, 'DRAFT')
    detail = f"/api/v1/warnings/{row['public_id']}"
    stored = analyst.get(detail).json()
    assert stored['lightning_assessment'] == expected and 'verification' not in stored
    assert stored['snow_assessment'] is None and stored['typhoon_assessment'] is None
    assert analyst.post(detail + '/submit', headers=csrf_headers(a)).status_code == 200
    review = review_body(reviewer, row['public_id'], 'APPROVE', '核对历史预报')
    assert reviewer.post(detail + '/review', headers=csrf_headers(r), json=review).status_code == 200
    assert reviewer.post(detail + '/publish', headers=csrf_headers(r)).json()['status'] == 'PUBLISHED'
    assert notifications_for(viewer, row['public_id'])
    assert viewer.get(detail).json()['lightning_assessment'] == expected
