"""响应任务：发布自动派发、接单与完成、超时升级（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

任务随预警创建，由 ``created_warnings`` 夹具一并清理；升级扫描直接调用
``run_scan(db, now=...)``，不依赖后台线程或 sleep。
"""

from datetime import datetime, timedelta

import pytest

from conftest import review_body, csrf_headers, publish_warning

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

    # 审核员能读到该预警的任务（详情页要展示负责人与时限），但推不动它
    visible = _tasks(reviewer, public_id)
    assert len(visible) == 1, visible
    assert visible[0]["assignee"] == "analyst_demo"

    # 不带预警过滤的看板列表仍然只给自己的任务
    board = reviewer.get("/api/v1/response-tasks")
    assert board.status_code == 200, board.text
    assert all(t["id"] != task_id for t in board.json()), board.json()

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


def test_completed_task_is_not_escalated(login, make_warning):
    """完成之后再过期：升级扫描不能把已完成的任务标成逾期。

    候选查询排除 ``COMPLETED``，条件 UPDATE 的 ``WHERE`` 再挡一层，
    所以「扫描读出候选之后、写入之前才提交完成」这种并发顺序也不会被覆盖成已升级。
    """
    from conftest import notifications_for

    from backend.app.db import SessionLocal
    from backend.app.models import ResponseTask
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-done")
    task_id = _tasks(admin, public_id)[0]["id"]

    assert analyst.post(
        f"/api/v1/response-tasks/{task_id}/ack", headers=csrf_headers(analyst_csrf)
    ).status_code == 200
    done = analyst.post(
        f"/api/v1/response-tasks/{task_id}/complete",
        headers=csrf_headers(analyst_csrf),
        json={"note": "提前处置完毕"},
    )
    assert done.status_code == 200, done.text

    _expire_task(task_id)  # 完成之后时限才过期

    with SessionLocal() as db:
        run_scan(db)
        db.commit()
        task = db.get(ResponseTask, task_id)
        assert task.status == "COMPLETED"
        assert task.escalated_at is None
        assert task.escalation_level == 0

    # 也不该给负责人或管理员发「超时」「升级」通知
    assert "TASK_OVERDUE" not in {n["kind"] for n in notifications_for(analyst, task_id)}
    assert notifications_for(admin, task_id) == []


