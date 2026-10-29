import json
from typing import Any

from .config import get_settings
from .db import get_redis


def _key(session_id: str) -> str:
    return f"session:{session_id}"


def create_session(session_id: str, user_id: int, roles: list[str], csrf_token: str) -> None:
    # roles 冗余存储仅为审计/诊断参考；鉴权以数据库实时角色为准（见 deps.get_current_user）
    payload = {
        "user_id": user_id,
        "roles": roles,
        "csrf_token": csrf_token,
    }
    get_redis().setex(_key(session_id), get_settings().session_ttl_seconds, json.dumps(payload))


def read_session(session_id: str) -> dict[str, Any] | None:
    raw = get_redis().get(_key(session_id))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def touch_session(session_id: str) -> None:
    get_redis().expire(_key(session_id), get_settings().session_ttl_seconds)


def delete_session(session_id: str) -> None:
    get_redis().delete(_key(session_id))
