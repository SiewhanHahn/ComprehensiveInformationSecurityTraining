"""登录与会话安全（FR-01 / SEC-01）。需要 RUN_INTEGRATION=1 与 DEMO_*_PASSWORD。"""

from uuid import uuid4

import pytest

from conftest import csrf_headers

pytestmark = pytest.mark.integration

PASSWORD = "initial-password"


def _create_user(admin, admin_csrf, created_users, prefix, password=PASSWORD, roles=("VIEWER",)):
    username = f"{prefix}_{uuid4().hex[:12]}"
    resp = admin.post(
        "/api/v1/users",
        headers=csrf_headers(admin_csrf),
        json={"username": username, "display_name": username, "password": password, "roles": list(roles)},
    )
    assert resp.status_code == 201, resp.text
    created_users.add(username)
    return username


def _login(new_client, username, password, headers=None):
    return new_client().post("/api/v1/auth/login", json={"username": username, "password": password}, headers=headers or {})


def test_unknown_and_wrong_password_are_indistinguishable(new_client):
    unknown = _login(new_client, f"no_such_{uuid4().hex}", "anything")
    wrong = _login(new_client, "viewer_demo", "definitely-wrong")
    assert unknown.status_code == 401
    assert wrong.status_code == 401
    # request_id 每个响应不同，只比较码与文案，确认不泄露“用户是否存在”
    assert unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"]
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_disabled_account_only_after_correct_password(login, created_users, new_client):
    admin, admin_csrf = login("admin_demo")
    username = _create_user(admin, admin_csrf, created_users, "disable")
    # 用列表找到用户 id 后停用
    listing = admin.get("/api/v1/users?page=1&page_size=100").json()["items"]
    uid = next(item["id"] for item in listing if item["username"] == username)
    assert admin.patch(f"/api/v1/users/{uid}/status", headers=csrf_headers(admin_csrf), json={"is_active": False}).status_code == 200

    wrong = _login(new_client, username, "wrong-password")
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"

    correct = _login(new_client, username, PASSWORD)
    assert correct.status_code == 401
    assert correct.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_lockout_returns_generic_message(login, created_users, new_client):
    admin, admin_csrf = login("admin_demo")
    username = _create_user(admin, admin_csrf, created_users, "lock")

    for _ in range(5):
        assert _login(new_client, username, "wrong-password").status_code == 401

    # 已锁定：即使密码正确也返回统一的 INVALID_CREDENTIALS，不泄露“已锁定”状态
    correct = _login(new_client, username, PASSWORD)
    assert correct.status_code == 401
    assert correct.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_logout_invalidates_session(login):
    client, csrf = login("viewer_demo")
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/logout", headers=csrf_headers(csrf)).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_ip_rate_limit_blocks_after_threshold(new_client):
    from backend.app.config import get_settings

    ip = "10.99.99.99"
    headers = {"X-Real-IP": ip}
    limit = get_settings().ip_login_attempts

    for _ in range(limit):
        resp = _login(new_client, f"no_such_{uuid4().hex}", "x", headers=headers)
        assert resp.status_code == 401

    blocked = _login(new_client, f"no_such_{uuid4().hex}", "x", headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "LOGIN_RATE_LIMITED"
