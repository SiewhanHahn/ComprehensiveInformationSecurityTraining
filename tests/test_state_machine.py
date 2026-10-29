"""预警状态机全路径与非法跳转（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

测试创建的预警会在结束时清理。
"""

import pytest

from conftest import csrf_headers

pytestmark = pytest.mark.integration


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
