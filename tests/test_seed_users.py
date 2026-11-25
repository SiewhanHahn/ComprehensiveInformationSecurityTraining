"""Demo credentials may be explicitly reset, but existing grants belong to administrators."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.app import seed
from backend.app.clock import utcnow
from backend.app.db import SessionLocal
from backend.app.models import User
from backend.app.security import verify_password
from conftest import csrf_headers


@pytest.mark.integration
@pytest.mark.parametrize(
    ("sync_passwords", "disable_first"),
    [(False, False), (False, True), (True, True)],
    ids=["active", "disabled", "credential-reset"],
)
def test_seed_preserves_admin_assigned_roles_on_rerun(monkeypatch, login, created_users, sync_passwords, disable_first):
    # Use a disposable account instead of changing any of the four shared demo identities.
    username = "seedtest_" + uuid4().hex[:12]
    created_users.add(username)
    env = "TEST_SEED_PASSWORD"
    initial, replacement = uuid4().hex, uuid4().hex
    monkeypatch.setattr(seed, "DEMO_ACCOUNTS", [(username, "教学账号", "ADMIN", env)])
    monkeypatch.setenv(env, initial)
    with SessionLocal() as db:
        seed.seed_users(db)
        user = db.scalar(select(User).where(User.username == username))
        user_id = user.id
        assert [r.code for r in user.roles] == ["ADMIN"]
        assert verify_password(initial, user.password_hash)

    admin, csrf = login("admin_demo")
    url = f"/api/v1/users/{user_id}"
    new_roles = ["REVIEWER", "VIEWER"]
    changed = admin.put(url + "/roles", headers=csrf_headers(csrf), json={"roles": new_roles})
    assert changed.status_code == 200, changed.text
    if disable_first:
        disabled = admin.patch(url + "/status", headers=csrf_headers(csrf), json={"is_active": False})
        assert disabled.status_code == 200, disabled.text

    # A disabled, locked account must stay that way unless credentials are explicitly reset.
    locked_until = utcnow() + timedelta(hours=1) if disable_first else None
    if disable_first:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            user.failed_login_count = 3
            user.locked_until = locked_until
            db.commit()

    monkeypatch.setenv(env, replacement)
    with SessionLocal() as db:
        seed.seed_users(db, sync_passwords=sync_passwords)
    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert sorted(r.code for r in user.roles) == new_roles
        assert user.is_active is (sync_passwords or not disable_first)
        assert user.failed_login_count == (3 if disable_first and not sync_passwords else 0)
        assert user.locked_until == (None if sync_passwords else locked_until)
        assert verify_password(replacement if sync_passwords else initial, user.password_hash)

    if sync_passwords or not disable_first:
        target, _ = login(username, replacement if sync_passwords else initial)
        me = target.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        assert sorted(me.json()["user"]["roles"]) == new_roles
