"""站内通知：发布/撤回投递、通知中心查询与扫描补投。

写操作只 ``flush``，由调用方 ``commit``，保证预警状态变更、通知与审计同事务。
``dedupe_key`` 唯一索引保证同一 (预警, 用户, 种类) 只产生一条通知，
定时扫描重复执行不会重复打扰。
"""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..cities import ALL_CITIES, CITIES
from ..clock import utcnow
from ..hazards import HAZARDS
from ..models import Notification, Warning
from .subscriptions import subscriber_ids

NOTIFY_PUBLISHED = "WARNING_PUBLISHED"
NOTIFY_WITHDRAWN = "WARNING_WITHDRAWN"

NOTIFICATION_TITLES = {
    NOTIFY_PUBLISHED: "预警发布",
    NOTIFY_WITHDRAWN: "预警撤回",
}

HAZARD_NAMES = {h["code"]: h["name"] for h in HAZARDS}

# ``services.warnings.PUBLISHED``；此处写字面量避免 warnings ↔ notifications 循环导入
_PUBLISHED = "PUBLISHED"


def dedupe_key(kind: str, public_id: str, user_id: int) -> str:
    return f"{kind.lower()}:{public_id}:{user_id}"


def _summary(w: Warning) -> str:
    result = w.warning_result
    if result is None:
        return w.title
    city = CITIES.get(result.city_code, result.city_code)
    hazard = HAZARD_NAMES.get(w.hazard_type, w.hazard_type)
    return f"{city} {result.valid_date} {hazard}；四模式融合 {float(result.fused_mm):.1f}mm"


def notify_warning(db: Session, w: Warning, kind: str) -> int:
    """给匹配订阅的用户投递通知；已投递过的跳过，返回新增条数。"""
    result = w.warning_result
    city_code = result.city_code if result is not None else ALL_CITIES
    user_ids = subscriber_ids(db, w.hazard_type, city_code)
    if not user_ids:
        return 0

    keys = {dedupe_key(kind, w.public_id, uid): uid for uid in user_ids}
    delivered = set(db.scalars(select(Notification.dedupe_key).where(Notification.dedupe_key.in_(keys))).all())
    title = f"{NOTIFICATION_TITLES[kind]}：{w.title}"[:200]
    body = _summary(w)[:1000]

    created = 0
    for key, user_id in keys.items():
        if key in delivered:
            continue
        db.add(
            Notification(
                user_id=user_id,
                kind=kind,
                title=title,
                body=body,
                resource_type="warning",
                resource_id=w.public_id,
                dedupe_key=key,
            )
        )
        created += 1
    db.flush()
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
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    ).all()
    now = utcnow()
    for n in rows:
        n.read_at = now
    db.flush()
    return len(rows)


def backfill_published(db: Session, *, hours: int, now: datetime) -> int:
    """补投：最近 ``hours`` 小时内已发布、但订阅者还没收到通知的预警。

    订阅发生在发布之后时也能收到；重复执行不会重复投递（``dedupe_key``）。
    """
    since = now - timedelta(hours=hours)
    warnings = db.scalars(
        select(Warning).where(Warning.status == _PUBLISHED, Warning.published_at >= since)
    ).all()
    return sum(notify_warning(db, w, NOTIFY_PUBLISHED) for w in warnings)
