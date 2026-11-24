from datetime import date
from importlib import import_module

import pytest
from pydantic import ValidationError

from conftest import csrf_headers

DROUGHT_URL = '/api/v1/basic-forecast/drought/assessment'


@pytest.fixture
def basic():
    return import_module('backend.app.services.basic_forecast')


def sample(**overrides):
    return dict(location='课程示例点', start_date='2025-07-01', antecedent_dry_days=9,
                daily_rain_mm=[0.0, 0.2, 0.0, 0.3, 0.0, 0.8, 0.0]) | overrides


def test_drought_endpoint_and_basic_hazard_registration():
    from backend.app.hazards import HAZARDS, hazard_summary
    from backend.app.main import app

    drought = next(item for item in HAZARDS if item['code'] == 'DROUGHT')
    assert drought['status'] == 'BASIC' and DROUGHT_URL in app.openapi()['paths']
    assert hazard_summary() == {'total': 8, 'implemented': 4, 'basic': 1, 'framework': 3}


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
