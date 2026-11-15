from datetime import timedelta
from functools import lru_cache
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..clock import utcnow
from ..config import get_settings
from ..db import get_db, get_redis
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


def _ip_rate_key(ip: str) -> str:
    return f"login:fail:{ip}"


def _ip_rate_limited(ip: str | None) -> bool:
    """按来源 IP 的失败计数是否已达阈值。只读，不递增。"""
    if not ip:
        return False
    redis = get_redis()
    key = _ip_rate_key(ip)
    count = redis.get(key)
    if count is None:
        return False
    limited = int(count) >= get_settings().ip_login_attempts
    if limited:
        # 429 分支不会再走 _record_ip_failure；旧版本留下的无 TTL 键会因此永久锁死
        # 该 IP。返回 429 前先补一次过期时间（已有 TTL 时 NX 不会重设）。
        redis.expire(key, get_settings().ip_lockout_seconds, nx=True)
    return limited


def _record_ip_failure(ip: str | None) -> None:
    """登录失败时递增来源 IP 的失败计数，防止对已知账号的锁号与爆破。

    ``SET NX EX`` 保证键一旦创建就带固定窗口的过期时间：不会出现「自增成功但没设过期」
    的永久键，也不会因为持续失败把窗口一直往后推（滑动窗口会让该 IP 永远出不来）。
    再补一次 ``EXPIRE NX``：旧版本可能留下过没有 TTL 的键，那些键不会因为 NX 而重设。
    """
    if not ip:
        return
    redis = get_redis()
    key = _ip_rate_key(ip)
    ttl = get_settings().ip_lockout_seconds
    redis.set(key, 0, ex=ttl, nx=True)
    redis.incr(key)
    redis.expire(key, ttl, nx=True)  # 自愈：已存在但没有过期时间的键在这里补上


def _set_cookies(response: Response, session_id: str, csrf_token: str) -> None:
    settings = get_settings()
    # 会话 Cookie 不设 max_age（浏览器会话级）；服务端由 Redis 空闲 TTL + 绝对 TTL 控制
    common = dict(samesite=settings.cookie_samesite, secure=settings.cookie_secure, path="/")
    response.set_cookie(settings.session_cookie_name, session_id, httponly=True, **common)
    # 供前端 JS 读取的 CSRF token（非 HttpOnly），刷新页面后仍可回退恢复
    response.set_cookie(settings.csrf_cookie_name, csrf_token, httponly=False, **common)


def _clear_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", samesite=settings.cookie_samesite, secure=settings.cookie_secure)


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if _ip_rate_limited(ip):
        raise HTTPException(status_code=429, detail="LOGIN_RATE_LIMITED")

    settings = get_settings()
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None:
        verify_password(body.password, _dummy_password_hash())
        _record_ip_failure(ip)
        _deny(db, request, "INVALID_CREDENTIALS", "unknown user")

    # 已存在用户一律先校验密码，抹平锁定/停用/错误密码之间的时序差异，也不泄露账号状态
    if not verify_password(body.password, user.password_hash):
        # 原子自增：读改写会让并发的失败请求互相覆盖，账号锁定阈值可被并发绕过
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(failed_login_count=User.failed_login_count + 1)
            .execution_options(synchronize_session=False)
        )
        db.flush()
        # 用加锁读拿最新计数：db.refresh 在 REPEATABLE READ 下是快照读，
        # 看不到并发失败请求已提交的累加值，突发请求就会各自看到 1 而没有一个人触发锁定
        current_count = db.execute(
            select(User.failed_login_count).where(User.id == user.id).with_for_update()
        ).scalar_one()
        user.failed_login_count = current_count
        if current_count >= settings.max_login_attempts:
            user.locked_until = utcnow() + timedelta(seconds=settings.lockout_seconds)
            user.failed_login_count = 0
        _record_ip_failure(ip)
        _deny(db, request, "INVALID_CREDENTIALS", "bad password", actor_id=user.id)

    # 密码正确后才区分状态：锁定仍返回统一失败；停用才单独提示（密码已证明本人）。
    # 这里必须用加锁读拿最新状态：前面的普通 SELECT 在 REPEATABLE READ 下是快照，
    # 并发请求刚提交的锁定/停用看不到；成功分支还会把 locked_until 清空。
    # 锁会一直持有到本次 commit，避免读完之后又被并发锁定。
    locked_until, is_active = db.execute(
        select(User.locked_until, User.is_active).where(User.id == user.id).with_for_update()
    ).one()
    user.locked_until = locked_until
    user.is_active = is_active
    if locked_until is not None and locked_until > utcnow():
        _deny(db, request, "INVALID_CREDENTIALS", "locked", actor_id=user.id)
    if not is_active:
        _deny(db, request, "ACCOUNT_DISABLED", "disabled", actor_id=user.id)

    user.failed_login_count = 0
    user.locked_until = None
    roles = [r.code for r in user.roles]
    session_id = new_session_id()
    csrf_token = new_csrf_token()
    create_session(session_id, user.id, roles, csrf_token)
    _audit(db, request, "LOGIN_SUCCESS", "SUCCESS", actor_id=user.id, actor_role=",".join(roles))
    db.commit()
    # 不清空 IP 失败计数：只要持有一个有效账号，就能在每轮猜测之间登录一次把自己的
    # 额度重置掉，per-IP 限速等于失效。账号级计数仍然在成功时清零，正常用户不受影响；
    # IP 计数按 ip_lockout_seconds 窗口自然过期。

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
