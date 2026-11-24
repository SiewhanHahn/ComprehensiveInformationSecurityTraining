"""Typhoon case replay and the shared formal warning lifecycle."""
from datetime import datetime, timedelta, timezone
from importlib import import_module
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.assessment_schemas import TrackPoint
from backend.app.schemas import TyphoonWarningCreate
from backend.app.services import typhoon
from conftest import csrf_headers, notifications_for, review_body

CASE = 'hato-20170822'
ASSESSMENT = f'/api/v1/typhoon/cases/{CASE}/assessment'
CREATE = '/api/v1/warnings/typhoon'


@pytest.mark.parametrize(('city', 'distance', 'outcome'), [
    ('GUANGZHOU', 144.3, 'NEAR'), ('HONGKONG', 213.0, 'NOT_NEAR'), ('SHANGHAI', 1351.3, 'NOT_NEAR'),
])
def test_hato_archived_forecast_and_same_time_reference(city, distance, outcome):
    replay = typhoon.replay(CASE, city)
    forecast, verification = replay.forecast, replay.verification
    assert forecast.outcome == outcome and forecast.metric.value == distance
    assert (forecast.metric.unit, forecast.metric.threshold, forecast.metric.comparison) == ('km', 200, '<=')
    assert forecast.case.issued_at == datetime(2017, 8, 22, 10, 30, tzinfo=timezone.utc)
    assert forecast.closest_point.valid_at - forecast.case.issued_at == timedelta(hours=22, minutes=30)
    assert (forecast.closest_point.latitude, forecast.closest_point.longitude) == (22.4, 112.1)
    assert verification.point.valid_at == forecast.closest_point.valid_at
    assert (verification.point.latitude, verification.point.longitude) == (22.4, 112.0)
    assert 10.2 < verification.position_error_km < 10.4


def test_forecast_window_and_missing_times_never_borrow_reference():
    case = typhoon.get_case(CASE)
    city = typhoon.get_city('GUANGZHOU')
    issue = case.info.issued_at
    rejected_times = [issue - timedelta(minutes=1), issue, issue + timedelta(hours=24, seconds=1)]
    excluded = tuple(TrackPoint(latitude=city.latitude, longitude=city.longitude, valid_at=t) for t in rejected_times)
    missing = typhoon.assess_forecast(case.info, excluded, city)
    assert missing.outcome == 'INSUFFICIENT' and missing.metric is None and missing.closest_point is None
    assert typhoon.verify_assessment(missing, case) is None
    boundary = TrackPoint(latitude=city.latitude, longitude=city.longitude, valid_at=issue + timedelta(hours=24))
    result = typhoon.assess_forecast(case.info, excluded + (boundary,), city)
    assert result.outcome == 'NEAR' and result.metric.value == 0 and result.closest_point == boundary
    assert typhoon.verify_assessment(result, case) is None


def test_window_distance_ties_pick_earliest_time_and_threshold_is_inclusive(monkeypatch):
    case = typhoon.get_case(CASE)
    city = typhoon.get_city('GUANGZHOU')
    early = TrackPoint(latitude=22, longitude=112, valid_at=case.info.issued_at + timedelta(hours=3))
    late = early.model_copy(update={'valid_at': early.valid_at + timedelta(hours=1)})
    monkeypatch.setattr(typhoon, 'great_circle_km', lambda *_: 200.0)
    result = typhoon.assess_forecast(case.info, (late, early), city)
    assert result.outcome == 'NEAR' and result.closest_point == early


@pytest.mark.parametrize('lat,lon', [(90.01, 0), (0, -180.01), (float('nan'), 0)])
def test_case_coordinates_are_bounded(lat, lon):
    with pytest.raises(ValidationError):
        TrackPoint(latitude=lat, longitude=lon, valid_at='2017-08-23T09:00:00Z')


def draft(city='GUANGZHOU'):
    return dict(case_id=CASE, city_code=city, title=f'天鸽教学演练 {uuid4().hex[:8]}', area_text='广州代表点',
                impact_text='台风中心接近风险，不代表当地风雨和损失', reasoning_text='回放航运公报的离散预报点')


def test_draft_schema_cannot_accept_client_computed_risk_or_distance():
    with pytest.raises(ValidationError):
        TyphoonWarningCreate(**draft(), distance_km=1, risk_level='YELLOW')


