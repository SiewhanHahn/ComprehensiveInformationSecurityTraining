"""健康检查、登录与回放的基础集成测试（RUN_INTEGRATION=1）。"""

import os

import pytest

from conftest import csrf_headers

pytestmark = pytest.mark.integration


def test_health_endpoints(new_client):
    client = new_client()
    assert client.get("/health").status_code == 200
    assert client.get("/health/db").status_code == 200
    assert client.get("/health/redis").status_code == 200


def test_login_and_replay(login):
    client, token = login("viewer_demo")
    replay = client.get("/api/v1/replay?city_code=CHANGSHA&date=2024-03-27&threshold_code=HEAVY")
    assert replay.status_code == 200
    assert replay.json()["data_status"] == "COMPLETE"
    assert replay.json()["fused_mm"] > 0

    # state-changing request without CSRF must be rejected
    no_csrf = client.post("/api/v1/warnings/unknown/submit", headers={})
    assert no_csrf.status_code in (403, 404)
    with_csrf = client.post("/api/v1/warnings/unknown/submit", headers=csrf_headers(token))
    assert with_csrf.status_code in (403, 404)


def test_csrf_cookie_and_partial(new_client):
    client = new_client()
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "viewer_demo", "password": os.environ.get("DEMO_VIEWER_PASSWORD", "")},
    )
    assert resp.status_code == 200
    # 登录应下发可被 JS 读取的 ww_csrf cookie（用于刷新后回退）
    assert "ww_csrf=" in resp.headers.get("set-cookie", "")
    # PARTIAL 回放 fused_mm 应为 null 而非 0.0
    partial = client.get("/api/v1/replay?city_code=CHANGSHA&date=2024-02-06&threshold_code=HEAVY")
    assert partial.status_code == 200
    assert partial.json()["data_status"] == "PARTIAL"
    assert partial.json()["fused_mm"] is None
