"""User schema boundaries and opt-in end-to-end user-management coverage.

Integration tests require the real MySQL/Redis services and are intentionally
opt-in via ``RUN_INTEGRATION=1``.  They only mutate users created by the test.
"""

import os
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.schemas import (
    UserCreate,
    UserOut,
    UserPasswordReset,
    UserRolesUpdate,
    UserStatusUpdate,
)


# ---- schema boundaries ---------------------------------------------------


def test_password_is_not_trimmed_but_blank_password_is_rejected():
    value = "  pass-word  "
    assert UserPasswordReset(password=value).password == value

    for value in ("", "   ", "\t\n"):
        with pytest.raises(ValidationError):
            UserPasswordReset(password=value)


def test_roles_are_enum_valid_unique_and_sorted():
    assert UserRolesUpdate(roles=["VIEWER", "ADMIN", "VIEWER"]).roles == ["ADMIN", "VIEWER"]

    with pytest.raises(ValidationError):
        UserRolesUpdate(roles=[])
    with pytest.raises(ValidationError):
        UserRolesUpdate(roles=["NOT_A_ROLE"])


def test_username_boundaries_and_display_name_trimming():
    assert UserCreate(
        username="user_01-xy",
        display_name="  Display name  ",
        password="safe-password",
        roles=["VIEWER"],
    ).display_name == "Display name"

    for username in ("ab", "has space", "bad/name", "中文用户名"):
        with pytest.raises(ValidationError):
            UserCreate(username=username, display_name="User", password="safe-password", roles=["VIEWER"])

    with pytest.raises(ValidationError):
        UserCreate(username="valid_user", display_name="   ", password="safe-password", roles=["VIEWER"])


def test_status_update_requires_strict_boolean():
    assert UserStatusUpdate(is_active=True).is_active is True
    with pytest.raises(ValidationError):
        UserStatusUpdate(is_active=1)
    with pytest.raises(ValidationError):
        UserStatusUpdate(is_active="true")


def test_user_response_does_not_expose_password_fields():
    output = UserOut(id=7, username="safe_user", display_name="Safe", is_active=True, roles=["VIEWER"])
    dumped = output.model_dump()
    assert "password" not in dumped
    assert "password_hash" not in dumped


# ---- integration helpers -------------------------------------------------

integration = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="requires running MySQL/Redis/API",
)


def _admin_client():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    password = os.environ.get("DEMO_ADMIN_PASSWORD")
    if not password:
        pytest.skip("DEMO_ADMIN_PASSWORD not set")
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin_demo", "password": password},
    )
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"], response.json()["user"]["id"]


def _cleanup_users(usernames):
    """Delete only users created by this module, including their audit rows."""
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, User, UserRole

    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.username.in_(list(usernames)))).all()
        ids = [user.id for user in users]
        if not ids:
            return
        db.execute(delete(UserRole).where(UserRole.user_id.in_(ids)))
        db.execute(
            delete(AuditLog).where(
                (AuditLog.actor_id.in_(ids))
                | (
                    (AuditLog.resource_type == "USER")
                    & AuditLog.resource_id.in_([str(user_id) for user_id in ids])
                )
            )
        )
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()


