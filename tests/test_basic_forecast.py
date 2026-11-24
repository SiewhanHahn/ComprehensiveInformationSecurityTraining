from datetime import UTC, date, datetime, timedelta
from importlib import import_module

import pytest
from pydantic import ValidationError

from conftest import csrf_headers

DROUGHT_URL = '/api/v1/basic-forecast/drought/assessment'
HEAT_URL = '/api/v1/basic-forecast/heat/assessment'
COLD_URL = '/api/v1/basic-forecast/cold/assessment'
WIND_HAIL_URL = '/api/v1/basic-forecast/wind-hail/assessment'


@pytest.fixture
def basic():
    return import_module('backend.app.services.basic_forecast')


def sample(**overrides):
    return dict(location='课程示例点', start_date='2025-07-01', antecedent_dry_days=9,
                daily_rain_mm=[0.0, 0.2, 0.0, 0.3, 0.0, 0.8, 0.0]) | overrides


def test_drought_endpoint_and_basic_hazard_registration():
    from backend.app.hazards import HAZARDS
    from backend.app.main import app

    drought = next(item for item in HAZARDS if item['code'] == 'DROUGHT')
    assert drought['status'] == 'BASIC' and DROUGHT_URL in app.openapi()['paths']


@pytest.mark.parametrize(('prior_days', 'fifth_rain', 'end_days', 'outcome'), [
    (9, 0.99, 16, 'REACHED'), (7, 0.0, 14, 'REACHED'), (6, 0.0, 13, 'NOT_REACHED'),
    (9, 1.0, 2, 'NOT_REACHED'),
])
def test_drought_uses_dry_streak_at_end_of_seventh_day(basic, prior_days, fifth_rain, end_days, outcome):
    data = sample(antecedent_dry_days=prior_days)
    data['daily_rain_mm'][4] = fifth_rain
    result = basic.assess_drought(basic.DroughtInput.model_validate(data))
    assert result.location == '课程示例点'
    assert (result.start_date, result.end_date) == (date(2025, 7, 1), date(2025, 7, 7))
    assert (result.end_dry_days, result.outcome, result.usable_days) == (end_days, outcome, 7)
    assert (result.dry_day_below_mm, result.continuation_at_least_days) == (1.0, 14)
    assert [day.valid_date.day for day in result.days] == list(range(1, 8))
    if fifth_rain == 1.0:
        assert [day.dry_days for day in result.days] == [10, 11, 12, 13, 0, 1, 2]


@pytest.mark.parametrize(('overrides', 'usable_days'), [
    ({'antecedent_dry_days': None}, 7),
    ({'daily_rain_mm': [0, 0, None, 0, 0, 0, 0]}, 6),
])
def test_drought_missing_input_does_not_become_zero_or_below_threshold(basic, overrides, usable_days):
    result = basic.assess_drought(basic.DroughtInput.model_validate(sample(**overrides)))
    assert result.outcome == 'INSUFFICIENT' and result.end_dry_days is None
    assert result.usable_days == usable_days and all(day.dry_days is None for day in result.days)


@pytest.mark.parametrize(('field', 'invalid'), [
    ('location', '   '), ('start_date', '2025-07-01T00:00:00Z'), ('start_date', '9999-12-30'),
    ('antecedent_dry_days', True), ('antecedent_dry_days', -1), ('antecedent_dry_days', '9'),
    ('daily_rain_mm', [0] * 6), ('daily_rain_mm', [0] * 8),
    ('daily_rain_mm', [0, 0, -0.01, 0, 0, 0, 0]), ('daily_rain_mm', [0, 0, True, 0, 0, 0, 0]),
    ('daily_rain_mm', [0, 0, '0.2', 0, 0, 0, 0]), ('daily_rain_mm', [0, 0, float('inf'), 0, 0, 0, 0]),
])
def test_wrong_clock_shape_and_numeric_types_are_rejected(basic, field, invalid):
    with pytest.raises(ValidationError, match=field):
        basic.DroughtInput.model_validate(sample(**{field: invalid}))