def test_downgrade_with_assessments_does_not_start_ddl(monkeypatch):
    migration = import_module('backend.migrations.versions.0008_hazard_assessment')
    ops = Mock(); ops.get_bind.return_value.scalar.return_value = 1
    monkeypatch.setattr(migration, 'op', ops)
    with pytest.raises(RuntimeError, match='0008'):
        migration.downgrade()
    ops.alter_column.assert_not_called()
    ops.drop_column.assert_not_called()


@pytest.mark.integration
def test_typhoon_untrusted_or_far_case_is_not_a_draft(new_client, login):
    assert new_client().get(ASSESSMENT, params={'city_code': 'GUANGZHOU'}).status_code == 401
    analyst, token = login('analyst_demo')
    viewer, viewer_token = login('viewer_demo')
    assert viewer.get('/api/v1/typhoon/cases').json()['cases'][0]['case_id'] == CASE
    assert viewer.post(CREATE, json=draft(), headers=csrf_headers(viewer_token)).status_code == 403
    assert analyst.post(CREATE, json=draft()).status_code == 403
    assert analyst.post(CREATE, json=draft() | {'distance_km': 1}, headers=csrf_headers(token)).status_code == 422
    assert analyst.get(ASSESSMENT, params={'city_code': 'BEIJING'}).status_code == 422
    assert analyst.get('/api/v1/typhoon/cases/not-a-case/assessment', params={'city_code': 'GUANGZHOU'}).status_code == 404
    far = analyst.get(ASSESSMENT, params={'city_code': 'SHANGHAI'}).json()
    assert far['forecast']['outcome'] == 'NOT_NEAR'
    refused = analyst.post(CREATE, json=draft('SHANGHAI'), headers=csrf_headers(token))
    assert refused.status_code == 409 and refused.json()['error']['code'] == 'THRESHOLD_NOT_REACHED'


@pytest.mark.integration
def test_typhoon_publish_uses_existing_lifecycle_without_fake_rain(login, created_warnings, subscriber, created_subscriptions):
    from sqlalchemy import select
    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, Warning

    analyst, a = login('analyst_demo')
    reviewer, r = login('reviewer_demo')
    viewer, v = subscriber
    sub = viewer.post('/api/v1/subscriptions', json={'hazard_type': 'TYPHOON', 'city_code': 'GUANGZHOU'}, headers=csrf_headers(v))
    assert sub.status_code == 200, sub.text
    created_subscriptions.append(sub.json()['id'])
    response = analyst.post(CREATE, json=draft(), headers=csrf_headers(a))
    assert response.status_code == 200, response.text
    saved = response.json()
    ident = saved['public_id']
    created_warnings.append(ident)
    assert (saved['hazard_type'], saved['status'], saved['fused_mm']) == ('TYPHOON', 'DRAFT', None)
    assert saved['metric']['value'] == 144.3 and saved['metric']['unit'] == 'km'
    path = f'/api/v1/warnings/{ident}'
    assert viewer.get(path).status_code == 404
    assert notifications_for(viewer, ident) == []
    assert analyst.get('/api/v1/response-tasks', params={'warning': ident}).json() == []
    evidence = analyst.get(path).json()['typhoon_assessment']
    assert 'verification' not in evidence and evidence['closest_point']['longitude'] == 112.1
    assert analyst.post(path + '/submit', headers=csrf_headers(a)).status_code == 200
    assert reviewer.post(path + '/publish', headers=csrf_headers(r)).status_code == 409
    review = reviewer.post(path + '/review', json=review_body(reviewer, ident, 'APPROVE', '核对签发资料'), headers=csrf_headers(r))
    assert review.status_code == 200, review.text
    assert reviewer.post(path + '/publish', json={'reason': '教学演练'}, headers=csrf_headers(r)).json()['status'] == 'PUBLISHED'
    visible = viewer.get(path).json()
    assert visible['typhoon_assessment'] == evidence and visible['models'] == [] and visible['proxy_label_mm'] is None
    published = notifications_for(viewer, ident)
    assert len(published) == 1 and '144.3 km' in published[0]['body'] and '四模式融合' not in published[0]['body']
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
        audited = db.scalars(select(AuditLog).where(AuditLog.resource_id == ident, AuditLog.action.in_(['WARNING_PUBLISH', 'WARNING_WITHDRAW']))).all()
        assert {row.action: (row.reason, row.resource_version) for row in audited} == {
            'WARNING_PUBLISH': ('教学演练', 1), 'WARNING_WITHDRAW': ('演练结束', 1),
        }
