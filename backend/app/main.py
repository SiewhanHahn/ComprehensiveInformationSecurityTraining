import re
import secrets
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .db import check_database, get_redis
from .errors import code_for, error_response
from .routers import audit, auth, hazards, metrics, monitor, replay, users, warnings
from .session import read_session

settings = get_settings()

app = FastAPI(
    title="气象灾害预测与预警系统",
    version="0.1.0",
    description="教学演示用气象预警系统 API",
)

app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(replay.router, prefix="/api/v1", tags=["replay"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(warnings.router, prefix="/api/v1", tags=["warnings"])
app.include_router(audit.router, prefix="/api/v1", tags=["audit"])
app.include_router(hazards.router, prefix="/api/v1", tags=["hazards"])
app.include_router(monitor.router, prefix="/api/v1", tags=["monitor"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,36}$")


# Starlette 中后注册的中间件在外层：CSRF 先注册，请求号中间件后注册，
# 保证 CSRF 拒绝的响应同样带 request_id / X-Request-ID。
@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)
    if request.url.path.endswith("/auth/login"):
        return await call_next(request)

    token = request.headers.get("x-csrf-token")
    session_id = request.cookies.get(settings.session_cookie_name)
    expected = None
    if session_id:
        try:
            payload = read_session(session_id)
            expected = payload.get("csrf_token") if payload else None
        except Exception:
            return error_response(request, 503, "DEPENDENCY_UNAVAILABLE")
    if not token or not expected or not secrets.compare_digest(token, expected):
        return error_response(request, 403, "CSRF")
    return await call_next(request)


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
