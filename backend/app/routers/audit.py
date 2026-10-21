from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ROLE_ADMIN, require_roles
from ..models import AuditLog
from ..schemas import AuditOut

router = APIRouter()


@router.get("/audit-logs", response_model=list[AuditOut])
def audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_ADMIN)),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return [
        AuditOut(
            id=r.id,
            actor_id=r.actor_id,
            actor_role=r.actor_role,
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            result=r.result,
            reason=r.reason,
            ip_address=r.ip_address,
            created_at=r.created_at,
        )
        for r in rows
    ]
