"""定时扫描：投递补偿的幂等性与 SYSTEM 审计（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

``run_scan`` 是纯函数，直接传入时间窗口调用，不需要 sleep 或后台线程。
订阅者用临时账号，不依赖演示账号的历史订阅。
"""

import pytest
from sqlalchemy import func, select

from conftest import csrf_headers, notifications_for, publish_warning

pytestmark = pytest.mark.integration


def test_backfill_scan_is_idempotent(login, subscriber, make_warning, created_subscriptions):
    """先发布、后订阅：扫描补投一条，再跑一次不重复，且留下 SYSTEM 审计。"""
    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "scan-backfill")
    # 订阅发生在发布之后，所以此刻还没收到
    assert notifications_for(viewer, public_id) == []

    resp = viewer.post(
        "/api/v1/subscriptions", headers=csrf_headers(viewer_csrf), json={"hazard_type": "*", "city_code": ""}
    )
    assert resp.status_code == 200, resp.text
    created_subscriptions.append(resp.json()["id"])

    with SessionLocal() as db:
        before_audit_id = db.scalar(select(func.max(AuditLog.id))) or 0
        first = run_scan(db, hours=1)
        db.commit()
    assert first.backfilled >= 1
    assert len(notifications_for(viewer, public_id)) == 1

    with SessionLocal() as db:
        second = run_scan(db, hours=1)
        db.commit()
    assert second.backfilled == 0
    assert len(notifications_for(viewer, public_id)) == 1

    with SessionLocal() as db:
        # 只看本次扫描之后新增的审计行；历史行不清理，用「最新一行」会掩盖审计被删掉的回归
        row = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "NOTIFICATION_BACKFILL", AuditLog.id > before_audit_id)
            .order_by(AuditLog.id.desc())
        )
    assert row is not None
    assert row.actor_id is None
    assert row.actor_role == "SYSTEM"
    assert row.resource_type == "notification"


def test_a_failing_pass_does_not_revert_the_other(
    login, subscriber, make_warning, created_subscriptions, monkeypatch
):
    """第二趟抛错不能把第一趟已经补投的通知一起回滚。

    两趟共用一次 commit 时，只要超时升级这一趟失败，订阅者就永远收不到补投，
    而且每 5 分钟重跑一次、每次都失败。
    """
    from backend.app import scheduler
    from backend.app.db import SessionLocal
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "scan-isolation")
    resp = viewer.post(
        "/api/v1/subscriptions", headers=csrf_headers(viewer_csrf), json={"hazard_type": "*", "city_code": ""}
    )
    assert resp.status_code == 200, resp.text
    created_subscriptions.append(resp.json()["id"])

    def boom(db, *, now):  # 模拟第二趟遇到一条毒数据
        raise RuntimeError("synthetic escalation failure")

    monkeypatch.setattr(scheduler, "escalate_overdue", boom)

    with SessionLocal() as db:
        result = run_scan(db, hours=1)

    assert "escalate" in result.failed
    assert result.backfilled >= 1
    # 第一趟的结果必须已经落库
    assert len(notifications_for(viewer, public_id)) == 1