@pytest.mark.integration
def test_drought_trial_is_authenticated_validated_and_does_not_create_a_warning(new_client, login):
    assert new_client().post(DROUGHT_URL, json=sample()).status_code == 401
    client, token = login('viewer_demo')
    analyst, _ = login('analyst_demo')
    before = analyst.get('/api/v1/warnings').json()
    assert client.post(DROUGHT_URL, json=sample()).status_code == 403
    headers = csrf_headers(token)
    result = client.post(DROUGHT_URL, headers=headers, json=sample())
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert (result.json()['end_dry_days'], result.json()['outcome']) == (16, 'REACHED')
    assert client.post(DROUGHT_URL, headers=headers, json=sample(extra_result=0)).status_code == 422
    assert analyst.get('/api/v1/warnings').json() == before


def temperature_sample(**overrides):
    return dict(location='课程示例点', start_at='2024-02-28T18:00:00Z',
                hourly_temperature_c=[21.0] * 24) | overrides


def test_heat_endpoint_and_basic_hazard_registration():
    from backend.app.hazards import HAZARDS
    from backend.app.main import app

    heat = next(item for item in HAZARDS if item['code'] == 'HEATWAVE')
    response = app.openapi()['paths'][HEAT_URL]['post']['responses']['200']
    assert response['content']['application/json']['schema']['$ref'] == '#/components/schemas/HourlyTemperatureAssessment'
    assert heat['status'] == 'BASIC' and heat['thresholds'][0]['value'] == 35.0


@pytest.mark.parametrize(('values', 'outcome', 'peak', 'qualified_offsets'), [
    ([34.9] * 24, 'NOT_REACHED', 34.9, []),
    ([22.0] * 23 + [35.0], 'REACHED', 35.0, [23]),
    ([35.0, 36.2] + [22.0] * 21 + [35.0], 'REACHED', 36.2, [0, 1, 23]),
])
def test_heat_uses_maximum_and_all_qualifying_utc_hours(basic, values, outcome, peak, qualified_offsets):
    body = basic.HourlyTemperatureInput.model_validate(temperature_sample(hourly_temperature_c=values))
    result = basic.assess_heat(body)
    start = datetime(2024, 2, 28, 18, tzinfo=UTC)
    assert result.hazard_type == 'HEATWAVE' and result.location == '课程示例点'
    assert (result.start_at, result.end_at, result.usable_hours) == (start, datetime(2024, 2, 29, 17, tzinfo=UTC), 24)
    assert (result.threshold_c, result.extreme_c, result.outcome) == (35.0, peak, outcome)
    assert result.qualifying_hours == [start + timedelta(hours=i) for i in qualified_offsets]


@pytest.mark.parametrize('values', [[36.0] + [20.0] * 22 + [None], [None] * 24])
def test_heat_does_not_report_peak_or_outcome_from_incomplete_hours(basic, values):
    body = basic.HourlyTemperatureInput.model_validate(temperature_sample(hourly_temperature_c=values))
    result = basic.assess_heat(body)
    assert (result.outcome, result.extreme_c, result.qualifying_hours) == ('INSUFFICIENT', None, [])
    assert result.usable_hours == sum(value is not None for value in values)


@pytest.mark.parametrize(('field', 'invalid'), [
    ('location', '  '), ('location', 'x' * 81),
    ('start_at', '2024-02-28T18:00:00'), ('start_at', '2024-02-28T18:00:00+08:00'),
    ('start_at', '2024-02-28T18:30:00Z'), ('start_at', '2024-02-28T18:00:01Z'),
    ('start_at', '2025-02-29T18:00:00Z'), ('start_at', '9999-12-31T01:00:00Z'),
    ('start_at', 1709143200),
    ('hourly_temperature_c', [0] * 23), ('hourly_temperature_c', [0] * 25),
    ('hourly_temperature_c', [0] * 23 + [True]), ('hourly_temperature_c', [0] * 23 + ['35']),
    ('hourly_temperature_c', [0] * 23 + [float('inf')]), ('hourly_temperature_c', [0] * 23 + [float('nan')]),
])
def test_temperature_window_rejects_invalid_time_shape_or_number(basic, field, invalid):
    with pytest.raises(ValidationError, match=field):
        basic.HourlyTemperatureInput.model_validate(temperature_sample(**{field: invalid}))