@integration
def test_user_management_create_list_role_status_reset_self_protection_and_audit():
    client, csrf, admin_id = _admin_client()
    username = f"test_user_{uuid4().hex}"
    _cleanup_users({username})
    try:
        headers = {"X-CSRF-Token": csrf}
        payload = {
            "username": username,
            "display_name": "  User management test  ",
            "password": "initial-password",
            "roles": ["VIEWER", "VIEWER"],
        }

        created = client.post("/api/v1/users", headers=headers, json=payload)
        assert created.status_code == 201, created.text
        created_body = created.json()
        user_id = created_body["id"]
        assert created_body["username"] == username
        assert created_body["display_name"] == "User management test"
        assert created_body["roles"] == ["VIEWER"]
        assert "password" not in created_body
        assert "password_hash" not in created_body

        duplicate = client.post("/api/v1/users", headers=headers, json=payload)
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "USERNAME_EXISTS"
        assert "request_id" in duplicate.json()["error"]

        listing = client.get("/api/v1/users?page=1&page_size=100")
        assert listing.status_code == 200
        listed = next(item for item in listing.json()["items"] if item["id"] == user_id)
        assert listed["username"] == username
        assert "password_hash" not in listed

        from fastapi.testclient import TestClient
        from backend.app.main import app

        target = TestClient(app)
        login = target.post("/api/v1/auth/login", json={"username": username, "password": payload["password"]})
        assert login.status_code == 200

        changed_roles = client.put(
            f"/api/v1/users/{user_id}/roles",
            headers=headers,
            json={"roles": ["ANALYST", "VIEWER", "ANALYST"]},
        )
        assert changed_roles.status_code == 200, changed_roles.text
        assert changed_roles.json()["roles"] == ["ANALYST", "VIEWER"]
        assert sorted(target.get("/api/v1/auth/me").json()["user"]["roles"]) == ["ANALYST", "VIEWER"]

        disabled = client.patch(
            f"/api/v1/users/{user_id}/status",
            headers=headers,
            json={"is_active": False},
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["is_active"] is False
        assert target.get("/api/v1/auth/me").status_code == 401
        assert TestClient(app).post("/api/v1/auth/login", json={"username": username, "password": payload["password"]}).status_code == 401
        enabled = client.patch(
            f"/api/v1/users/{user_id}/status",
            headers=headers,
            json={"is_active": True},
        )
        assert enabled.status_code == 200

        reset = client.post(
            f"/api/v1/users/{user_id}/reset-password",
            headers=headers,
            json={"password": "reset-password"},
        )
        assert reset.status_code == 204
        assert target.get("/api/v1/auth/me").status_code == 200
        fresh = TestClient(app)
        assert fresh.post("/api/v1/auth/login", json={"username": username, "password": payload["password"]}).status_code == 401
        assert fresh.post("/api/v1/auth/login", json={"username": username, "password": "reset-password"}).status_code == 200

        # The authenticated admin cannot remove their own admin role or disable itself.
        self_disable = client.patch(
            f"/api/v1/users/{admin_id}/status",
            headers=headers,
            json={"is_active": False},
        )
        assert self_disable.status_code == 409
        self_demote = client.put(
            f"/api/v1/users/{admin_id}/roles",
            headers=headers,
            json={"roles": ["VIEWER"]},
        )
        assert self_demote.status_code == 409

        audit = client.get("/api/v1/audit-logs?action=USER_CREATE&page_size=100")
        assert audit.status_code == 200
        assert any(row["resource_id"] == str(user_id) for row in audit.json())

    finally:
        _cleanup_users({username})


@integration
def test_user_management_authentication_authorization_and_csrf():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/users").status_code == 401
    assert anonymous.get("/api/v1/users").json()["error"]["code"] == "UNAUTHENTICATED"

    client, csrf, _ = _admin_client()
    assert client.post(
        "/api/v1/users",
        json={
            "username": f"test_csrf_{uuid4().hex}",
            "display_name": "csrf",
            "password": "safe-password",
            "roles": ["VIEWER"],
        },
    ).status_code == 403
    assert client.post(
        "/api/v1/users",
        headers={"X-CSRF-Token": "wrong-token"},
        json={
            "username": f"test_csrf_{uuid4().hex}",
            "display_name": "csrf",
            "password": "safe-password",
            "roles": ["VIEWER"],
        },
    ).status_code == 403

    viewer_password = os.environ.get("DEMO_VIEWER_PASSWORD")
    if not viewer_password:
        pytest.skip("DEMO_VIEWER_PASSWORD not set")
    viewer = TestClient(app)
    login = viewer.post(
        "/api/v1/auth/login",
        json={"username": "viewer_demo", "password": viewer_password},
    )
    assert login.status_code == 200
    assert viewer.get("/api/v1/users").status_code == 403
    # Keep the valid CSRF token assertion explicit for the authenticated admin.
    assert client.get("/api/v1/users").status_code == 200
    assert csrf


@integration
@pytest.mark.parametrize("operation", ["status", "roles"])
def test_concurrent_admin_changes_recheck_revoked_actor(monkeypatch, operation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.routers import users

    admin, csrf, _ = _admin_client()
    names = {f"race_{uuid4().hex}" for _ in range(2)}
    accounts = []
    try:
        for name in names:
            created = admin.post("/api/v1/users", headers={"X-CSRF-Token": csrf}, json={
                "username": name, "display_name": name, "password": "race-password", "roles": ["ADMIN"],
            })
            assert created.status_code == 201, created.text
            client = TestClient(app)
            login = client.post("/api/v1/auth/login", json={"username": name, "password": "race-password"})
            assert login.status_code == 200
            accounts.append((client, login.json()["csrf_token"], created.json()["id"]))

        barrier = Barrier(2, timeout=10)
        original = users._lock_admin

        def synchronized_lock(db, current):
            barrier.wait()
            return original(db, current)

        monkeypatch.setattr(users, "_lock_admin", synchronized_lock)

        def change(index):
            client, token, _ = accounts[index]
            target = accounts[1 - index][2]
            headers = {"X-CSRF-Token": token}
            if operation == "status":
                return client.patch(f"/api/v1/users/{target}/status", headers=headers, json={"is_active": False})
            return client.put(f"/api/v1/users/{target}/roles", headers=headers, json={"roles": ["VIEWER"]})

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(change, [0, 1]))
        assert sorted(r.status_code for r in responses) == [200, 403], [r.text for r in responses]
        states = [client.get("/api/v1/auth/me") for client, _, _ in accounts]
        assert sum(r.status_code == 200 and "ADMIN" in r.json()["user"]["roles"] for r in states) == 1
    finally:
        _cleanup_users(names)


@integration
def test_error_responses_use_documented_envelope():
    client, csrf, _ = _admin_client()
    headers = {"X-CSRF-Token": csrf}
    responses = {
        "NOT_FOUND": client.patch("/api/v1/users/999999999/status", headers=headers, json={"is_active": True}),
        "VALIDATION_ERROR": client.post("/api/v1/users", headers=headers, json={"username": "x"}),
        "INVALID_PARAMETER": client.get("/api/v1/warnings?status=NOT_A_STATUS"),
    }
    for code, response in responses.items():
        error = response.json()["error"]
        assert error["code"] == code, response.text
        assert error["message"]
        assert error["request_id"] == response.headers["X-Request-ID"]
        assert "detail" not in response.json()
    assert client.get("/api/v1/no-such-route").json()["error"]["code"] == "NOT_FOUND"


@integration
@pytest.mark.parametrize("operation", ["create", "roles"])
def test_missing_role_reference_fails_without_partial_grant(monkeypatch, operation):
    from sqlalchemy import func, select

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, User
    from backend.app.routers import users

    admin, csrf, _ = _admin_client()
    headers = {"X-CSRF-Token": csrf}
    name = f"missing_role_{uuid4().hex}"
    try:
        user_id = None
        if operation == "roles":
            created = admin.post("/api/v1/users", headers=headers, json={
                "username": name, "display_name": name, "password": "missing-role-password", "roles": ["VIEWER"],
            })
            assert created.status_code == 201, created.text
            user_id = created.json()["id"]
        with SessionLocal() as db:
            audit_before = db.scalar(select(func.count()).select_from(AuditLog))

        # 模拟参考数据缺少 ANALYST：只过滤本测试请求的结果，不修改共享 roles 表
        original = users._roles

        def roles_without_analyst(db, codes):
            if "ANALYST" in codes:
                raise users.HTTPException(status_code=503, detail="DEPENDENCY_UNAVAILABLE")
            return original(db, codes)

        monkeypatch.setattr(users, "_roles", roles_without_analyst)
        if operation == "create":
            response = admin.post("/api/v1/users", headers=headers, json={
                "username": name, "display_name": name, "password": "missing-role-password",
                "roles": ["ANALYST", "VIEWER"],
            })
        else:
            response = admin.put(f"/api/v1/users/{user_id}/roles", headers=headers, json={"roles": ["ANALYST"]})
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"

        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == name))
            if operation == "create":
                assert user is None
            else:
                assert [role.code for role in user.roles] == ["VIEWER"]
            assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_before
    finally:
        _cleanup_users({name})


