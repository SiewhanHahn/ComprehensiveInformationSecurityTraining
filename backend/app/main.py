from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import get_settings
from .db import check_database, get_redis
from .deps import request_id
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


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid4().hex
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


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
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "DEPENDENCY_UNAVAILABLE", "message": "会话存储不可用"}},
            )
    if not token or not expected or token != expected:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "CSRF", "message": "缺少或错误的 CSRF Token"}},
        )
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/db")
def database_health() -> dict[str, str]:
    try:
        check_database()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "database": "mysql"}


@app.get("/health/redis")
def redis_health() -> dict[str, str]:
    try:
        get_redis().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="redis unavailable") from exc
    return {"status": "ok", "redis": "up"}


# Starlette 基类同时覆盖路由级 404/405；业务端点以大写错误码作为 detail
@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    status_codes = {400: "INVALID_PARAMETER", 401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND",
                    503: "DEPENDENCY_UNAVAILABLE"}
    detail = exc.detail if isinstance(exc.detail, str) else ""
    code = detail if detail.replace("_", "").isalpha() and detail.isupper() else status_codes.get(exc.status_code, "HTTP_ERROR")
    messages = {
        "FORBIDDEN": "当前角色无权执行该操作",
        "UNAUTHENTICATED": "未登录或会话已过期",
        "NOT_FOUND": "请求的资源不存在",
        "USERNAME_EXISTS": "用户名已存在",
        "LAST_ADMIN_REQUIRED": "系统至少需要一名管理员",
        "SELF_DISABLE_FORBIDDEN": "不能停用当前登录账号",
        "SELF_ADMIN_REMOVAL_FORBIDDEN": "不能撤销当前登录账号的管理员角色",
        "DEPENDENCY_UNAVAILABLE": "依赖服务不可用，请稍后重试",
        "CSRF": "缺少或错误的 CSRF Token",
        "SELF_REVIEW_FORBIDDEN": "不能审核自己创建的预警",
        "PARTIAL_DATA": "数据不完整，无法创建正式预警",
        "INVALID_STATE": "当前状态不允许此操作",
        "INVALID_PARAMETER": "请求参数不合法",
        "REJECT_REQUIRES_COMMENT": "驳回时必须填写审核意见",
        "INVALID_CREDENTIALS": "用户名或密码错误",
        "ACCOUNT_LOCKED": "账号已锁定，请稍后再试",
        "ACCOUNT_DISABLED": "账号已停用",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": messages.get(code, code), "request_id": request_id(request)}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数不合法（请检查输入）", "request_id": request_id(request)}},
    )


@app.exception_handler(RedisError)
async def redis_error_handler(request: Request, exc: RedisError):
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "DEPENDENCY_UNAVAILABLE", "message": "会话存储不可用", "request_id": request_id(request)}},
    )
