"""预警状态机全路径与非法跳转（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

测试创建的预警会在结束时清理。
"""

import pytest

from conftest import csrf_headers

import pytest
from sqlalchemy import select

from conftest import csrf_headers

pytestmark = pytest.mark.integration


def test_owner_can_cancel_draft_and_retains_trace_without_side_effects(login, make_warning):
    analyst, analyst_csrf = login("analyst_demo")
    admin, admin_csrf = login("admin_demo")
    public_id = make_warning(analyst, analyst_csrf, "state-cancel-draft")

    response = analyst.post(f"/api/v1/warnings/{public_id}/cancel", headers=csrf_headers(analyst_csrf))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"

    assert admin.post(
        f"/api/v1/warnings/{public_id}/cancel", headers=csrf_headers(admin_csrf)
    ).status_code == 403
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/cancel", headers=csrf_headers(analyst_csrf)
    ).status_code == 409
    assert analyst.patch(
        f"/api/v1/warnings/{public_id}",
        headers=csrf_headers(analyst_csrf),
        json={"title": "不能修改"},
    ).status_code == 403
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)
    ).status_code == 403
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/feedback",
        headers=csrf_headers(analyst_csrf),
        json={"response_status": "RECEIVED", "content": "不应成功"},
    ).status_code == 409

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, Notification, ResponseTask, Warning, WarningResult

    with SessionLocal() as db:
        warning = db.scalar(select(Warning).where(Warning.public_id == public_id))
        assert warning.status == "CANCELLED"
        assert warning.cancelled_at is not None
        assert warning.cancelled_by == analyst.get("/api/v1/auth/me").json()["user"]["id"]
        assert db.scalar(select(WarningResult).where(WarningResult.id == warning.warning_result_id)) is not None
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.resource_id == public_id, AuditLog.action == "WARNING_CANCEL"
            )
        )
        assert audit is not None
        assert audit.resource_version == 1
        assert audit.reason == "未提供原因"
        assert db.scalars(select(Notification).where(Notification.resource_id == public_id)).all() == []
        assert db.scalars(select(ResponseTask).where(ResponseTask.warning_id == warning.id)).all() == []


def test_owner_can_cancel_rejected_with_reason_and_viewer_cannot_read(login, make_warning):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, _ = login("viewer_demo")
    public_id = make_warning(analyst, analyst_csrf, "state-cancel-rejected")
    assert analyst.post(f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/review",
        headers=csrf_headers(reviewer_csrf),
        json={"decision": "REJECT", "comment": "需要补充"},
    ).status_code == 200

    response = analyst.post(
        f"/api/v1/warnings/{public_id}/cancel",
        headers=csrf_headers(analyst_csrf),
        json={"reason": "  暂不发布  "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"
    assert viewer.get(f"/api/v1/warnings/{public_id}").status_code == 404
    assert viewer.get(f"/api/v1/warnings/{public_id}/feedback").status_code == 404
    assert analyst.get("/api/v1/warnings?status=CANCELLED").json()[0]["status"] == "CANCELLED"

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog

    with SessionLocal() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.resource_id == public_id, AuditLog.action == "WARNING_CANCEL"
            )
        )
        assert audit.reason == "暂不发布"
        assert audit.resource_version == 1


def test_cancel_requires_auth_and_csrf(login, new_client, make_warning):
    client = new_client()
    assert client.post("/api/v1/warnings/missing/cancel").status_code == 401
    analyst, csrf = login("analyst_demo")
    public_id = make_warning(analyst, csrf, "state-cancel-csrf")
    assert analyst.post(f"/api/v1/warnings/{public_id}/cancel").status_code == 403


