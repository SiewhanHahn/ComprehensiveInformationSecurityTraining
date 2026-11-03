"""共享测试夹具。

标记为 ``integration`` 的测试需要运行中的 MySQL/Redis，并设置 ``RUN_INTEGRATION=1``
与 ``DEMO_*_PASSWORD``；未设置时自动跳过。测试只清理自己创建的数据。
"""

import os
from uuid import uuid4

import pytest

DEMO_PASSWORD_ENV = {
    "viewer_demo": "DEMO_VIEWER_PASSWORD",
    "analyst_demo": "DEMO_ANALYST_PASSWORD",
    "reviewer_demo": "DEMO_REVIEWER_PASSWORD",
    "admin_demo": "DEMO_ADMIN_PASSWORD",
}

# 回放样本中四模式完整的一天（长沙 2024-03-27，融合 29.625mm）
COMPLETE_DAY = {"city_code": "CHANGSHA", "valid_date": "2024-03-27"}
# 回放样本中缺 GEM 的一天
PARTIAL_DAY = {"city_code": "CHANGSHA", "valid_date": "2024-02-06"}


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires running MySQL/Redis (RUN_INTEGRATION=1)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="requires running MySQL/Redis/API (set RUN_INTEGRATION=1)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


def csrf_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, prefix, **overrides) -> str:
    """建草稿 → 提交 → 批准 → 发布，返回 public_id。三个集成测试文件共用。"""
    public_id = make_warning(analyst, analyst_csrf, prefix, **overrides)
    assert analyst.post(
        f"/api/v1/warnings/{public_id}/submit", headers=csrf_headers(analyst_csrf)
    ).status_code == 200
    assert reviewer.post(
        f"/api/v1/warnings/{public_id}/review",
        headers=csrf_headers(reviewer_csrf),
        json={"decision": "APPROVE", "comment": "同意发布"},
    ).status_code == 200
    resp = reviewer.post(f"/api/v1/warnings/{public_id}/publish", headers=csrf_headers(reviewer_csrf))
    assert resp.status_code == 200, resp.text
    return public_id


def notifications_for(client, resource_id) -> list[dict]:
    """按资源标识（预警 public_id 或任务 id）过滤当前用户的通知。"""
    resp = client.get("/api/v1/notifications", params={"page_size": 100})
    assert resp.status_code == 200, resp.text
    target = str(resource_id)
    return [n for n in resp.json()["items"] if n["resource_id"] == target]


@pytest.fixture
def new_client():
    """返回无会话 TestClient 的工厂；每次调用得到独立 Cookie 容器。"""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    return lambda: TestClient(app)


@pytest.fixture
def login(new_client):
    """``login(username, password=None) -> (client, csrf)``；演示账号密码从环境变量读取。"""

    def _login(username: str, password: str | None = None):
        if password is None:
            env = DEMO_PASSWORD_ENV[username]
            password = os.environ.get(env)
            if not password:
                pytest.skip(f"{env} not set")
        client = new_client()
        resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert resp.status_code == 200, resp.text
        return client, resp.json()["csrf_token"]

    return _login


@pytest.fixture
def created_warnings():
    """测试把创建的预警 public_id 追加到此列表，结束时连同融合记录一并删除。"""
    public_ids: list[str] = []
    yield public_ids
    _delete_warnings(public_ids)


@pytest.fixture
def make_warning(created_warnings):
    """``make_warning(client, csrf, prefix, **overrides) -> public_id``，默认使用完整样本日。"""

    def _make(client, csrf: str, prefix: str = "test", **overrides) -> str:
        payload = {
            **COMPLETE_DAY,
            "threshold_code": "HEAVY",
            "title": f"{prefix}-{uuid4().hex[:8]}",
            "area_text": "自动化测试",
            "reasoning_text": "自动化测试",
            **overrides,
        }
        resp = client.post("/api/v1/warnings", headers=csrf_headers(csrf), json=payload)
        assert resp.status_code == 200, resp.text
        public_id = resp.json()["public_id"]
        created_warnings.append(public_id)
        return public_id

    return _make


