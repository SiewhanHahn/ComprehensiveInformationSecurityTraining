"""站内通知：发布/撤回投递、通知中心查询与扫描补投。

写操作只 ``flush``，由调用方 ``commit``，保证预警状态变更、通知与审计同事务。
``dedupe_key`` 唯一索引保证同一 (预警, 用户, 种类) 只产生一条通知，
定时扫描重复执行不会重复打扰。
"""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from ..cities import ALL_CITIES, WARNING_CITIES
from ..clock import utcnow
from ..hazards import HAZARDS
from ..models import Notification, Warning
from .subscriptions import active_subscriptions, match_subscriptions, subscriber_ids

NOTIFY_PUBLISHED = "WARNING_PUBLISHED"
NOTIFY_WITHDRAWN = "WARNING_WITHDRAWN"

NOTIFICATION_TITLES = {
    NOTIFY_PUBLISHED: "预警发布",
    NOTIFY_WITHDRAWN: "预警撤回",
}

HAZARD_NAMES = {h["code"]: h["name"] for h in HAZARDS}


def dedupe_key(kind: str, public_id: str, user_id: int) -> str:
    return f"{kind.lower()}:{public_id}:{user_id}"


def warning_summary(w: Warning) -> str:
    result = w.warning_result
    if result is None:
        return w.title
    city = WARNING_CITIES.get(result.city_code, result.city_code)
    hazard = HAZARD_NAMES.get(w.hazard_type, w.hazard_type)
    if result.assessment_json is not None:
        metric = result.assessment_json["metric"]
        precision = 2 if metric["unit"] == "cm" else 1
        return f"{city} {result.valid_date} {hazard}教学演练；{metric['label']} {metric['value']:.{precision}f} {metric['unit']}"
    return f"{city} {result.valid_date} {hazard}；四模式融合 {float(result.fused_mm):.1f}mm"


def notify_users(
    db: Session,
    *,
    user_ids: list[int],
    kind: str,
    title: str,
    body: str,
    resource_type: str,
    resource_id: str,
) -> int:
    """按 ``dedupe_key`` 去重后批量投递，返回新增条数。只 flush，由调用方 commit。

    用 ``INSERT IGNORE`` 而不是「先查再逐条插入」：两个生产者（scheduler 与 API、
    或滚动重启期间的两个 scheduler）可能同时给同一条预警投递，双方都查不到对方尚未
    提交的行，后提交者会撞 ``uq_notifications_dedupe``。那样抛出的 ``IntegrityError``
    会把调用方的整个业务事务——预警状态、响应任务、审计——一起回滚。
    ``INSERT IGNORE`` 让撞键的那条静默跳过，其余照常写入。
    """
    if not user_ids:
        return 0

    keys = {dedupe_key(kind, resource_id, uid): uid for uid in user_ids}
    delivered = set(db.scalars(select(Notification.dedupe_key).where(Notification.dedupe_key.in_(keys))).all())

    rows = [
        {
            "user_id": user_id,
            "kind": kind,
            "title": title[:200],
            "body": body[:1000],
            "resource_type": resource_type,
            "resource_id": resource_id,
            "dedupe_key": key,
        }
        for key, user_id in keys.items()
        if key not in delivered
    ]
    if not rows:
        return 0
    # rowcount 是真正插入的行数（被 IGNORE 掉的冲突行不计），与「新增条数」语义一致
    result = db.execute(insert(Notification).values(rows).prefix_with("IGNORE"))
    return int(result.rowcount or 0)


def notify_warning(db: Session, w: Warning, kind: str, *, user_ids: list[int] | None = None) -> int:
    """向同一批收件人按业务顺序投递至指定事件；返回本次实际新增的通知数。"""
    if user_ids is None:
        result = w.warning_result
        city_code = result.city_code if result is not None else ALL_CITIES
        user_ids = subscriber_ids(db, w.hazard_type, city_code)
    # 晚订阅者可能尚未收到发布；撤回与扫描都应先补齐发布，再投撤回。
    kinds = (NOTIFY_PUBLISHED, NOTIFY_WITHDRAWN) if kind == NOTIFY_WITHDRAWN else (kind,)
    body = warning_summary(w)
    created = 0
    for event in kinds:
        prefix = f"{NOTIFICATION_TITLES[event]}："
        created += notify_users(
            db,
            user_ids=user_ids,
            kind=event,
            title=prefix + w.title[: 200 - len(prefix)],
            body=body,
            resource_type="warning",
            resource_id=w.public_id,
        )
    return created


# ---- 通知中心 ----


def list_notifications(
    db: Session, user_id: int, *, unread_only: bool, page: int, page_size: int
) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Notification.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(rows), total


def unread_count(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
        or 0
    )


def mark_read(db: Session, user_id: int, notification_id: int) -> None:
    """只能标记自己的通知；别人的通知一律表现为不存在。"""
    n = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    )
    if n is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if n.read_at is None:
        n.read_at = utcnow()
        db.flush()


def mark_all_read(db: Session, user_id: int) -> int:
    """一条 UPDATE 搞定；逐行读进 ORM 再逐行更新的话，积压越多越慢。"""
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.flush()
    return result.rowcount or 0


def backfill_published(db: Session, *, hours: int, now: datetime) -> int:
    """补投：最近 ``hours`` 小时内发布过、但订阅者还没收到通知的预警。

    按 ``published_at``（发布事件）取数而不是当前状态：预警在两次扫描之间被撤回时，
    仍然按顺序补上「发布」和「撤回」两条，避免订阅者收到一条自己从没见过的撤回通知。
    重复执行不会重复投递（``dedupe_key``）。
    """
    since = now - timedelta(hours=hours)
    warnings = db.scalars(select(Warning).where(Warning.published_at >= since)).all()
    if not warnings:
        return 0
    subs = active_subscriptions(db)
    created = 0
    for w in warnings:
        result = w.warning_result
        city_code = result.city_code if result is not None else ALL_CITIES
        user_ids = match_subscriptions(subs, w.hazard_type, city_code)
        kind = NOTIFY_WITHDRAWN if w.withdrawn_at is not None else NOTIFY_PUBLISHED
        created += notify_warning(db, w, kind, user_ids=user_ids)
    return created
