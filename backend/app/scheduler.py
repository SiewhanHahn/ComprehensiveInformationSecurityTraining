"""定时扫描：独立的扫描循环，由 compose 的 ``scheduler`` 服务运行（不随 API 进程启动）。

每轮跑两趟：通知补投与响应任务超时升级。``run_scan`` 是纯函数，
测试可以直接传入 ``now`` 调用，不需要 sleep 或后台线程。
"""

import logging
import signal
import threading
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from .clock import utcnow
from .config import get_settings
from .db import SessionLocal
from .services.audit import add_audit
from .services.notifications import backfill_published
from .services.tasks import escalate_overdue

logger = logging.getLogger("backend.scheduler")


@dataclass
class ScanResult:
    backfilled: int = 0
    escalated: int = 0
    failed: tuple[str, ...] = ()


def run_scan(db: Session, *, now: datetime | None = None, hours: int | None = None) -> ScanResult:
    """跑一轮扫描。只有真的做了事才写审计，避免空扫描把审计表刷满。

    两趟各有自己的事务：任何一趟抛错只回滚它自己，不会把另一趟已经写入的通知、
    任务状态与审计一起抹掉。失败记进 ``ScanResult.failed`` 并写日志，循环继续下一轮
    （让一条毒数据把补投永远卡住，比这轮少补几条更糟）。
    """
    now = now or utcnow()
    if hours is None:
        hours = get_settings().notification_backfill_hours

    result = ScanResult()

    try:
        result.backfilled = _run_backfill(db, hours=hours, now=now)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("通知补投失败")
        result.failed = (*result.failed, "backfill")

    try:
        result.escalated = _run_escalation(db, now=now)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("响应任务升级失败")
        result.failed = (*result.failed, "escalate")

    return result


def _run_backfill(db: Session, *, hours: int, now: datetime) -> int:
    created = backfill_published(db, hours=hours, now=now)
    if created:
        add_audit(
            db,
            action="NOTIFICATION_BACKFILL",
            resource_type="notification",
            result="SUCCESS",
            actor_role="SYSTEM",
            reason=f"created={created}",
        )
        logger.info("通知补投 created=%s", created)
    return created


def _run_escalation(db: Session, *, now: datetime) -> int:
    escalated = escalate_overdue(db, now=now)
    if escalated:
        add_audit(
            db,
            action="RESPONSE_TASK_ESCALATE",
            resource_type="response_task",
            result="SUCCESS",
            actor_role="SYSTEM",
            reason=f"escalated={escalated}",
        )
        logger.info("响应任务超时升级 escalated=%s", escalated)
    return escalated


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    interval = max(1, get_settings().notification_scan_interval_seconds)
    stop = threading.Event()

    def _shutdown(signum, _frame):
        logger.info("收到信号 %s，停止扫描", signum)
        stop.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("定时扫描启动，间隔 %s 秒", interval)
    while not stop.is_set():
        with SessionLocal() as db:
            try:
                run_scan(db)  # 每趟各自提交；这里再兜一层，防止连接/会话级异常打断循环
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("扫描失败")
        stop.wait(interval)
    logger.info("定时扫描已停止")


if __name__ == "__main__":
    main()