@pytest.mark.integration
def test_heat_trial_auth_csrf_validation_and_read_only_response(new_client, login):
    body = temperature_sample(location=' 可编辑课程点 ', hourly_temperature_c=[-0.5] * 23 + [35.0])
    assert new_client().post(HEAT_URL, json=body).status_code == 401
    client, token = login('viewer_demo')
    analyst, _ = login('analyst_demo')
    before = analyst.get('/api/v1/warnings').json()
    assert client.post(HEAT_URL, json=body).status_code == 403
    headers = csrf_headers(token)
    result = client.post(HEAT_URL, headers=headers, json=body)
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assessment = result.json()
    assert (assessment['outcome'], assessment['extreme_c'], assessment['location']) == ('REACHED', 35.0, '可编辑课程点')
    assert assessment['qualifying_hours'] == ['2024-02-29T17:00:00Z']
    assert client.post(HEAT_URL, headers=headers, json=body | {'outcome': 'REACHED'}).status_code == 422
    assert analyst.get('/api/v1/warnings').json() == before


def test_cold_endpoint_and_basic_hazard_registration():
    from backend.app.hazards import HAZARDS
    from backend.app.main import app

    cold = next(item for item in HAZARDS if item['code'] == 'LOW_TEMPERATURE')
    assert COLD_URL in app.openapi()['paths']
    assert cold['status'] == 'BASIC' and cold['thresholds'][0]['value'] == 0.0


@pytest.mark.parametrize(('values', 'outcome', 'minimum', 'qualified_offsets'), [
    ([0.1] * 24, 'NOT_REACHED', 0.1, []),
    ([4.0] * 23 + [0.0], 'REACHED', 0.0, [23]),
    ([0.0, -3.4] + [2.0] * 21 + [-0.2], 'REACHED', -3.4, [0, 1, 23]),
    ([4.0] * 22 + [-3.4, None], 'INSUFFICIENT', None, []),
])
def test_cold_uses_minimum_and_complete_window(basic, values, outcome, minimum, qualified_offsets):
    body = basic.HourlyTemperatureInput.model_validate(temperature_sample(hourly_temperature_c=values))
    result = basic.assess_cold(body)
    start = datetime(2024, 2, 28, 18, tzinfo=UTC)
    assert result.hazard_type == 'LOW_TEMPERATURE' and result.location == '课程示例点'
    assert (result.start_at, result.end_at) == (start, datetime(2024, 2, 29, 17, tzinfo=UTC))
    assert (result.threshold_c, result.extreme_c, result.outcome) == (0.0, minimum, outcome)
    assert result.qualifying_hours == [start + timedelta(hours=i) for i in qualified_offsets]
    assert result.usable_hours == sum(value is not None for value in values)


@pytest.mark.integration
def test_cold_trial_auth_requested_mode_and_shared_validation(new_client, login):
    body = temperature_sample(start_at='2024-02-28T18:00:00+00:00', hourly_temperature_c=[2.0] * 23 + [0.0])
    assert new_client().post(COLD_URL, json=body).status_code == 401
    client, token = login('viewer_demo')
    assert client.post(COLD_URL, json=body).status_code == 403
    headers = csrf_headers(token)
    result = client.post(COLD_URL, headers=headers, json=body)
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assessment = result.json()
    assert (assessment['hazard_type'], assessment['outcome'], assessment['extreme_c']) == ('LOW_TEMPERATURE', 'REACHED', 0.0)
    assert assessment['qualifying_hours'] == ['2024-02-29T17:00:00Z']
    assert client.post(COLD_URL, headers=headers, json=body | {'start_at': '2024-02-28T18:15:00Z'}).status_code == 422
    assert client.post(COLD_URL, headers=headers, json=body | {'hazard_type': 'HEATWAVE'}).status_code == 422


def wind_hail_sample(**overrides):
    return dict(location='课程示例点', start_at='2025-07-01T21:00:00Z',
                hourly_gust_mps=[8, 10, 13, 15, 16.9, 17.0], hourly_hail_signal=[False] * 6) | overrides


def test_wind_hail_endpoint_and_final_basic_hazard_registration():
    from backend.app.hazards import HAZARDS, hazard_summary
    from backend.app.main import app

    entry = next(item for item in HAZARDS if item['code'] == 'WIND_HAIL')
    assert WIND_HAIL_URL in app.openapi()['paths']
    assert entry['status'] == 'BASIC' and entry['thresholds'][0]['value'] == 17.0
    assert hazard_summary() == {'total': 8, 'implemented': 4, 'basic': 4, 'framework': 0}


