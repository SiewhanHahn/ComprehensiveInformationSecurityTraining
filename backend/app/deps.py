from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User
from .session import read_session, touch_session

settings = get_settings()

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
    return request.cookies.get(settings.session_cookie_name)


def client_ip(request: Request) -> str | None:
    # nginx 反代下取 X-Forwarded-For 首跳（真实客户端）；无则回退 X-Real-IP / 直连地址
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else None


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
    user_id = payload.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    roles = [r.code for r in user.roles]
    touch_session(session_id)
    return CurrentUser(id=user.id, username=user.username, roles=roles)


def require_roles(*roles: str):
    def dependency(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(current.has_role(r) for r in roles):
            raise HTTPException(status_code=403, detail="FORBIDDEN")
        return current

    return dependency
