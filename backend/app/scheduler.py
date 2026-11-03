"""定时扫描：独立的扫描循环，由 compose 的 ``scheduler`` 服务运行（不随 API 进程启动）。

``run_scan`` 是纯函数，测试可以直接传入 ``now`` 调用，不需要 sleep 或后台线程。
本阶段只有「投递补偿」一趟；B 档第二刀的响应任务超时升级作为新一轮加在这里。
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

logger = logging.getLogger("backend.scheduler")


@dataclass
class ScanResult:
    backfilled: int = 0


def run_scan(db: Session, *, now: datetime | None = None, hours: int | None = None) -> ScanResult:
    """跑一轮扫描。补投了才写审计，避免空扫描把审计表刷满。"""
    now = now or utcnow()
    if hours is None:
        hours = get_settings().notification_backfill_hours
    backfilled = backfill_published(db, hours=hours, now=now)
    if backfilled:
        add_audit(
            db,
            action="NOTIFICATION_BACKFILL",
            resource_type="notification",
            result="SUCCESS",
            actor_role="SYSTEM",
            reason=f"created={backfilled}",
        )
        logger.info("通知补投 created=%s", backfilled)
    return ScanResult(backfilled=backfilled)


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
                run_scan(db)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("扫描失败")
        stop.wait(interval)
    logger.info("定时扫描已停止")


if __name__ == "__main__":
    main()
