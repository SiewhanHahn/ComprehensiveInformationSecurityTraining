from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import CurrentUser, client_ip, get_current_user, get_session_id, request_id
from ..models import User
from ..schemas import AuthResponse, AuthUser, LoginRequest, MeResponse
from ..security import hash_password, new_csrf_token, new_session_id, verify_password
from ..services.audit import add_audit
from ..session import create_session, delete_session

router = APIRouter()
settings = get_settings()


@lru_cache
def _dummy_password_hash() -> str:
    # 未知用户也做一次等价 Argon2 校验，抹平登录时序差异（防用户名枚举）
    return hash_password("dummy-timing-equalizer")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _audit(db: Session, request: Request, action: str, result: str, actor_id=None, actor_role=None, reason=None):
    # 注意：本函数内部会 commit，调用处不要在同一逻辑分支里再手动 commit（避免两次提交）
    add_audit(
        db,
        action=action,
        resource_type="auth",
        result=result,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        request_id=request_id(request),
        ip_address=client_ip(request),
    )
    db.commit()


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None:
        verify_password(body.password, _dummy_password_hash())
        _audit(db, request, "LOGIN_FAILED", "DENIED", reason="unknown user")
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")

    if user.locked_until is not None and user.locked_until > _now():
        _audit(db, request, "LOGIN_FAILED", "DENIED", actor_id=user.id, reason="locked")
        raise HTTPException(status_code=401, detail="ACCOUNT_LOCKED")

    if not user.is_active:
        _audit(db, request, "LOGIN_FAILED", "DENIED", actor_id=user.id, reason="disabled")
        raise HTTPException(status_code=401, detail="ACCOUNT_DISABLED")

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_login_attempts:
            user.locked_until = _now() + timedelta(seconds=settings.lockout_seconds)
            user.failed_login_count = 0
        db.commit()
        _audit(db, request, "LOGIN_FAILED", "DENIED", actor_id=user.id, reason="bad password")
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")

    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    roles = [r.code for r in user.roles]
    session_id = new_session_id()
    csrf_token = new_csrf_token()
    create_session(session_id, user.id, roles, csrf_token)
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    # 供前端 JS 读取的 CSRF token（非 HttpOnly），刷新页面后仍可回退恢复
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    _audit(db, request, "LOGIN_SUCCESS", "SUCCESS", actor_id=user.id, actor_role=",".join(roles))

    return AuthResponse(
        user=AuthUser(id=user.id, username=user.username, display_name=user.display_name, roles=roles),
        csrf_token=csrf_token,
    )


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    session_id = get_session_id(request)
    if session_id:
        delete_session(session_id)
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
    )
    response.delete_cookie(
        settings.csrf_cookie_name,
        path="/",
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
    )
    _audit(db, request, "LOGOUT", "SUCCESS", actor_id=current.id, actor_role=",".join(current.roles))
    return {"status": "ok"}


@router.get("/auth/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.id == current.id))
    if user is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    return MeResponse(
        user=AuthUser(id=current.id, username=current.username, display_name=user.display_name, roles=current.roles)
    )
