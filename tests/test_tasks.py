"""响应任务：发布自动派发、接单与完成、超时升级（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

任务随预警创建，由 ``created_warnings`` 夹具一并清理；升级扫描直接调用
``run_scan(db, now=...)``，不依赖后台线程或 sleep。
"""

from datetime import datetime, timedelta

import pytest

from conftest import csrf_headers, publish_warning

pytestmark = pytest.mark.integration


def _tasks(client, public_id) -> list[dict]:
    resp = client.get("/api/v1/response-tasks", params={"warning": public_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _expire_task(task_id: int) -> None:
    """把时限改到过去，模拟「已经过了处置时限」。"""
    from backend.app.db import SessionLocal
    from backend.app.models import ResponseTask
    from backend.app.clock import utcnow

    with SessionLocal() as db:
        task = db.get(ResponseTask, task_id)
        task.due_at = utcnow() - timedelta(minutes=5)
        db.commit()


def test_publish_creates_task_for_creator(login, make_warning):
    from backend.app.config import get_settings

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-create")

    tasks = _tasks(admin, public_id)
    assert len(tasks) == 1, tasks
    task = tasks[0]
    assert task["assignee"] == "analyst_demo"
    assert task["status"] == "PENDING"
    assert task["overdue"] is False
    assert task["escalation_level"] == 0
    # 时限 = 任务创建时刻 + 配置的处置时长
    expected = timedelta(minutes=get_settings().response_task_due_minutes)
    actual = datetime.fromisoformat(task["due_at"]) - datetime.fromisoformat(task["created_at"])
    assert abs(actual - expected) < timedelta(minutes=1), actual


def test_assignee_receives_task_notification(login, make_warning):
    from conftest import notifications_for

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-notify")
    task = _tasks(analyst, public_id)[0]

    items = notifications_for(analyst, task["id"])
    assert len(items) == 1, items
    assert items[0]["kind"] == "TASK_ASSIGNED"
    assert items[0]["resource_type"] == "response_task"


def test_only_assignee_or_admin_can_advance(login, make_warning):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, admin_csrf = login("admin_demo")
    viewer, _ = login("viewer_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-scope")
    task_id = _tasks(admin, public_id)[0]["id"]

    # 查看者整体被角色拦掉
    assert viewer.get("/api/v1/response-tasks").status_code == 403

    # 其他业务角色看不到、也推不动别人的任务
    assert _tasks(reviewer, public_id) == []
    denied = reviewer.post(f"/api/v1/response-tasks/{task_id}/ack", headers=csrf_headers(reviewer_csrf))
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "NOT_FOUND"

    # 管理员可以代为接单
    assert admin.post(
        f"/api/v1/response-tasks/{task_id}/ack", headers=csrf_headers(admin_csrf)
    ).status_code == 200


def test_task_state_machine(login, make_warning):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-state")
    task_id = _tasks(analyst, public_id)[0]["id"]

    # 没接单不能直接完成
    early = analyst.post(
        f"/api/v1/response-tasks/{task_id}/complete",
        headers=csrf_headers(analyst_csrf),
        json={"note": "跳过接单"},
    )
    assert early.status_code == 409
    assert early.json()["error"]["code"] == "INVALID_STATE"

    ack = analyst.post(f"/api/v1/response-tasks/{task_id}/ack", headers=csrf_headers(analyst_csrf))
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == "ACKED"
    assert ack.json()["acked_at"] is not None

    again = analyst.post(f"/api/v1/response-tasks/{task_id}/ack", headers=csrf_headers(analyst_csrf))
    assert again.status_code == 409

    done = analyst.post(
        f"/api/v1/response-tasks/{task_id}/complete",
        headers=csrf_headers(analyst_csrf),
        json={"note": "已通知长沙市应急办并回填反馈"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"
    assert done.json()["completed_at"] is not None
    assert done.json()["note"] == "已通知长沙市应急办并回填反馈"
    assert done.json()["overdue"] is False


def test_overdue_task_is_escalated_once(login, make_warning):
    from conftest import notifications_for

    from backend.app.db import SessionLocal
    from backend.app.models import ResponseTask
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-overdue")
    task_id = _tasks(admin, public_id)[0]["id"]
    _expire_task(task_id)

    with SessionLocal() as db:
        first = run_scan(db)
        db.commit()
    assert first.escalated >= 1

    escalated = _tasks(admin, public_id)[0]
    assert escalated["escalated_at"] is not None
    assert escalated["escalation_level"] == 1
    assert escalated["overdue"] is True
    # 超时不改流转状态
    assert escalated["status"] == "PENDING"

    assert len(notifications_for(analyst, task_id)) == 2  # TASK_ASSIGNED + TASK_OVERDUE
    assert len(notifications_for(admin, task_id)) == 1  # TASK_ESCALATED

    # 再跑一次不重复升级
    with SessionLocal() as db:
        second = run_scan(db)
        db.commit()
    assert second.escalated == 0
    with SessionLocal() as db:
        level = db.get(ResponseTask, task_id).escalation_level
    assert level == 1


def test_task_before_due_is_not_escalated(login, make_warning):
    from backend.app.db import SessionLocal
    from backend.app.models import ResponseTask
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-fresh")
    task_id = _tasks(admin, public_id)[0]["id"]

    with SessionLocal() as db:
        run_scan(db)
        db.commit()
        task = db.get(ResponseTask, task_id)
        assert task.escalated_at is None
        assert task.escalation_level == 0
