"""角色 × 接口权限矩阵。

需要运行中的 MySQL/Redis/API，并以 RUN_INTEGRATION=1 且注入 DEMO_*_PASSWORD 执行。
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="requires running MySQL/Redis/API",
)

CREDENTIALS = {
    "viewer_demo": "DEMO_VIEWER_PASSWORD",
    "analyst_demo": "DEMO_ANALYST_PASSWORD",
    "reviewer_demo": "DEMO_REVIEWER_PASSWORD",
    "admin_demo": "DEMO_ADMIN_PASSWORD",
}

READ_ENDPOINTS = ("/api/v1/warnings", "/api/v1/hazards", "/api/v1/monitor/status")


def _client_as(username):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    password = os.environ.get(CREDENTIALS[username])
    if not password:
        pytest.skip(f"{CREDENTIALS[username]} not set")

    client = TestClient(app)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return client, resp.json()["csrf_token"]


def _create_payload(title):
    return {
        "city_code": "CHANGSHA",
        "valid_date": "2024-03-27",
        "threshold_code": "HEAVY",
        "title": title,
        "area_text": "权限矩阵测试",
        "reasoning_text": "权限矩阵测试",
    }


def _cleanup_warning(public_id):
    from sqlalchemy import delete, select

    from backend.app.db import SessionLocal
    from backend.app.models import Warning, WarningFeedback, WarningResult, WarningReview

    with SessionLocal() as session:
        warning = session.scalar(select(Warning).where(Warning.public_id == public_id))
        if warning is None:
            return
        result_id = warning.warning_result_id
        session.execute(delete(WarningFeedback).where(WarningFeedback.warning_id == warning.id))
        session.execute(delete(WarningReview).where(WarningReview.warning_id == warning.id))
        session.delete(warning)
        session.flush()
        if result_id is not None:
            session.execute(delete(WarningResult).where(WarningResult.id == result_id))
        session.commit()


def test_unauthenticated_is_rejected():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)
    for path in (*READ_ENDPOINTS, "/api/v1/audit-logs"):
        assert client.get(path).status_code == 401, path


def test_viewer_read_only_and_limited_to_published():
    client, csrf = _client_as("viewer_demo")

    for path in READ_ENDPOINTS:
        assert client.get(path).status_code == 200, path

    assert client.get("/api/v1/warnings?status=PUBLISHED").status_code == 200
    assert client.get("/api/v1/warnings?status=DRAFT").json() == []
    assert client.get("/api/v1/audit-logs").status_code == 403

    resp = client.post(
        "/api/v1/warnings",
        headers={"X-CSRF-Token": csrf},
        json=_create_payload("rbac-viewer"),
    )
    assert resp.status_code == 403


def test_analyst_cannot_audit_review_or_publish():
    client, csrf = _client_as("analyst_demo")

    assert client.get("/api/v1/warnings").status_code == 200
    assert client.get("/api/v1/hazards").status_code == 200
    assert client.get("/api/v1/monitor/status").status_code == 200
    assert client.get("/api/v1/audit-logs").status_code == 403

    review = client.post(
        "/api/v1/warnings/unknown/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "APPROVE", "comment": "x"},
    )
    assert review.status_code == 403

    publish = client.post(
        "/api/v1/warnings/unknown/publish",
        headers={"X-CSRF-Token": csrf},
    )
    assert publish.status_code == 403


def test_reviewer_permissions_follow_assigned_roles():
    client, csrf = _client_as("reviewer_demo")

    me = client.get("/api/v1/auth/me").json()["user"]
    roles = set(me["roles"])
    assert "REVIEWER" in roles

    assert client.get("/api/v1/warnings").status_code == 200
    assert client.get("/api/v1/hazards").status_code == 200
    assert client.get("/api/v1/audit-logs").status_code == 403

    # 创建权限取决于是否同时拥有 ANALYST/ADMIN，而不是账号名。
    resp = client.post(
        "/api/v1/warnings",
        headers={"X-CSRF-Token": csrf},
        json=_create_payload("rbac-reviewer"),
    )
    if {"ANALYST", "ADMIN"} & roles:
        assert resp.status_code == 200, resp.text
        _cleanup_warning(resp.json()["public_id"])
    else:
        assert resp.status_code == 403


def test_admin_can_audit_and_monitor():
    client, _ = _client_as("admin_demo")

    assert client.get("/api/v1/audit-logs?page=1&page_size=5").status_code == 200
    assert client.get("/api/v1/warnings?status=PUBLISHED").status_code == 200
    assert client.get("/api/v1/hazards").status_code == 200
    assert client.get("/api/v1/monitor/status").status_code == 200


def test_invalid_status_filter_is_rejected():
    client, _ = _client_as("admin_demo")
    assert client.get("/api/v1/warnings?status=BOGUS").status_code == 400


def test_hazards_registry_contains_eight_entries():
    client, _ = _client_as("viewer_demo")
    data = client.get("/api/v1/hazards").json()

    assert data["summary"]["total"] == 8
    assert data["summary"]["implemented"] == 1
    assert data["summary"]["framework"] == 7

    codes = {item["code"] for item in data["hazards"]}
    assert codes == {
        "RAINSTORM",
        "TYPHOON",
        "HEATWAVE",
        "DROUGHT",
        "THUNDERSTORM",
        "FOG",
        "FLASH_FLOOD",
        "URBAN_WATERLOGGING",
    }