@pytest.mark.parametrize(('gusts', 'signals', 'gust_outcome', 'hail_outcome', 'gust_i', 'hail_i'), [
    ([16.9] * 6, [False] * 6, 'NOT_REACHED', 'NOT_REACHED', [], []),
    ([0.0] * 5 + [17.0], [False] * 6, 'REACHED', 'NOT_REACHED', [5], []),
    ([20.0, 17.0] + [0.0] * 4, [True, False, False, True, False, False], 'REACHED', 'REACHED', [0, 1], [0, 3]),
    ([0.0] * 5 + [16.9], [False] * 5 + [True], 'NOT_REACHED', 'REACHED', [], [5]),
    ([None, 17.0] + [13.0] * 4, [False] * 5 + [True], 'INSUFFICIENT', 'REACHED', [], [5]),
    ([0.0] * 5 + [17.0], [True, None] + [False] * 4, 'REACHED', 'INSUFFICIENT', [5], []),
    ([None] * 6, [None] * 6, 'INSUFFICIENT', 'INSUFFICIENT', [], []),
])
def test_wind_hail_components_assess_known_and_missing_independently(basic, gusts, signals, gust_outcome, hail_outcome, gust_i, hail_i):
    data = wind_hail_sample(hourly_gust_mps=gusts, hourly_hail_signal=signals)
    result = basic.assess_wind_hail(basic.WindHailInput.model_validate(data))
    start = datetime(2025, 7, 1, 21, tzinfo=UTC)
    assert (result.hazard_type, result.start_at, result.end_at) == ('WIND_HAIL', start, datetime(2025, 7, 2, 2, tzinfo=UTC))
    assert (result.gust.outcome, result.hail.outcome, result.gust.threshold_mps) == (gust_outcome, hail_outcome, 17.0)
    assert result.gust.qualifying_hours == [start + timedelta(hours=i) for i in gust_i]
    assert result.hail.qualifying_hours == [start + timedelta(hours=i) for i in hail_i]
    assert result.gust.max_gust_mps == (None if None in gusts else max(gusts))
    assert result.gust.usable_hours == sum(value is not None for value in gusts)
    assert result.hail.usable_hours == sum(value is not None for value in signals)


@pytest.mark.parametrize(('field', 'invalid'), [
    ('start_at', '2025-07-01T21:00:00-05:00'), ('start_at', '9999-12-31T19:00:00Z'),
    ('hourly_gust_mps', [0] * 5), ('hourly_gust_mps', [0] * 5 + [-1]),
    ('hourly_gust_mps', [0] * 5 + [True]), ('hourly_gust_mps', [0] * 5 + [float('inf')]),
    ('hourly_hail_signal', [False] * 7), ('hourly_hail_signal', [False] * 5 + [0]),
    ('hourly_hail_signal', [False] * 5 + ['false']),
])
def test_wind_hail_rejects_bad_windows_gusts_and_non_boolean_signals(basic, field, invalid):
    with pytest.raises(ValidationError, match=field):
        basic.WindHailInput.model_validate(wind_hail_sample(**{field: invalid}))


@pytest.mark.integration
def test_wind_hail_trial_requires_auth_and_csrf_and_does_not_create_warning(new_client, login):
    body = wind_hail_sample(hourly_hail_signal=[False] * 5 + [None])
    assert new_client().post(WIND_HAIL_URL, json=body).status_code == 401
    client, token = login('viewer_demo')
    analyst, _ = login('analyst_demo')
    before = analyst.get('/api/v1/warnings').json()
    assert client.post(WIND_HAIL_URL, json=body).status_code == 403
    headers = csrf_headers(token)
    result = client.post(WIND_HAIL_URL, headers=headers, json=body)
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert result.json()['gust']['outcome'] == 'REACHED'
    assert result.json()['hail']['outcome'] == 'INSUFFICIENT'
    assert client.post(WIND_HAIL_URL, headers=headers, json=body | {'hourly_hail_signal': [0] * 6}).status_code == 422
    assert analyst.get('/api/v1/warnings').json() == before
