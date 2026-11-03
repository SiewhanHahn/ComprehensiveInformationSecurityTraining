"""通知与订阅接口：参数、鉴权与序列化；业务规则见 ``services/notifications.py``
与 ``services/subscriptions.py``。

所有端点都按当前用户收敛，查看者同样可以订阅和接收通知。
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, get_current_user
from ..models import Notification, WarningSubscription
from ..schemas import NotificationOut, NotificationPage, SubscriptionCreate, SubscriptionOut
from ..services import notifications as notif_svc
from ..services import subscriptions as sub_svc
from ..services.audit import audit_context

router = APIRouter()


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        kind=n.kind,
        title=n.title,
        body=n.body,
        resource_type=n.resource_type,
        resource_id=n.resource_id,
        read_at=n.read_at,
        created_at=n.created_at,
    )


def _to_sub_out(s: WarningSubscription) -> SubscriptionOut:
    return SubscriptionOut(
        id=s.id, hazard_type=s.hazard_type, city_code=s.city_code, created_at=s.created_at
    )


# ---- 通知 ----


@router.get("/notifications", response_model=NotificationPage)
def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    rows, total = notif_svc.list_notifications(
        db, current.id, unread_only=unread_only, page=page, page_size=page_size
    )
    return NotificationPage(
        items=[_to_out(n) for n in rows], total=total, page=page, page_size=page_size
    )


@router.get("/notifications/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, int]:
    return {"count": notif_svc.unread_count(db, current.id)}


@router.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    notif_svc.mark_read(db, current.id, notification_id)
    db.commit()
    return {"read": True}


@router.post("/notifications/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, int]:
    updated = notif_svc.mark_all_read(db, current.id)
    db.commit()
    return {"updated": updated}


# ---- 订阅 ----


@router.get("/subscriptions", response_model=list[SubscriptionOut])
def list_subscriptions(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    return [_to_sub_out(s) for s in sub_svc.list_subscriptions(db, current.id)]


@router.post("/subscriptions", response_model=SubscriptionOut)
def create_subscription(
    body: SubscriptionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    sub = sub_svc.create_subscription(db, current.id, body)
    audit_context(request, db, current).record("SUBSCRIPTION_CREATE", resource_type="subscription", resource_id=str(sub.id))
    db.commit()
    return _to_sub_out(sub)


@router.delete("/subscriptions/{subscription_id}", status_code=204, response_class=Response)
def delete_subscription(
    subscription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    sub_svc.delete_subscription(db, current.id, subscription_id)
    audit_context(request, db, current).record("SUBSCRIPTION_DELETE", resource_type="subscription", resource_id=str(subscription_id))
    db.commit()
    return Response(status_code=204)