@integration
def test_roles_helper_rejects_incomplete_reference_rows():
    from backend.app.db import SessionLocal
    from backend.app.routers import users

    with SessionLocal() as db:
        assert set(users._roles(db, {"ADMIN", "VIEWER"})) == {"ADMIN", "VIEWER"}
        with pytest.raises(users.HTTPException) as exc:
            users._roles(db, {"VIEWER", "NOT_SEEDED_ROLE"})
        assert exc.value.status_code == 503
        assert exc.value.detail == "DEPENDENCY_UNAVAILABLE"


@integration
@pytest.mark.parametrize("operation", ["status", "roles"])
def test_audit_failure_rolls_back_user_change(monkeypatch, operation):
    from sqlalchemy import func, select

    from backend.app.db import SessionLocal
    from backend.app.models import AuditLog, User
    from backend.app.routers import users

    admin, csrf, _ = _admin_client()
    name = f"rollback_{uuid4().hex}"
    try:
        created = admin.post("/api/v1/users", headers={"X-CSRF-Token": csrf}, json={
            "username": name, "display_name": name, "password": "rollback-password", "roles": ["VIEWER"],
        })
        assert created.status_code == 201, created.text
        user_id = created.json()["id"]
        with SessionLocal() as db:
            before = db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.resource_type == "USER", AuditLog.resource_id == str(user_id),
            ))

        def fail_audit(db, **kwargs):
            db.flush()
            raise RuntimeError("injected audit failure")

        monkeypatch.setattr(users, "add_audit", fail_audit)
        with pytest.raises(RuntimeError, match="injected audit failure"):
            if operation == "status":
                admin.patch(f"/api/v1/users/{user_id}/status", headers={"X-CSRF-Token": csrf}, json={"is_active": False})
            else:
                admin.put(f"/api/v1/users/{user_id}/roles", headers={"X-CSRF-Token": csrf}, json={"roles": ["ANALYST"]})

        with SessionLocal() as db:
            user = db.get(User, user_id)
            assert user.is_active is True
            assert [role.code for role in user.roles] == ["VIEWER"]
            after = db.scalar(select(func.count()).select_from(AuditLog).where(
                AuditLog.resource_type == "USER", AuditLog.resource_id == str(user_id),
            ))
            assert after == before
    finally:
        _cleanup_users({name})
