"""定时扫描：投递补偿的幂等性与 SYSTEM 审计（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

``run_scan`` 是纯函数，直接传入时间窗口调用，不需要 sleep 或后台线程。
订阅者用临时账号，不依赖演示账号的历史订阅。
"""

import pytest
from sqlalchemy import select

from conftest import csrf_headers

pytestmark = pytest.mark.integration


def _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, prefix) -> str:
    public_id = make_warning(analyst, analyst_csrf, prefix)
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)
    ).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/review",
        headers=csrf_headers(reviewer_csrf),
        json={"decision": "APPROVE", "comment": "同意发布"},
    ).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/publish", headers=csrf_headers(reviewer_csrf)
    ).status_code == 200
    return public_id


def _notifications_for(client, public_id) -> list[dict]:
    resp = client.get("/api/v1/notifications", params={"page_size": 100})
    assert resp.status_code == 200, resp.text
    return [n for n in resp.json()["items"] if n["resource_id"] == public_id]


def test_backfill_scan_is_idempotent(login, subscriber, make_warning, created_subscriptions):
    """先发布、后订阅：扫描补投一条，再跑一次不重复，且留下 SYSTEM 审计。"""
    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    public_id = _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "scan-backfill")
    # 订阅发生在发布之后，所以此刻还没收到
    assert _notifications_for(viewer, public_id) == []

    resp = viewer.post(
        "/api/v1/subscriptions", headers=csrf_headers(viewer_csrf), json={"hazard_type": "*", "city_code": ""}
    )
    assert resp.status_code == 200, resp.text
    created_subscriptions.append(resp.json()["id"])

    with SessionLocal() as db:
        first = run_scan(db, hours=1)
        db.commit()
    assert first.backfilled >= 1
    assert len(_notifications_for(viewer, public_id)) == 1

    with SessionLocal() as db:
        second = run_scan(db, hours=1)
        db.commit()
    assert second.backfilled == 0
    assert len(_notifications_for(viewer, public_id)) == 1

    with SessionLocal() as db:
        row = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "NOTIFICATION_BACKFILL")
            .order_by(AuditLog.id.desc())
        )
    assert row is not None
    assert row.actor_id is None
    assert row.actor_role == "SYSTEM"
    assert row.resource_type == "notification"
