"""订阅与站内通知（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

订阅者用 ``subscriber`` 夹具创建的临时账号，不依赖演示账号的历史订阅；
通知按 ``resource_id``（预警 public_id）挂在预警上，随预警一并删除。
"""

import pytest

from conftest import csrf_headers

pytestmark = pytest.mark.integration


def _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, prefix, **overrides) -> str:
    """建草稿 → 提交 → 批准 → 发布，返回 public_id。"""
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


def _subscribe(client, csrf, created, hazard_type="RAINSTORM", city_code="") -> dict:
    resp = client.post(
        "/api/v1/subscriptions",
        headers=csrf_headers(csrf),
        json={"hazard_type": hazard_type, "city_code": city_code},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    created.append(body["id"])
    return body


def _notifications_for(client, public_id) -> list[dict]:
    # 只看第一页足够：同一测试最多产生个位数通知
    resp = client.get("/api/v1/notifications", params={"page_size": 100})
    assert resp.status_code == 200, resp.text
    return [n for n in resp.json()["items"] if n["resource_id"] == public_id]


def test_publish_notifies_matching_subscriber(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-match")

    items = _notifications_for(viewer, public_id)
    assert len(items) == 1, items
    assert items[0]["kind"] == "WARNING_PUBLISHED"
    assert items[0]["read_at"] is None
    assert "长沙" in items[0]["body"]


def test_publish_skips_non_matching_subscription(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    # 订阅的是台风，发布的是暴雨
    _subscribe(viewer, viewer_csrf, created_subscriptions, hazard_type="TYPHOON")
    public_id = _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-skip")

    assert _notifications_for(viewer, public_id) == []


def test_withdraw_notifies_subscribers(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-withdraw")

    withdraw = reviewer.post(f"/api/v1/warnings/{public_id}/withdraw", headers=csrf_headers(reviewer_csrf))
    assert withdraw.status_code == 200, withdraw.text

    kinds = sorted(n["kind"] for n in _notifications_for(viewer, public_id))
    assert kinds == ["WARNING_PUBLISHED", "WARNING_WITHDRAWN"]


def test_duplicate_subscription_conflict(subscriber, created_subscriptions):
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    dup = viewer.post(
        "/api/v1/subscriptions",
        headers=csrf_headers(viewer_csrf),
        json={"hazard_type": "RAINSTORM", "city_code": ""},
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "SUBSCRIPTION_EXISTS"


def test_unknown_subscription_scope_rejected(subscriber):
    viewer, viewer_csrf = subscriber

    bad_hazard = viewer.post(
        "/api/v1/subscriptions",
        headers=csrf_headers(viewer_csrf),
        json={"hazard_type": "METEOR_STRIKE", "city_code": ""},
    )
    assert bad_hazard.status_code == 422
    assert bad_hazard.json()["error"]["code"] == "VALIDATION_ERROR"

    bad_city = viewer.post(
        "/api/v1/subscriptions",
        headers=csrf_headers(viewer_csrf),
        json={"hazard_type": "RAINSTORM", "city_code": "ATLANTIS"},
    )
    assert bad_city.status_code == 422


def test_notifications_are_per_user(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-scope")

    items = _notifications_for(viewer, public_id)
    assert len(items) == 1

    # 分析员没有订阅，看不到这条通知
    assert _notifications_for(analyst, public_id) == []

    # 也不能标记别人的通知
    read = analyst.post(
        f"/api/v1/notifications/{items[0]['id']}/read", headers=csrf_headers(analyst_csrf)
    )
    assert read.status_code == 404
    assert read.json()["error"]["code"] == "NOT_FOUND"


def test_mark_read_and_unread_count(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = _publish(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-read")

    # 临时账号从零开始，未读数就是这条预警产生的通知数
    before = viewer.get("/api/v1/notifications/unread-count").json()["count"]
    assert before == 1

    notification_id = _notifications_for(viewer, public_id)[0]["id"]
    assert viewer.post(
        f"/api/v1/notifications/{notification_id}/read", headers=csrf_headers(viewer_csrf)
    ).status_code == 200
    assert viewer.get("/api/v1/notifications/unread-count").json()["count"] == 0

    # 已读的通知仍在列表里，只是 read_at 有值
    assert _notifications_for(viewer, public_id)[0]["read_at"] is not None

    assert viewer.post(
        "/api/v1/notifications/read-all", headers=csrf_headers(viewer_csrf)
    ).status_code == 200
    assert viewer.get("/api/v1/notifications/unread-count").json()["count"] == 0
