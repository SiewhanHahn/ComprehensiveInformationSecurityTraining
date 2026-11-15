"""预警订阅：按灾种与城市筛选站内通知的收件人。

「不限」用哨兵值表达（``hazards.ALL_HAZARDS`` / ``cities.ALL_CITIES``），不用 NULL——
MySQL 唯一索引不把 NULL 视为相等，用 NULL 会让同一人重复插入同样的订阅。
写操作只 ``flush``，由调用方 ``commit``。
"""

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..cities import ALL_CITIES
from ..hazards import ALL_HAZARDS
from ..models import User, WarningSubscription
from ..schemas import SubscriptionCreate


def matches(sub: WarningSubscription, hazard_type: str, city_code: str) -> bool:
    """订阅是否覆盖这条预警：两个维度各自「不限」或精确相等。"""
    hazard_ok = sub.hazard_type == ALL_HAZARDS or sub.hazard_type == hazard_type
    city_ok = sub.city_code == ALL_CITIES or sub.city_code == city_code
    return hazard_ok and city_ok


def _all_subscriptions(db: Session) -> list[WarningSubscription]:
    # 已停用账号读不到任何接口，不必再给他堆通知
    stmt = (
        select(WarningSubscription)
        .join(User, User.id == WarningSubscription.user_id)
        .where(User.is_active.is_(True))
    )
    return list(db.scalars(stmt).all())


def subscriber_ids(db: Session, hazard_type: str, city_code: str) -> list[int]:
    """匹配该预警的订阅者。订阅与用户数量都很小，在内存里比对即可，保持匹配逻辑只有一处实现。"""
    return sorted({sub.user_id for sub in _all_subscriptions(db) if matches(sub, hazard_type, city_code)})


def list_subscriptions(db: Session, user_id: int) -> list[WarningSubscription]:
    stmt = (
        select(WarningSubscription)
        .where(WarningSubscription.user_id == user_id)
        .order_by(WarningSubscription.id)
    )
    return list(db.scalars(stmt).all())


def create_subscription(db: Session, user_id: int, body: SubscriptionCreate) -> WarningSubscription:
    existing = db.scalar(
        select(WarningSubscription).where(
            WarningSubscription.user_id == user_id,
            WarningSubscription.hazard_type == body.hazard_type,
            WarningSubscription.city_code == body.city_code,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="SUBSCRIPTION_EXISTS")
    sub = WarningSubscription(user_id=user_id, hazard_type=body.hazard_type, city_code=body.city_code)
    try:
        # db.add 也必须放在 SAVEPOINT 作用域内：如果在外层事务先 add 再进 begin_nested()，
        # SQLAlchemy 在 1062 回滚时会连带把外层 SessionTransaction 置为 DEACTIVE。
        with db.begin_nested():
            db.add(sub)
            db.flush()
    except IntegrityError as exc:
        # 预检查与唯一索引之间的并发窗口：与 routers/users.py 的 1062 处理一致，翻译成 409
        if getattr(exc.orig, "args", (None,))[0] == 1062:
            raise HTTPException(status_code=409, detail="SUBSCRIPTION_EXISTS") from exc
        raise
    return sub


def delete_subscription(db: Session, user_id: int, subscription_id: int) -> None:
    """只能删自己的订阅；别人的订阅或并发已删除一律表现为不存在。"""
    result = db.execute(
        delete(WarningSubscription).where(
            WarningSubscription.id == subscription_id,
            WarningSubscription.user_id == user_id,
        )
    )
    db.flush()
    if (result.rowcount or 0) == 0:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
