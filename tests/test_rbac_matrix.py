"""角色 × 接口权限矩阵（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。"""

import pytest

from conftest import COMPLETE_DAY, csrf_headers

pytestmark = pytest.mark.integration

READ_ENDPOINTS = ("/api/v1/warnings", "/api/v1/hazards", "/api/v1/monitor/status")


def _create_payload(title):
    return {
        **COMPLETE_DAY,
        "threshold_code": "HEAVY",
        "title": title,
        "area_text": "权限矩阵测试",
        "reasoning_text": "权限矩阵测试",
    }


def test_unauthenticated_is_rejected(new_client):
    client = new_client()
    protected = (
        *READ_ENDPOINTS,
        "/api/v1/audit-logs",
        "/api/v1/cities",
        "/api/v1/replay?city_code=CHANGSHA&date=2024-03-27&threshold_code=HEAVY",
    )
    for path in protected:
        assert client.get(path).status_code == 401, path


def test_viewer_read_only_and_limited_to_published(login):
    client, csrf = login("viewer_demo")

    for path in READ_ENDPOINTS:
        assert client.get(path).status_code == 200, path

    assert client.get("/api/v1/warnings?status=PUBLISHED").status_code == 200
    assert client.get("/api/v1/warnings?status=DRAFT").json() == []
    assert client.get("/api/v1/audit-logs").status_code == 403

    resp = client.post("/api/v1/warnings", headers=csrf_headers(csrf), json=_create_payload("rbac-viewer"))
    assert resp.status_code == 403


def test_analyst_cannot_audit_review_or_publish(login):
    client, csrf = login("analyst_demo")

    assert client.get("/api/v1/warnings").status_code == 200
    assert client.get("/api/v1/hazards").status_code == 200
    assert client.get("/api/v1/monitor/status").status_code == 200
    assert client.get("/api/v1/audit-logs").status_code == 403

    review = client.post(
        "/api/v1/warnings/unknown/review",
        headers=csrf_headers(csrf),
        json={"decision": "APPROVE", "comment": "x"},
    )
    assert review.status_code == 403

    publish = client.post("/api/v1/warnings/unknown/publish", headers=csrf_headers(csrf))
    assert publish.status_code == 403


def test_reviewer_permissions_follow_assigned_roles(login, created_warnings):
    client, csrf = login("reviewer_demo")

    roles = set(client.get("/api/v1/auth/me").json()["user"]["roles"])
    assert "REVIEWER" in roles

    assert client.get("/api/v1/warnings").status_code == 200
    assert client.get("/api/v1/hazards").status_code == 200
    assert client.get("/api/v1/audit-logs").status_code == 403

    # 创建权限取决于是否同时拥有 ANALYST/ADMIN，而不是账号名。
    resp = client.post("/api/v1/warnings", headers=csrf_headers(csrf), json=_create_payload("rbac-reviewer"))
    if {"ANALYST", "ADMIN"} & roles:
        assert resp.status_code == 200, resp.text
        created_warnings.append(resp.json()["public_id"])
    else:
        assert resp.status_code == 403


def test_admin_can_audit_and_monitor(login):
    client, _ = login("admin_demo")

    assert client.get("/api/v1/audit-logs?page=1&page_size=5").status_code == 200
    assert client.get("/api/v1/warnings?status=PUBLISHED").status_code == 200
    assert client.get("/api/v1/hazards").status_code == 200
    assert client.get("/api/v1/monitor/status").status_code == 200


def test_invalid_status_filter_is_rejected(login):
    client, _ = login("admin_demo")
    assert client.get("/api/v1/warnings?status=BOGUS").status_code == 400


def test_hazards_registry_contains_eight_entries(login):
    client, _ = login("viewer_demo")
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
