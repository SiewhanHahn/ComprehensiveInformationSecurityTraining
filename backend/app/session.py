import json
from typing import Any

from .config import get_settings
from .db import get_redis

settings = get_settings()


def create_session(session_id: str, user_id: int, roles: list[str], csrf_token: str) -> None:
    # roles 冗余存储仅为审计/诊断参考；鉴权以数据库实时角色为准（见 deps.get_current_user）
    payload = {
        "user_id": user_id,
        "roles": roles,
        "csrf_token": csrf_token,
    }
    redis = get_redis()
    redis.setex(
        f"session:{session_id}",
        settings.session_ttl_seconds,
        json.dumps(payload),
    )


def read_session(session_id: str) -> dict[str, Any] | None:
    raw = get_redis().get(f"session:{session_id}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def touch_session(session_id: str) -> None:
    get_redis().expire(f"session:{session_id}", settings.session_ttl_seconds)


def delete_session(session_id: str) -> None:
    get_redis().delete(f"session:{session_id}")
