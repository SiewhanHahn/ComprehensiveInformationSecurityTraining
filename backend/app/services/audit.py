from sqlalchemy.orm import Session

from ..models import AuditLog


def add_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    result: str,
    actor_id: int | None = None,
    actor_role: str | None = None,
    resource_id: str | None = None,
    reason: str | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            reason=reason,
            request_id=request_id,
            ip_address=ip_address,
        )
    )
