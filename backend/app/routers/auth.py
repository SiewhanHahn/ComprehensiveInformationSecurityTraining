from datetime import timedelta
from functools import lru_cache
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import utcnow
from ..config import get_settings
from ..db import get_db
from ..deps import CurrentUser, client_ip, get_current_user, get_session_id, request_id
from ..models import User
from ..schemas import AuthResponse, AuthUser, LoginRequest, MeResponse
from ..security import hash_password, new_csrf_token, new_session_id, verify_password
from ..services.audit import add_audit
from ..session import create_session, delete_session

router = APIRouter()


@lru_cache
def _dummy_password_hash() -> str:
    # 未知用户也做一次等价 Argon2 校验，抹平登录时序差异（防用户名枚举）
    return hash_password("dummy-timing-equalizer")


def _audit(db: Session, request: Request, action: str, result: str, actor_id=None, actor_role=None, reason=None):
    # 只追加，不提交；各分支末尾统一 commit，使账号状态变更与审计同事务
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


def _deny(db: Session, request: Request, code: str, reason: str, actor_id: int | None = None) -> NoReturn:
    # 失败也要留痕：连同失败计数/锁定状态一起提交后再拒绝
    _audit(db, request, "LOGIN_FAILED", "DENIED", actor_id=actor_id, reason=reason)
    db.commit()
    raise HTTPException(status_code=401, detail=code)


def _set_cookies(response: Response, session_id: str, csrf_token: str) -> None:
    settings = get_settings()
    common = dict(
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    response.set_cookie(settings.session_cookie_name, session_id, httponly=True, **common)
    # 供前端 JS 读取的 CSRF token（非 HttpOnly），刷新页面后仍可回退恢复
    response.set_cookie(settings.csrf_cookie_name, csrf_token, httponly=False, **common)


def _clear_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", samesite=settings.cookie_samesite, secure=settings.cookie_secure)


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None:
        verify_password(body.password, _dummy_password_hash())
        _deny(db, request, "INVALID_CREDENTIALS", "unknown user")

    if user.locked_until is not None and user.locked_until > utcnow():
        _deny(db, request, "ACCOUNT_LOCKED", "locked", actor_id=user.id)

    if not user.is_active:
        _deny(db, request, "ACCOUNT_DISABLED", "disabled", actor_id=user.id)

    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_login_attempts:
            user.locked_until = utcnow() + timedelta(seconds=settings.lockout_seconds)
            user.failed_login_count = 0
        _deny(db, request, "INVALID_CREDENTIALS", "bad password", actor_id=user.id)

    user.failed_login_count = 0
    user.locked_until = None
    roles = [r.code for r in user.roles]
    session_id = new_session_id()
    csrf_token = new_csrf_token()
    create_session(session_id, user.id, roles, csrf_token)
    _audit(db, request, "LOGIN_SUCCESS", "SUCCESS", actor_id=user.id, actor_role=",".join(roles))
    db.commit()

    _set_cookies(response, session_id, csrf_token)
    return AuthResponse(
        user=AuthUser(id=user.id, username=user.username, display_name=user.display_name, roles=roles),
        csrf_token=csrf_token,
    )


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)):
    session_id = get_session_id(request)
    if session_id:
        delete_session(session_id)
    _clear_cookies(response)
    _audit(db, request, "LOGOUT", "SUCCESS", actor_id=current.id, actor_role=",".join(current.roles))
    db.commit()
    return {"status": "ok"}


@router.get("/auth/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.id == current.id))
    if user is None:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    return MeResponse(
        user=AuthUser(id=current.id, username=current.username, display_name=user.display_name, roles=current.roles)
    )
