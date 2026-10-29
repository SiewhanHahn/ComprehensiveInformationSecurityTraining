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


def _delete_warnings(public_ids):
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal
    from backend.app.models import (
        FusionInput,
        FusionRun,
        Warning,
        WarningFeedback,
        WarningResult,
        WarningReview,
    )

    ids = [p for p in public_ids if p]
    if not ids:
        return
    with SessionLocal() as db:
        for warning in db.scalars(select(Warning).where(Warning.public_id.in_(ids))).all():
            result = db.get(WarningResult, warning.warning_result_id)
            db.execute(delete(WarningFeedback).where(WarningFeedback.warning_id == warning.id))
            db.execute(delete(WarningReview).where(WarningReview.warning_id == warning.id))
            db.delete(warning)
            db.flush()
            if result is not None:
                run_id = result.fusion_run_id
                db.delete(result)
                db.flush()
                db.execute(delete(FusionInput).where(FusionInput.fusion_run_id == run_id))
                db.execute(delete(FusionRun).where(FusionRun.id == run_id))
        db.commit()


def _delete_users(usernames):
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, User, UserRole

    if not usernames:
        return
    with SessionLocal() as db:
        ids = list(db.scalars(select(User.id).where(User.username.in_(list(usernames)))).all())
        if not ids:
            return
        db.execute(delete(UserRole).where(UserRole.user_id.in_(ids)))
        db.execute(
            delete(AuditLog).where(
                AuditLog.actor_id.in_(ids)
                | ((AuditLog.resource_type == "USER") & AuditLog.resource_id.in_([str(i) for i in ids]))
            )
        )
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()
