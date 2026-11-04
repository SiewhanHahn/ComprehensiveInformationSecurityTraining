"""响应任务：发布时自动生成、负责人接单与完成、超时升级。

状态只走 ``PENDING → ACKED → COMPLETED``；**超时不改状态**，只写 ``escalated_at`` /
``escalation_level``，避免把「已逾期」混进正常流转状态。写操作只 ``flush``，由调用方 ``commit``，
与预警状态变更、审计记录同事务。
"""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..clock import utcnow
from ..config import get_settings
from ..deps import ROLE_ADMIN, CurrentUser
from ..models import Role, ResponseTask, User, UserRole, Warning
from ..schemas import ResponseTaskOut
from .audit import AuditContext
from .notifications import notify_users, warning_summary

PENDING = "PENDING"
ACKED = "ACKED"
COMPLETED = "COMPLETED"
TASK_STATUSES = frozenset({PENDING, ACKED, COMPLETED})

NOTIFY_TASK_ASSIGNED = "TASK_ASSIGNED"
NOTIFY_TASK_OVERDUE = "TASK_OVERDUE"
NOTIFY_TASK_ESCALATED = "TASK_ESCALATED"


def is_overdue(task: ResponseTask, now: datetime) -> bool:
    """逾期只看时限与是否完成；超时不改状态，所以不能靠 status 判断。"""
    return task.status != COMPLETED and task.due_at < now


# ---- 写操作 ----


def create_for_published(db: Session, w: Warning, actor: CurrentUser, audit: AuditContext) -> ResponseTask:
    """发布时给预警创建者派一条处置任务，时限由配置决定。

    创建者若已停用（草稿提交后被管理员停用，但审核员仍可发布），任务改派给发布人：
    停用账号登录不了又没有改派接口，任务会永远没人能推进。
    """
    creator_active = db.scalar(select(User.is_active).where(User.id == w.created_by))
    assignee_id = w.created_by if creator_active else actor.id
    due_at = (w.published_at or utcnow()) + timedelta(minutes=get_settings().response_task_due_minutes)
    task = ResponseTask(warning_id=w.id, assignee_id=assignee_id, created_by=actor.id, due_at=due_at)
    db.add(task)
    db.flush()

    audit.record(
        "RESPONSE_TASK_CREATE",
        resource_type="response_task",
        resource_id=str(task.id),
        reason=None if assignee_id == w.created_by else f"创建者 {w.created_by} 已停用，改派发布人 {actor.id}",
    )
    notify_users(
        db,
        user_ids=[task.assignee_id],
        kind=NOTIFY_TASK_ASSIGNED,
        title="响应任务指派",
        body=f"{warning_summary(w)}；处置时限 {due_at:%Y-%m-%d %H:%M} UTC",
        resource_type="response_task",
        resource_id=str(task.id),
    )
    return task


def ack_task(db: Session, task_id: int, actor: CurrentUser, audit: AuditContext) -> ResponseTask:
    task = get_visible_task(db, task_id, actor)
    if task.status != PENDING:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    task.status = ACKED
    task.acked_at = utcnow()
    audit.record("RESPONSE_TASK_ACK", resource_type="response_task", resource_id=str(task.id))
    db.flush()
    return task


def complete_task(
    db: Session, task_id: int, note: str | None, actor: CurrentUser, audit: AuditContext
) -> ResponseTask:
    task = get_visible_task(db, task_id, actor)
    if task.status != ACKED:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    task.status = COMPLETED
    task.completed_at = utcnow()
    if note and note.strip():
        task.note = note.strip()
    audit.record("RESPONSE_TASK_COMPLETE", resource_type="response_task", resource_id=str(task.id))
    db.flush()
    return task


