from datetime import datetime, timezone


def utcnow() -> datetime:
    """当前 UTC 时间（naive），与 MySQL DATETIME(6) 列的存储约定一致。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