def test_publish_with_optional_reason_and_legacy_no_body_audit_version(login, make_warning):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    public_id = make_warning(analyst, analyst_csrf, "state-reason")
    assert analyst.post(f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/review",
        headers=csrf_headers(reviewer_csrf),
        json={"decision": "APPROVE", "comment": "审核通过"},
    ).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/publish",
        headers=csrf_headers(reviewer_csrf),
        json={"reason": "  正式发布  "},
    ).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/withdraw", headers=csrf_headers(reviewer_csrf)
    ).status_code == 200

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog

    with SessionLocal() as db:
        rows = db.scalars(
            select(AuditLog).where(
                AuditLog.resource_id == public_id,
                AuditLog.action.in_(["WARNING_REVIEW", "WARNING_PUBLISH", "WARNING_WITHDRAW"]),
            )
        ).all()
        by_action = {row.action: row for row in rows}
        assert by_action["WARNING_REVIEW"].reason == "审核通过"
        assert by_action["WARNING_REVIEW"].resource_version == 1
        assert by_action["WARNING_PUBLISH"].reason == "正式发布"
        assert by_action["WARNING_PUBLISH"].resource_version == 1
        assert by_action["WARNING_WITHDRAW"].reason == "未提供原因"
        assert by_action["WARNING_WITHDRAW"].resource_version == 1


def test_full_lifecycle_and_guards(login, make_warning):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, admin_csrf = login("admin_demo")
    viewer, _ = login("viewer_demo")

    public_id = make_warning(analyst, analyst_csrf, "state-full")

    submit = analyst.post(f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf))
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == "PENDING_REVIEW"

    # 未批准不得发布
    early_publish = reviewer.post(f"/api/v1/warnings/{public_id}/publish", headers=csrf_headers(reviewer_csrf))
    assert early_publish.status_code == 409

    # 管理员自建自审必须被拒绝
    admin_public_id = make_warning(admin, admin_csrf, "state-self-review")
    admin_submit = admin.post(f"/api/v1/warnings/{admin_public_id}/submit", headers=csrf_headers(admin_csrf))
    assert admin_submit.status_code == 200
    self_review = admin.post(
        f"/api/v1/warnings/{admin_public_id}/review",
        headers=csrf_headers(admin_csrf),
        json={"decision": "APPROVE", "comment": "self"},
    )
    assert self_review.status_code == 403
    assert self_review.json()["error"]["code"] == "SELF_REVIEW_FORBIDDEN"

    approve = reviewer.post(
        f"/api/v1/warnings/{public_id}/review",
        headers=csrf_headers(reviewer_csrf),
        json={"decision": "APPROVE", "comment": "同意发布"},
    )
    assert approve.status_code == 200, approve.text

    publish = reviewer.post(f"/api/v1/warnings/{public_id}/publish", headers=csrf_headers(reviewer_csrf))
    assert publish.status_code == 200, publish.text
    assert publish.json()["status"] == "PUBLISHED"

    # 发布后查看者可见
    assert viewer.get(f"/api/v1/warnings/{public_id}").status_code == 200

    feedback = analyst.post(
        f"/api/v1/warnings/{public_id}/feedback",
        headers=csrf_headers(analyst_csrf),
        json={"response_status": "RECEIVED", "content": "已通知相关单位"},
    )
    assert feedback.status_code == 200, feedback.text

    withdraw = reviewer.post(f"/api/v1/warnings/{public_id}/withdraw", headers=csrf_headers(reviewer_csrf))
    assert withdraw.status_code == 200, withdraw.text
    assert withdraw.json()["status"] == "WITHDRAWN"

    # 撤回后查看者不可见，且不能重复撤回
    assert viewer.get(f"/api/v1/warnings/{public_id}").status_code == 404
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/withdraw", headers=csrf_headers(reviewer_csrf)
    ).status_code == 409


def test_rejected_warning_can_be_resubmitted(login, make_warning):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")

    public_id = make_warning(analyst, analyst_csrf, "state-reject")
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)
    ).status_code == 200

    reject = reviewer.post(
        f"/api/v1/warnings/{public_id}/review",
        headers=csrf_headers(reviewer_csrf),
        json={"decision": "REJECT", "comment": "依据不足"},
    )
    assert reject.status_code == 200, reject.text

    resubmit = analyst.post(f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf))
    assert resubmit.status_code == 200, resubmit.text
    assert resubmit.json()["status"] == "PENDING_REVIEW"