def escalate_overdue(db: Session, *, now: datetime) -> int:
    """把已过时限、尚未完成、还没升级过的任务标记升级，并通知负责人与管理员。

    只升级一次：``escalated_at`` 一旦写入就不再进入筛选，扫描重复执行天然幂等。

    升级用**带条件的单行 UPDATE**，而不是读出对象后逐字段赋值：完成请求可能在本轮扫描
    读出候选之后才提交，UPDATE 的 WHERE（含 ``status``）在写时按 current read 求值，
    因此并发完成的任务不会被覆盖成「已升级」并误报管理员。
    """
    candidates = db.execute(
        select(ResponseTask.id, ResponseTask.warning_id, ResponseTask.assignee_id).where(
            ResponseTask.status.in_((PENDING, ACKED)),
            ResponseTask.due_at < now,
            ResponseTask.escalated_at.is_(None),
        )
    ).all()
    if not candidates:
        return 0

    escalated: list[tuple[int, int, int]] = []
    for task_id, warning_id, assignee_id in candidates:
        result = db.execute(
            update(ResponseTask)
            .where(
                ResponseTask.id == task_id,
                ResponseTask.status.in_((PENDING, ACKED)),
                ResponseTask.due_at < now,
                ResponseTask.escalated_at.is_(None),
            )
            .values(escalated_at=now, escalation_level=ResponseTask.escalation_level + 1)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            escalated.append((task_id, warning_id, assignee_id))
    if not escalated:
        return 0

    warnings = {
        w.id: w
        for w in db.scalars(select(Warning).where(Warning.id.in_({row[1] for row in escalated}))).all()
    }
    names = {
        u.id: u.username
        for u in db.scalars(select(User).where(User.id.in_({row[2] for row in escalated}))).all()
    }
    admin_ids = list(
        db.scalars(
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .join(User, User.id == UserRole.user_id)
            .where(Role.code == ROLE_ADMIN, User.is_active.is_(True))
        ).all()
    )

    for task_id, warning_id, assignee_id in escalated:
        summary = warning_summary(warnings[warning_id]) if warning_id in warnings else f"任务 #{task_id}"
        notify_users(
            db,
            user_ids=[assignee_id],
            kind=NOTIFY_TASK_OVERDUE,
            title="响应任务已超时",
            body=f"{summary}；处置时限已过，请尽快处置",
            resource_type="response_task",
            resource_id=str(task_id),
        )
        notify_users(
            db,
            user_ids=admin_ids,
            kind=NOTIFY_TASK_ESCALATED,
            title="响应任务超时升级",
            body=f"{summary}；负责人 {names.get(assignee_id, assignee_id)} 未在时限内处置",
            resource_type="response_task",
            resource_id=str(task_id),
        )
    db.flush()
    return len(escalated)


# ---- 查询 ----


def get_visible_task(db: Session, task_id: int, actor: CurrentUser) -> ResponseTask:
    """别人的任务对非管理员一律表现为不存在，与通知中心的按用户收敛一致。"""
    task = db.scalar(select(ResponseTask).where(ResponseTask.id == task_id))
    if task is None or (task.assignee_id != actor.id and not actor.has_role(ROLE_ADMIN)):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return task


def list_tasks(
    db: Session, actor: CurrentUser, *, status: str | None = None, warning_public_id: str | None = None
) -> list[ResponseTask]:
    """按条件列出任务。

    可见范围分两种：**带预警过滤**时，能打开该预警的业务角色都能读到它的任务（只读，
    用于详情页展示负责人/时限/升级情况）；**不带预警过滤**的看板列表仍只给管理员与本人，
    避免越权浏览别人的任务。接单与完成始终只允许负责人或管理员（见 ``get_visible_task``）。
    """
    if status is not None and status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="INVALID_PARAMETER")

    stmt = select(ResponseTask)
    if warning_public_id is not None:
        warning = db.scalar(select(Warning).where(Warning.public_id == warning_public_id))
        if warning is None:
            raise HTTPException(status_code=404, detail="NOT_FOUND")
        stmt = stmt.where(ResponseTask.warning_id == warning.id)
    elif not actor.has_role(ROLE_ADMIN):
        stmt = stmt.where(ResponseTask.assignee_id == actor.id)
    if status is not None:
        stmt = stmt.where(ResponseTask.status == status)

    return list(db.scalars(stmt.order_by(ResponseTask.due_at, ResponseTask.id)).all())


def to_out_list(db: Session, tasks: list[ResponseTask]) -> list[ResponseTaskOut]:
    if not tasks:
        return []

    warnings = {
        w.id: w
        for w in db.scalars(select(Warning).where(Warning.id.in_({t.warning_id for t in tasks}))).all()
    }
    names = {
        u.id: u.username
        for u in db.scalars(select(User).where(User.id.in_({t.assignee_id for t in tasks}))).all()
    }
    now = utcnow()
    out: list[ResponseTaskOut] = []
    for t in tasks:
        w = warnings.get(t.warning_id)
        out.append(
            ResponseTaskOut(
                id=t.id,
                warning_public_id=w.public_id if w else "",
                warning_title=w.title if w else "",
                assignee=names.get(t.assignee_id, str(t.assignee_id)),
                status=t.status,
                due_at=t.due_at,
                acked_at=t.acked_at,
                completed_at=t.completed_at,
                escalated_at=t.escalated_at,
                escalation_level=t.escalation_level,
                note=t.note,
                overdue=is_overdue(t, now),
                created_at=t.created_at,
            )
        )
    return out
