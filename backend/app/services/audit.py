from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from ..deps import CurrentUser, client_ip, request_id
from ..models import AuditLog


def _clip(value: str | None, width: int) -> str | None:
    if value is None:
        return None
    return value[:width]


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
    resource_version: int | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """追加一条审计记录；只 add 不 commit，与业务写入同事务提交。"""
    db.add(
        AuditLog(
            actor_id=actor_id,
            actor_role=_clip(actor_role, 32),
            action=_clip(action, 64),
            resource_type=_clip(resource_type, 64),
            resource_id=_clip(resource_id, 64),
            result=_clip(result, 16),
            reason=_clip(reason, 500),
            resource_version=resource_version,
            request_id=_clip(request_id, 36),
            ip_address=_clip(ip_address, 45),
        )
    )


@dataclass
class AuditContext:
    """绑定当前请求与操作者的审计写入器，避免每个端点重复传 IP/请求号/角色。"""

    db: Session
    actor: CurrentUser | None
    request_id: str | None
    ip_address: str | None

    def record(
        self,
        action: str,
        *,
        resource_type: str,
        resource_id: str | None = None,
        result: str = "SUCCESS",
        reason: str | None = None,
        resource_version: int | None = None,
        actor_role: str | None = None,
    ) -> None:
        add_audit(
            self.db,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            reason=reason,
            resource_version=resource_version,
            actor_id=self.actor.id if self.actor else None,
            actor_role=actor_role or (",".join(sorted(self.actor.roles)) if self.actor else None),
            request_id=self.request_id,
            ip_address=self.ip_address,
        )


def audit_context(request: Request, db: Session, actor: CurrentUser | None) -> AuditContext:
    return AuditContext(db=db, actor=actor, request_id=request_id(request), ip_address=client_ip(request))
