"""预警状态机全路径与非法跳转。

需要运行中的 MySQL/Redis/API，并以 RUN_INTEGRATION=1 且注入 DEMO_*_PASSWORD 执行。
测试创建的预警会在结束时清理。
"""

import os
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="requires running MySQL/Redis/API",
)

CREDENTIALS = {
    "viewer_demo": "DEMO_VIEWER_PASSWORD",
    "analyst_demo": "DEMO_ANALYST_PASSWORD",
    "reviewer_demo": "DEMO_REVIEWER_PASSWORD",
    "admin_demo": "DEMO_ADMIN_PASSWORD",
}


def _client_as(username):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    password = os.environ.get(CREDENTIALS[username])
    if not password:
        pytest.skip(f"{CREDENTIALS[username]} not set")

    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return client, resp.json()["csrf_token"]


def _create(client, csrf, prefix):
    resp = client.post(
        "/api/v1/warnings",
        headers={"X-CSRF-Token": csrf},
        json={
            "city_code": "CHANGSHA",
            "valid_date": "2024-03-27",
            "threshold_code": "HEAVY",
            "title": f"{prefix}-{uuid4().hex[:8]}",
            "area_text": "状态机测试",
            "reasoning_text": "状态机测试",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["public_id"]


def _cleanup(public_ids):
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal
    from backend.app.models import Warning, WarningFeedback, WarningResult, WarningReview

    with SessionLocal() as session:
        for public_id in public_ids:
            if not public_id:
                continue
            warning = session.scalar(select(Warning).where(Warning.public_id == public_id))
            if warning is None:
                continue
            result_id = warning.warning_result_id
            session.execute(delete(WarningFeedback).where(WarningFeedback.warning_id == warning.id))
            session.execute(delete(WarningReview).where(WarningReview.warning_id == warning.id))
            session.delete(warning)
            session.flush()
            if result_id is not None:
                session.execute(delete(WarningResult).where(WarningResult.id == result_id))
        session.commit()


def test_full_lifecycle_and_guards():
    analyst, analyst_csrf = _client_as("analyst_demo")
    reviewer, reviewer_csrf = _client_as("reviewer_demo")
    admin, admin_csrf = _client_as("admin_demo")
    viewer, _ = _client_as("viewer_demo")

    created = []
    try:
        public_id = _create(analyst, analyst_csrf, "state-full")
        created.append(public_id)

        submit = analyst.post(
            f"/api/v1/warnings/{public_id}/submit",
            headers={"X-CSRF-Token": analyst_csrf},
        )
        assert submit.status_code == 200, submit.text
        assert submit.json()["status"] == "PENDING_REVIEW"

        # 未批准不得发布
        early_publish = reviewer.post(
            f"/api/v1/warnings/{public_id}/publish",
            headers={"X-CSRF-Token": reviewer_csrf},
        )
        assert early_publish.status_code == 409

        # 管理员自建自审必须被拒绝
        admin_public_id = _create(admin, admin_csrf, "state-self-review")
        created.append(admin_public_id)
        admin_submit = admin.post(
            f"/api/v1/warnings/{admin_public_id}/submit",
            headers={"X-CSRF-Token": admin_csrf},
        )
        assert admin_submit.status_code == 200
        self_review = admin.post(
            f"/api/v1/warnings/{admin_public_id}/review",
            headers={"X-CSRF-Token": admin_csrf},
            json={"decision": "APPROVE", "comment": "self"},
        )
        assert self_review.status_code == 403
        assert self_review.json()["detail"] == "SELF_REVIEW_FORBIDDEN"

        approve = reviewer.post(
            f"/api/v1/warnings/{public_id}/review",
            headers={"X-CSRF-Token": reviewer_csrf},
            json={"decision": "APPROVE", "comment": "同意发布"},
        )
        assert approve.status_code == 200, approve.text

        publish = reviewer.post(
            f"/api/v1/warnings/{public_id}/publish",
            headers={"X-CSRF-Token": reviewer_csrf},
        )
        assert publish.status_code == 200, publish.text
        assert publish.json()["status"] == "PUBLISHED"

        # 发布后查看者可见
        assert viewer.get(f"/api/v1/warnings/{public_id}").status_code == 200

        feedback = analyst.post(
            f"/api/v1/warnings/{public_id}/feedback",
            headers={"X-CSRF-Token": analyst_csrf},
            json={"response_status": "RECEIVED", "content": "已通知相关单位"},
        )
        assert feedback.status_code == 200, feedback.text

        withdraw = reviewer.post(
            f"/api/v1/warnings/{public_id}/withdraw",
            headers={"X-CSRF-Token": reviewer_csrf},
        )
        assert withdraw.status_code == 200, withdraw.text
        assert withdraw.json()["status"] == "WITHDRAWN"

        # 撤回后查看者不可见，且不能重复撤回
        assert viewer.get(f"/api/v1/warnings/{public_id}").status_code == 404
        assert reviewer.post(
            f"/api/v1/warnings/{public_id}/withdraw",
            headers={"X-CSRF-Token": reviewer_csrf},
        ).status_code == 409
    finally:
        _cleanup(created)


def test_rejected_warning_can_be_resubmitted():
    analyst, analyst_csrf = _client_as("analyst_demo")
    reviewer, reviewer_csrf = _client_as("reviewer_demo")

    public_id = None
    try:
        public_id = _create(analyst, analyst_csrf, "state-reject")
        assert analyst.post(
            f"/api/v1/warnings/{public_id}/submit",
            headers={"X-CSRF-Token": analyst_csrf},
        ).status_code == 200

        reject = reviewer.post(
            f"/api/v1/warnings/{public_id}/review",
            headers={"X-CSRF-Token": reviewer_csrf},
            json={"decision": "REJECT", "comment": "依据不足"},
        )
        assert reject.status_code == 200, reject.text

        resubmit = analyst.post(
            f"/api/v1/warnings/{public_id}/submit",
            headers={"X-CSRF-Token": analyst_csrf},
        )
        assert resubmit.status_code == 200, resubmit.text
        assert resubmit.json()["status"] == "PENDING_REVIEW"
    finally:
        _cleanup([public_id])
