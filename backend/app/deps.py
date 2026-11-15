import ipaddress
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User
from .session import delete_session, read_session, session_expired, touch_session

ROLE_ADMIN = "ADMIN"
ROLE_ANALYST = "ANALYST"
ROLE_REVIEWER = "REVIEWER"
ROLE_VIEWER = "VIEWER"


@dataclass
class CurrentUser:
    id: int
    username: str
    roles: list[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles


def get_session_id(request: Request) -> str | None:
    return request.cookies.get(get_settings().session_cookie_name)


def _parse_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    candidate = raw.strip()
    if len(candidate) > 45:
        return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def client_ip(request: Request) -> str | None:
    # 只信任 nginx 覆盖写入的 X-Real-IP（= $remote_addr）；X-Forwarded-For 首跳可被客户端伪造。
    # 头格式不合法或超长时回退到连接对端地址，防止伪造限速键或写爆 audit_logs.ip_address。
    if get_settings().trust_proxy_headers:
        valid = _parse_ip(request.headers.get("x-real-ip"))
        if valid is not None:
            return valid
    host = request.client.host if request.client else None
    return host[:45] if host else None


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> CurrentUser:
    session_id = get_session_id(request)
    if session_id is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    payload = read_session(session_id)
    if payload is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    if session_expired(payload):
        delete_session(session_id)
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    user_id = payload.get("user_id")
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    roles = sorted(r.code for r in user.roles)
    touch_session(session_id)
    return CurrentUser(id=user.id, username=user.username, roles=roles)


def require_roles(*roles: str):
    def dependency(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(current.has_role(r) for r in roles):
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        return current

    return dependency
