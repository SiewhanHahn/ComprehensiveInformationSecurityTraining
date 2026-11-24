"""B candidate contracts: required impact, editable historical drafts and audit revisions."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.schemas import WarningCreate, WarningUpdate
from backend.app.services import warnings

BASE = dict(city_code="CHANGSHA", valid_date="2024-03-27", threshold_code="HEAVY", title="演练",
            area_text="城区", reasoning_text="四模式均值达到阈值")


@pytest.mark.parametrize("overrides", [{}, {"impact_text": None}, {"impact_text": "  "}])
def test_create_requires_meaningful_impact(overrides):
    with pytest.raises(ValidationError):
        WarningCreate(**BASE, **overrides)


@pytest.mark.parametrize("text", [None, " "])
def test_patch_cannot_erase_impact(text):
    with pytest.raises(ValidationError):
        WarningUpdate(impact_text=text)
    assert WarningUpdate().model_dump(exclude_unset=True) == {}


def test_legacy_draft_requires_repair_before_submit(monkeypatch):
    w = SimpleNamespace(status="DRAFT", created_by=1, impact_text=None, version_no=1, public_id="old-draft")
    monkeypatch.setattr(warnings, "get_warning", lambda *a, **kw: w)
    audit, db = Mock(), Mock()
    with pytest.raises(HTTPException) as err:
        warnings.submit_warning(db, w.public_id, SimpleNamespace(id=1), audit)
    assert err.value.detail == "IMPACT_REQUIRED" and w.status == "DRAFT"
    audit.record.assert_not_called()


def test_revision_only_changes_when_content_changes(monkeypatch):
    w = SimpleNamespace(status="REJECTED", created_by=1, impact_text="历史", version_no=2, public_id="draft")
    monkeypatch.setattr(warnings, "get_warning", lambda *a, **kw: w)
    audit, db, actor = Mock(), Mock(), SimpleNamespace(id=1)
    warnings.update_warning(db, w.public_id, WarningUpdate(impact_text=" 历史 "), actor, audit)
    audit.record.assert_not_called()
    db.flush.assert_not_called()
    warnings.update_warning(db, w.public_id, WarningUpdate(impact_text=" 新说明 "), actor, audit)
    assert (w.version_no, w.impact_text) == (3, "新说明")
    assert audit.record.call_args.kwargs['resource_version'] == 3


def test_duplicate_city_days_keep_first_usable_value_per_source():
    from backend.app.cities import DEFAULT_MODELS
    from backend.app.services.ingest import _validate_days
    day = dict(city_code='WUHAN', valid_date='2024-03-27')
    staged = _validate_days([{**day, 'models': {}, 'proxy_label_mm': 2},
                             {**day, 'models': dict.fromkeys(DEFAULT_MODELS, 4), 'proxy_label_mm': 9}])
    assert len(staged['fc_rows']) == 4
    assert [r[-1] for r in staged['obs_rows']] == [2]
    assert 'DUPLICATE' in {i[1] for i in staged['issues']}


def test_missing_proxy_explains_observation_quality():
    from backend.app.cities import DEFAULT_MODELS
    from backend.app.services.ingest import _validate_days
    staged = _validate_days([dict(city_code='WUHAN', valid_date='2024-03-27', models=dict.fromkeys(DEFAULT_MODELS, 4))])
    assert staged['obs_has_issue'] and not staged['fc_has_issue']
    assert any(i[0] and i[1] == 'MISSING_PROXY' for i in staged['issues'])


def test_unrecognized_warning_parameters_are_not_missing_resources(monkeypatch):
    monkeypatch.setattr(warnings, 'compute_replay', lambda *args: None)
    with pytest.raises(HTTPException) as err:
        warnings.create_warning(Mock(), WarningCreate(**BASE, impact_text='道路'), Mock(), Mock())
    assert err.value.status_code == 422


def test_request_id_is_new_for_each_request():
    from fastapi.testclient import TestClient
    from backend.app.main import app
    with TestClient(app) as client:
        headers = {'X-Request-ID': 'same-client-correlation'}
        a = client.get('/health', headers=headers).headers['x-request-id']
        b = client.get('/health', headers=headers).headers['x-request-id']
    assert len({a, b, headers['X-Request-ID']}) == 3


def test_rate_limit_logs_bounded_summary_without_credentials(monkeypatch, caplog):
    from backend.app.routers import auth
    times = iter((100.0, 110.0, 170.0))
    monkeypatch.setattr(auth, '_last_limit_log', None)
    monkeypatch.setattr(auth, 'monotonic', lambda: next(times))
    for _ in range(3):
        auth._log_rate_limit()
    assert [r.getMessage() for r in caplog.records if r.name == auth.__name__] == ['Login rate limit reached'] * 2


def test_downgrade_refuses_to_discard_lifecycle_history(monkeypatch):
    from importlib import import_module
    migration = import_module('backend.migrations.versions.0007_warning_lifecycle_audit')
    db = Mock(); db.scalar.return_value = 1
    ops = Mock(); ops.get_bind.return_value = db
    monkeypatch.setattr(migration, 'op', ops)
    with pytest.raises(RuntimeError, match='0007'):
        migration.downgrade()
    ops.drop_column.assert_not_called()
    ops.drop_constraint.assert_not_called()


@pytest.mark.parametrize('changed', [True, False])
def test_review_is_bound_to_one_displayed_submission(changed, monkeypatch):
    from datetime import datetime, timedelta
    from backend.app.deps import CurrentUser
    author = CurrentUser(1, 'author', ['ANALYST']); reviewer = CurrentUser(2, 'reviewer', ['REVIEWER'])
    first = datetime(2026, 1, 1)
    w = SimpleNamespace(id=3, status=warnings.PENDING_REVIEW, version_no=1, submitted_at=first,
                        public_id='draft', created_by=1, impact_text='通勤')
    monkeypatch.setattr(warnings, 'get_warning', lambda *a, **kw: w)
    # A frozen clock must not make two different submission rounds indistinguishable.
    monkeypatch.setattr(warnings, 'utcnow', lambda: first)
    db, audit = Mock(), Mock()
    previous = warnings.review_token(w)
    warnings.review_warning(db, 'draft', 'REJECT', '请复核区域', reviewer, audit, previous)
    if changed:
        warnings.update_warning(db, 'draft', WarningUpdate(impact_text='道路交通'), author, audit)
    warnings.submit_warning(db, 'draft', author, audit)
    current = warnings.review_token(w)
    assert current != previous and w.submitted_at >= first + timedelta(microseconds=1)
    for unavailable in [previous, None]:
        audit.reset_mock()
        with pytest.raises(HTTPException) as err:
            warnings.review_warning(db, 'draft', 'APPROVE', '', reviewer, audit, unavailable)
        assert (err.value.status_code, err.value.detail) == (409, 'REVIEW_CHANGED')
        assert w.status == warnings.PENDING_REVIEW
        audit.record.assert_not_called()
    warnings.review_warning(db, 'draft', 'APPROVE', '', reviewer, audit, current)
    assert w.status == warnings.APPROVED