@pytest.fixture
def created_users():
    """测试把创建的用户名加入此集合，结束时删除用户、角色关联及其审计记录。"""
    usernames: set[str] = set()
    yield usernames
    _delete_users(usernames)


@pytest.fixture
def created_subscriptions():
    """测试把创建的订阅 id 追加到此列表，结束时删除，避免污染演示库和后续扫描。"""
    ids: list[int] = []
    yield ids
    _delete_subscriptions(ids)


def _make_viewer(login, created_users):
    """建一个临时 VIEWER 账号并返回 ``(client, csrf)``；账号删除时订阅与通知一起清理。"""
    admin, admin_csrf = login("admin_demo")
    username = f"subtest_{uuid4().hex[:8]}"
    password = f"Aa1-{uuid4().hex[:12]}"
    resp = admin.post(
        "/api/v1/users",
        headers=csrf_headers(admin_csrf),
        json={"username": username, "display_name": "订阅测试", "password": password, "roles": ["VIEWER"]},
    )
    assert resp.status_code == 201, resp.text
    created_users.add(username)
    return login(username, password)


@pytest.fixture
def subscriber(login, created_users):
    """临时 VIEWER 账号作为订阅者，返回 ``(client, csrf)``。

    用独立账号而不是 ``viewer_demo``：演示库里的演示账号可能已有订阅和通知，
    会让「是否投递」「未读数」这类断言依赖环境残留。
    """
    return _make_viewer(login, created_users)


@pytest.fixture
def bystander(login, created_users):
    """另一个同样没有订阅的临时账号，用来验证通知不会串到别人头上。"""
    return _make_viewer(login, created_users)


def _delete_warnings(public_ids):
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal
    from backend.app.models import (
        FusionInput,
        FusionRun,
        Notification,
        ResponseTask,
        Warning,
        WarningFeedback,
        WarningResult,
        WarningReview,
    )

    ids = [p for p in public_ids if p]
    if not ids:
        return
    with SessionLocal() as db:
        # 通知按 public_id 弱引用预警（不建外键），必须显式清理
        db.execute(
            delete(Notification).where(
                Notification.resource_type == "warning", Notification.resource_id.in_(ids)
            )
        )
        for warning in db.scalars(select(Warning).where(Warning.public_id.in_(ids))).all():
            result = db.get(WarningResult, warning.warning_result_id)
            db.execute(delete(WarningFeedback).where(WarningFeedback.warning_id == warning.id))
            db.execute(delete(WarningReview).where(WarningReview.warning_id == warning.id))
            db.execute(delete(ResponseTask).where(ResponseTask.warning_id == warning.id))
            db.delete(warning)
            db.flush()
            if result is not None:
                run_id = result.fusion_run_id
                db.delete(result)
                db.flush()
                db.execute(delete(FusionInput).where(FusionInput.fusion_run_id == run_id))
                db.execute(delete(FusionRun).where(FusionRun.id == run_id))
        db.commit()


def _delete_subscriptions(ids):
    from sqlalchemy import delete

    from backend.app.db import SessionLocal
    from backend.app.models import WarningSubscription

    if not ids:
        return
    with SessionLocal() as db:
        db.execute(delete(WarningSubscription).where(WarningSubscription.id.in_(list(ids))))
        db.commit()


def _delete_users(usernames):
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, Notification, ResponseTask, User, UserRole, WarningSubscription

    if not usernames:
        return
    with SessionLocal() as db:
        ids = list(db.scalars(select(User.id).where(User.username.in_(list(usernames)))).all())
        if not ids:
            return
        # 三张新表都外键到 users 且没有 ondelete，必须先清
        db.execute(
            delete(ResponseTask).where(
                ResponseTask.assignee_id.in_(ids) | ResponseTask.created_by.in_(ids)
            )
        )
        db.execute(delete(Notification).where(Notification.user_id.in_(ids)))
        db.execute(delete(WarningSubscription).where(WarningSubscription.user_id.in_(ids)))
        db.execute(delete(UserRole).where(UserRole.user_id.in_(ids)))
        db.execute(
            delete(AuditLog).where(
                AuditLog.actor_id.in_(ids)
                | ((AuditLog.resource_type == "USER") & AuditLog.resource_id.in_([str(i) for i in ids]))
            )
        )
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()
