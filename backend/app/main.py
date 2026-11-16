import logging
import re
import secrets
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .db import check_database, get_redis
from .errors import code_for, error_response
from .routers import audit, auth, hazards, metrics, monitor, notifications, replay, tasks, users, warnings
from .session import delete_session, read_session, session_expired

settings = get_settings()
settings.validate_for_serving()
logger = logging.getLogger("backend.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    auth._dummy_password_hash()
    yield


app = FastAPI(
    title="气象灾害预测与预警系统",
    version="0.1.0",
    description="教学演示用气象预警系统 API",
    lifespan=lifespan,
)

app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(replay.router, prefix="/api/v1", tags=["replay"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(warnings.router, prefix="/api/v1", tags=["warnings"])
app.include_router(audit.router, prefix="/api/v1", tags=["audit"])
app.include_router(hazards.router, prefix="/api/v1", tags=["hazards"])
app.include_router(monitor.router, prefix="/api/v1", tags=["monitor"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])


_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,36}$")


def csrf_matches(token: str | None, expected: str | None) -> bool:
    """常量时间比较 CSRF token。

    按字节比较：``compare_digest`` 遇到含非 ASCII 的 str 会抛 TypeError，
    那样请求得到的会是 500 而不是 403。
    """
    if not token or not expected:
        return False
    return secrets.compare_digest(
        token.encode("utf-8", "surrogateescape"), expected.encode("utf-8", "surrogateescape")
    )


# Starlette 中后注册的中间件在外层：CSRF 先注册，请求号中间件后注册，
# 保证 CSRF 拒绝的响应同样带 request_id / X-Request-ID。
@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)
    if request.method == "POST" and request.url.path == "/api/v1/auth/login":
        return await call_next(request)

    token = request.headers.get("x-csrf-token")
    session_id = request.cookies.get(settings.session_cookie_name)
    # 没有会话 Cookie 时不要报 CSRF：请求会由 get_current_user 返回 401。
    # 否则未登录的写请求会被误报成「CSRF 校验失败」，前端无法据此回到登录页。
    if not session_id:
        return await call_next(request)
    try:
        payload = read_session(session_id)
    except Exception:
        return error_response(request, 503, "DEPENDENCY_UNAVAILABLE")
    # 有 Cookie 但 Redis 会话已过期/绝对超时/已登出：这是未认证，不是 CSRF 失败。
    if payload is None:
        return error_response(request, 401, "UNAUTHENTICATED")
    if session_expired(payload):
        try:
            delete_session(session_id)
        except Exception:
            pass
        return error_response(request, 401, "UNAUTHENTICATED")
    if not csrf_matches(token, payload.get("csrf_token")):
        return error_response(request, 403, "CSRF")
    return await call_next(request)


if settings.cors_origin_list:
    # CORSMiddleware 在 csrf_middleware 之后、request_id_middleware 之前注册，
    # 在洋葱栈中包裹 csrf_middleware，使 401/403 拒绝响应也能带出 CORS 与 X-Request-ID 头。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    # 只接受格式合规的上游请求号（写入审计 VARCHAR(36)），否则自行生成
    incoming = request.headers.get("x-request-id", "")
    rid = incoming if _REQUEST_ID.match(incoming) else uuid4().hex
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def database_health() -> dict[str, str]:
    try:
        check_database()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="DEPENDENCY_UNAVAILABLE") from exc
    return {"status": "ok", "database": "mysql"}


@app.get("/health/redis")
def redis_health() -> dict[str, str]:
    try:
        get_redis().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="DEPENDENCY_UNAVAILABLE") from exc
    return {"status": "ok", "redis": "up"}


# Starlette 基类同时覆盖路由级 404/405；业务端点以大写错误码作为 detail
@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return error_response(request, exc.status_code, code_for(exc.status_code, exc.detail), headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return error_response(request, 422, "VALIDATION_ERROR")


@app.exception_handler(RedisError)
async def redis_error_handler(request: Request, exc: RedisError):
    return error_response(request, 503, "DEPENDENCY_UNAVAILABLE")


# 兜底：没有这个处理器时，未捕获异常会以纯文本 500 返回，前端拿不到 error.code / request_id
@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", None)
    logger.exception("未处理的异常 request_id=%s path=%s", rid, request.url.path)
    response = error_response(request, 500, "INTERNAL_ERROR")
    if rid:
        # 异常穿过了 request_id 中间件，它没机会写响应头，在这里补齐以保持与 body 一致
        response.headers["X-Request-ID"] = rid
    return response
