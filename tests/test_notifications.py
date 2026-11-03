"""订阅与站内通知（RUN_INTEGRATION=1，并注入 DEMO_*_PASSWORD）。

订阅者用 ``subscriber`` 夹具创建的临时账号，不依赖演示账号的历史订阅；
通知按 ``resource_id``（预警 public_id）挂在预警上，随预警一并删除。
"""

import pytest

from conftest import csrf_headers, notifications_for, publish_warning

pytestmark = pytest.mark.integration


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


def _unread_ids(client) -> set[int]:
    resp = client.get("/api/v1/notifications", params={"unread_only": "true", "page_size": 100})
    assert resp.status_code == 200, resp.text
    return {n["id"] for n in resp.json()["items"]}


def test_publish_notifies_matching_subscriber(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-match")

    items = notifications_for(viewer, public_id)
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
    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-skip")

    assert notifications_for(viewer, public_id) == []


def test_withdraw_notifies_subscribers(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-withdraw")

    withdraw = reviewer.post(f"/api/v1/warnings/{public_id}/withdraw", headers=csrf_headers(reviewer_csrf))
    assert withdraw.status_code == 200, withdraw.text

    kinds = sorted(n["kind"] for n in notifications_for(viewer, public_id))
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
    assert bad_city.json()["error"]["code"] == "VALIDATION_ERROR"


def test_notifications_are_per_user(login, subscriber, bystander, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber
    other, other_csrf = bystander

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-scope")

    items = notifications_for(viewer, public_id)
    assert len(items) == 1

    # 另一个没有订阅的临时账号看不到这条通知（用临时账号而不是演示账号，避免历史订阅干扰）
    assert notifications_for(other, public_id) == []

    # 也不能标记别人的通知
    read = other.post(
        f"/api/v1/notifications/{items[0]['id']}/read", headers=csrf_headers(other_csrf)
    )
    assert read.status_code == 404
    assert read.json()["error"]["code"] == "NOT_FOUND"


def test_mark_read_and_unread_count(login, subscriber, make_warning, created_subscriptions):
    analyst, analyst_csrf = login("analyst_demo")
    reviewer, reviewer_csrf = login("reviewer_demo")
    viewer, viewer_csrf = subscriber

    _subscribe(viewer, viewer_csrf, created_subscriptions)
    public_id = publish_warning(analyst, analyst_csrf, reviewer, reviewer_csrf, make_warning, "notify-read")

    # 只断言「这一条」的已读状态与未读集合，不用绝对未读数：
    # 同一账号若被定时扫描补投了别的通知，绝对计数会变，但这条的归属不会变。
    notification_id = notifications_for(viewer, public_id)[0]["id"]
    assert notification_id in _unread_ids(viewer)
    assert viewer.get("/api/v1/notifications/unread-count").json()["count"] >= 1

    assert viewer.post(
        f"/api/v1/notifications/{notification_id}/read", headers=csrf_headers(viewer_csrf)
    ).status_code == 200
    assert notification_id not in _unread_ids(viewer)

    # 已读的通知仍在列表里，只是 read_at 有值
    assert notifications_for(viewer, public_id)[0]["read_at"] is not None

    assert viewer.post(
        "/api/v1/notifications/read-all", headers=csrf_headers(viewer_csrf)
    ).status_code == 200
    assert viewer.get("/api/v1/notifications/unread-count").json()["count"] == 0
