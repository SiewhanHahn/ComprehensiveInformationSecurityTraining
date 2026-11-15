"""响应任务接口：参数、鉴权与序列化；业务规则见 ``services/tasks.py``。

任务只对业务角色开放（查看者整体 403）。看板列表里非管理员只看到指派给自己的任务；
按预警查询时，能看到该预警的业务角色都能读到它的任务，但接单与完成仍限负责人或管理员。
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER, CurrentUser, require_roles
from ..schemas import ResponseTaskOut, TaskCompleteRequest
from ..services import tasks as svc
from ..services.audit import audit_context

router = APIRouter()

business_required = require_roles(ROLE_ANALYST, ROLE_REVIEWER, ROLE_ADMIN)


@router.get("/response-tasks", response_model=list[ResponseTaskOut])
def list_tasks(
    status: str | None = Query(None),
    warning: str | None = Query(None),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(business_required),
):
    tasks = svc.list_tasks(db, current, status=status, warning_public_id=warning)
    return svc.to_out_list(db, tasks)


@router.post("/response-tasks/{task_id}/ack", response_model=ResponseTaskOut)
def ack_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(business_required),
):
    task = svc.ack_task(db, task_id, current, audit_context(request, db, current))
    db.commit()
    return svc.to_out_list(db, [task])[0]


@router.post("/response-tasks/{task_id}/complete", response_model=ResponseTaskOut)
def complete_task(
    task_id: int,
    body: TaskCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(business_required),
):
    task = svc.complete_task(db, task_id, body.note, current, audit_context(request, db, current))
    db.commit()
    return svc.to_out_list(db, [task])[0]
