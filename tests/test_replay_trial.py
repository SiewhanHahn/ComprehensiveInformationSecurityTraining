from copy import deepcopy
from decimal import Decimal

import pytest

from backend.app.services.trial import TrialError, calculate_trial

MODELS = ['ecmwf_ifs025', 'gfs_global', 'icon_global', 'gem_global']
BASE = {'schema_version': 1, 'lead_hours': 24, 'rows': [
    {'city': '南京', 'valid_date': '2026-10-01', 'models': dict(zip(MODELS, [20, 30, 10, 40]))}
]}


def test_new_city_at_threshold_and_reference_independence():
    data = deepcopy(BASE)
    row = calculate_trial(data, Decimal('25'))[0]
    assert (row['fused_mm'], row['fusion_hit'], row['baseline_hit']) == (25, True, False)
    assert row['reference_hit'] is None
    data['rows'][0].update(reference_type='ERA5_PROXY', reference_mm=0)
    with_reference = calculate_trial(data, Decimal('25'))[0]
    assert with_reference['fused_mm'] == row['fused_mm'] and not with_reference['reference_hit']


@pytest.mark.parametrize('values, mean, hit', [([24.999, 24.999, 25, 25], 25.000, True),
                                              ([24.998, 24.998, 24.999, 24.999], 24.999, False)])
def test_trial_threshold_compares_displayed_half_up_value(values, mean, hit):
    data = deepcopy(BASE)
    data['rows'][0]['models'] = dict(zip(MODELS, values))
    row = calculate_trial(data, Decimal('25'))[0]
    assert row['fused_mm'] == mean and row['fusion_hit'] is hit


@pytest.mark.parametrize('change,location', [
    (lambda d: d.update(lead_hours=0), 'lead_hours'),
    (lambda d: d.update(schema_version=True), 'schema_version'),
    (lambda d: d['rows'][0].update(reference_mmm=5), '未知字段'),
    (lambda d: d['rows'][0].update(city='\ud800'), 'city'),
    (lambda d: d['rows'].append(deepcopy(d['rows'][0])), '第 2 行'),
    (lambda d: d['rows'][0].update(valid_date='2026-02-30'), 'valid_date'),
    (lambda d: d['rows'][0].update(reference_mm=10), 'reference_type'),
    (lambda d: d['rows'][0]['models'].pop('gem_global'), 'gem_global'),
    (lambda d: d['rows'][0]['models'].update(gem_global='10'), 'gem_global'),
    (lambda d: d['rows'][0]['models'].update(gem_global=-1), 'gem_global'),
    (lambda d: d['rows'][0]['models'].update(gem_global=float('nan')), 'gem_global'),
    (lambda d: d.update(rows=d['rows'] * 201), 'rows'),
])
def test_invalid_dataset(change, location):
    data = deepcopy(BASE)
    change(data)
    with pytest.raises(TrialError, match=location):
        calculate_trial(data, Decimal('25'))


def test_hourly_totals_reject_missing_or_misaligned_source():
    from datetime import timedelta
    from backend.make_nanjing_trial import START, totals

    payload = {'utc_offset_seconds': 0, 'hourly_units': {'rain': 'mm'}, 'hourly': {
        'time': [f'{START + timedelta(days=i // 24)}T{i % 24:02}:00' for i in range(168)], 'rain': [1] * 168}}
    assert totals(payload, 'rain') == [24] * 7
    for field, value in [('time', 'unexpected hour'), ('rain', None)]:
        broken = deepcopy(payload)
        broken['hourly'][field][12] = value
        with pytest.raises(ValueError):
            totals(broken, 'rain')


@pytest.mark.integration
def test_trial_endpoint_permissions_and_isolation(new_client, login):
    from sqlalchemy import func, select
    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, Dataset, ForecastRecord, ObservationRecord, Warning
    from backend.app.services.metrics import get_experiment

    url = '/api/v1/replay/trial?threshold_code=HEAVY'
    assert new_client().post(url, json=BASE).status_code == 401
    for name in ['viewer_demo', 'reviewer_demo']:
        client, csrf = login(name)
        assert client.post(url, json=BASE, headers={'X-CSRF-Token': csrf}).status_code == 403
    client, csrf = login('analyst_demo')
    def snapshot():
        with SessionLocal() as db:
            return ([db.scalar(select(func.count()).select_from(model)) for model in
                     [Dataset, ForecastRecord, ObservationRecord, Warning]], get_experiment('10mm').model_dump())
    before = snapshot()
    assert client.post(url, json=BASE).status_code == 403
    headers = {'X-CSRF-Token': csrf}
    invalid = deepcopy(BASE)
    del invalid['rows'][0]['models']['gem_global']
    bad = client.post(url, json=invalid, headers=headers)
    assert bad.status_code == 422 and '第 1 行 models.gem_global' in bad.json()['error']['message']
    assert client.post(url, content=b'{', headers=headers).status_code == 422
    assert client.post(url, content=b' ' * (256 * 1024 + 1), headers=headers).status_code == 413
    for name in ['analyst_demo', 'admin_demo']:
        if name == 'admin_demo':
            client, csrf = login(name)
        resp = client.post(url, json=BASE, headers={'X-CSRF-Token': csrf})
        assert resp.status_code == 200, resp.text
        assert resp.headers['cache-control'] == 'no-store'
        assert resp.json()['rows'][0]['fusion_hit'] is True
        with SessionLocal() as db:
            record = db.scalars(select(AuditLog).where(AuditLog.request_id == resp.headers['x-request-id'],
                                                       AuditLog.action == 'REPLAY_TRIAL')).one()
            assert record.reason == 'threshold=HEAVY; rows=1' and record.actor_id
    assert snapshot() == before


@pytest.mark.integration
def test_trial_leaves_existing_pending_review_unchanged(login, make_warning):
    """C1 is a calculation, not a warning revision or another submission round."""
    from conftest import csrf_headers, review_body

    analyst, a = login('analyst_demo')
    reviewer, r = login('reviewer_demo')
    ident = make_warning(analyst, a, 'rain-integration')
    url = f'/api/v1/warnings/{ident}'
    assert analyst.post(url + '/submit', headers=csrf_headers(a)).status_code == 200
    reviewed = review_body(reviewer, ident, 'APPROVE', '独立审阅原草稿')
    before = reviewer.get(url).json()
    trial = analyst.post('/api/v1/replay/trial?threshold_code=HEAVY', json=BASE, headers=csrf_headers(a))
    assert trial.status_code == 200 and trial.json()['rows'][0]['fusion_hit']
    after = reviewer.get(url).json()
    for field in ['public_id', 'status', 'version_no', 'submitted_at', 'review_token', 'fused_mm']:
        assert before[field] == after[field], field
    assert reviewer.post(url + '/review', json=reviewed, headers=csrf_headers(r)).status_code == 200
