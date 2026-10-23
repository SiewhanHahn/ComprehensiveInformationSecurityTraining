from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from .config import get_settings
from .db import check_database, get_redis
from .routers import audit, auth, hazards, metrics, monitor, replay, warnings
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


@app.exception_handler(RedisError)
async def redis_error_handler(request: Request, exc: RedisError):
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "DEPENDENCY_UNAVAILABLE", "message": "会话存储不可用"}},
    )