def test_withdrawal_closes_task_and_stops_escalation(login, make_warning):
    """撤回预警后任务自动关闭：不能再出现「已撤回预警超时升级」的通知。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, ResponseTask
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-withdraw")
    task_id = _tasks(admin, public_id)[0]["id"]

    withdrawn = reviewer.post(
        f"/api/v1/warnings/{public_id}/withdraw", headers=csrf_headers(reviewer_csrf)
    )
    assert withdrawn.status_code == 200, withdrawn.text

    task = _tasks(admin, public_id)[0]
    assert task["status"] == "COMPLETED"
    assert task["completed_at"] is not None
    assert task["overdue"] is False

    _expire_task(task_id)
    with SessionLocal() as db:
        run_scan(db)
        db.commit()
        task = db.get(ResponseTask, task_id)
        assert task.escalated_at is None
        close_audits = db.scalars(
            select(AuditLog).where(
                AuditLog.action == "RESPONSE_TASK_CLOSE",
                AuditLog.resource_id == str(task_id),
            )
        ).all()
        assert close_audits and close_audits[0].actor_role == "SYSTEM"


def test_inactive_creator_task_goes_to_publisher(login, make_warning):
    """创建者提交草稿后被停用：任务改派给发布人，停用账号不再收到通知。

    停用账号登录不了、也没有改派接口，任务若挂给它就永远没人能推进。
    """
    from sqlalchemy import select

    from conftest import notifications_for

    from backend.app.db import SessionLocal
    from backend.app.models import User

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = make_warning(analyst, analyst_csrf, "task-reassign")
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)
    ).status_code == 200

    def set_active(value: bool) -> None:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == "analyst_demo"))
            user.is_active = value
            db.commit()

    set_active(False)
    try:
        assert reviewer.post(
            f"/api/v1/warnings/{public_id}/review",
            headers=csrf_headers(reviewer_csrf),
            json=review_body(reviewer, public_id, "APPROVE", "同意发布"),
        ).status_code == 200
        resp = reviewer.post(f"/api/v1/warnings/{public_id}/publish", headers=csrf_headers(reviewer_csrf))
        assert resp.status_code == 200, resp.text
    finally:
        set_active(True)

    task = _tasks(admin, public_id)[0]
    assert task["assignee"] == "reviewer_demo"
    # 指派通知投递给新的负责人，停用账号收不到
    assert notifications_for(analyst, task["id"]) == []
    assert [n["kind"] for n in notifications_for(reviewer, task["id"])] == ["TASK_ASSIGNED"]


def test_inactive_assignee_gets_no_overdue_notification(login, make_warning):
    """负责人已停用时不再给它堆超时通知；管理员的升级通知照发。"""
    from sqlalchemy import select

    from conftest import notifications_for

    from backend.app.db import SessionLocal
    from backend.app.models import User
    from backend.app.scheduler import run_scan

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "task-noassignee")
    task_id = _tasks(admin, public_id)[0]["id"]
    _expire_task(task_id)

    def set_active(value: bool) -> None:
        with SessionLocal() as db:
            db.scalar(select(User).where(User.username == "analyst_demo")).is_active = value
            db.commit()

    set_active(False)
    try:
        with SessionLocal() as db:
            run_scan(db)
            db.commit()
    finally:
        set_active(True)

    assert "TASK_OVERDUE" not in {n["kind"] for n in notifications_for(analyst, task_id)}
    assert [n["kind"] for n in notifications_for(admin, task_id)] == ["TASK_ESCALATED"]


def test_demoted_creator_task_goes_to_publisher(login, make_warning):
    """创建者被降级到只剩 VIEWER：任务同样改派发布人。

    这类账号一打开 /response-tasks 就 403，任务挂在它名下等于没人能处理。
    """
    from sqlalchemy import delete, select

    from conftest import notifications_for

    from backend.app.db import SessionLocal
    from backend.app.models import Role, User, UserRole

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = make_warning(analyst, analyst_csrf, "task-demoted")
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)
    ).status_code == 200

    with SessionLocal() as db:
        analyst_id = db.scalar(select(User.id).where(User.username == "analyst_demo"))
        role_id = db.scalar(select(Role.id).where(Role.code == "ANALYST"))
        db.execute(delete(UserRole).where(UserRole.user_id == analyst_id, UserRole.role_id == role_id))
        db.commit()

    try:
        assert reviewer.post(
            f"/api/v1/warnings/{public_id}/review",
            headers=csrf_headers(reviewer_csrf),
            json=review_body(reviewer, public_id, "APPROVE", "同意发布"),
        ).status_code == 200
        assert reviewer.post(
            f"/api/v1/warnings/{public_id}/publish", headers=csrf_headers(reviewer_csrf)
        ).status_code == 200
    finally:
        with SessionLocal() as db:
            db.add(UserRole(user_id=analyst_id, role_id=role_id, granted_by=analyst_id))
            db.commit()

    task = _tasks(admin, public_id)[0]
    assert task["assignee"] == "reviewer_demo"
    assert notifications_for(reviewer, task["id"])[0]["kind"] == "TASK_ASSIGNED"


def test_escalate_overdue_and_publish_acquire_expected_locks(login, make_warning, monkeypatch):
    """I-12/I-13：超时升级先加锁确认预警未撤回，派单资格查询使用 FOR UPDATE。"""
    from datetime import timedelta
    from sqlalchemy import event, select

    from backend.app.clock import utcnow
    from backend.app.db import SessionLocal, engine
    from backend.app.models import ResponseTask, Warning
    from backend.app.services import notifications as notif_svc
    from backend.app.services import tasks as task_svc
    from backend.app.services import warnings as warn_svc

    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    admin, _ = login("admin_demo")

    public_id = make_warning(analyst, analyst_csrf, "lock-check")
    assert analyst.post(f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/review",
        headers=csrf_headers(reviewer_csrf),
        json=review_body(reviewer, public_id, "APPROVE", "同意"),
    ).status_code == 200

    executed_sqls: list[str] = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        executed_sqls.append(statement.upper())

    engine_ref = engine
    event.listen(engine_ref, "before_cursor_execute", capture_sql)
    try:
        assert reviewer.post(
            f"/api/v1/warnings/{public_id}/publish", headers=csrf_headers(reviewer_csrf)
        ).status_code == 200
    finally:
        event.remove(engine_ref, "before_cursor_execute", capture_sql)

    assert any("FOR UPDATE" in s and "USERS" in s and "USER_ROLES" in s for s in executed_sqls), executed_sqls

    # 验证 withdraw_warning 先关闭任务再发撤回通知
    call_order: list[str] = []
    orig_close = warn_svc.close_for_withdrawn
    orig_notify = warn_svc.notify_warning
    monkeypatch.setattr(warn_svc, "close_for_withdrawn", lambda *a, **kw: (call_order.append("close"), orig_close(*a, **kw))[1])
    monkeypatch.setattr(warn_svc, "notify_warning", lambda *a, **kw: (call_order.append("notify"), orig_notify(*a, **kw))[1])

    task_id = _tasks(admin, public_id)[0]["id"]
    with SessionLocal() as db:
        t = db.get(ResponseTask, task_id)
        t.due_at = utcnow() - timedelta(minutes=10)
        db.commit()

        # escalate_overdue 对 Warning 加 FOR UPDATE 锁检查状态，避免并发撤回窗口里误升级
        esc_sqls: list[str] = []

        def capture_esc(conn, cursor, statement, parameters, context, executemany):
            esc_sqls.append(statement.upper())

        event.listen(engine_ref, "before_cursor_execute", capture_esc)
        try:
            assert task_svc.escalate_overdue(db, now=utcnow()) == 1
        finally:
            event.remove(engine_ref, "before_cursor_execute", capture_esc)
            db.rollback()

    warning_lock_idx = next(
        (i for i, s in enumerate(esc_sqls) if "FOR UPDATE" in s and "WARNINGS" in s),
        None,
    )
    task_update_idx = next(
        (i for i, s in enumerate(esc_sqls) if s.startswith("UPDATE RESPONSE_TASKS")),
        None,
    )
    assert warning_lock_idx is not None and task_update_idx is not None and warning_lock_idx < task_update_idx, esc_sqls

    reviewer.post(f"/api/v1/warnings/{public_id}/withdraw", headers=csrf_headers(reviewer_csrf))
    assert call_order[:2] == ["close", "notify"], call_order
