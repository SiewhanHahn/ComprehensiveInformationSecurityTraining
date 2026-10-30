"""预警状态机与业务规则。

路由只负责参数、鉴权依赖和响应序列化；状态是否允许、谁能操作、写哪些时间戳
和审计记录都集中在这里，便于后续阶段在状态变更后挂接通知/响应任务。
所有写操作只 ``flush``，由调用方在请求末尾统一 ``commit``，保证业务记录与审计同事务。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import LEAD_HOURS, MODEL_DISPLAY
from ..clock import utcnow
from ..deps import ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER, ROLE_VIEWER, CurrentUser
from ..models import Dataset, ForecastRecord, FusionInput, FusionRun, User, Warning, WarningFeedback, WarningResult, WarningReview
from ..schemas import FeedbackRequest, ModelValue, WarningCreate, WarningDetailOut, WarningOut, WarningUpdate
from ..security import new_public_id
from .audit import AuditContext
from .replay import compute_replay

DRAFT = "DRAFT"
PENDING_REVIEW = "PENDING_REVIEW"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
PUBLISHED = "PUBLISHED"
WITHDRAWN = "WITHDRAWN"

WARNING_STATUSES = frozenset({DRAFT, PENDING_REVIEW, APPROVED, REJECTED, PUBLISHED, WITHDRAWN})
EDITABLE_STATUSES = frozenset({DRAFT, REJECTED})
FEEDBACK_STATUSES = frozenset({PUBLISHED, WITHDRAWN})


@dataclass(frozen=True)
class Transition:
    """一次状态转换：允许的起始状态、目标状态、写入的时间戳/操作者字段与审计动作。"""

    sources: frozenset[str]
    target: str
    audit_action: str
    timestamp_field: str | None = None
    actor_field: str | None = None


SUBMIT = Transition(EDITABLE_STATUSES, PENDING_REVIEW, "WARNING_SUBMIT", "submitted_at")
APPROVE = Transition(frozenset({PENDING_REVIEW}), APPROVED, "WARNING_REVIEW", "approved_at")
REJECT = Transition(frozenset({PENDING_REVIEW}), REJECTED, "WARNING_REVIEW")
PUBLISH = Transition(frozenset({APPROVED}), PUBLISHED, "WARNING_PUBLISH", "published_at", "published_by")
WITHDRAW = Transition(frozenset({PUBLISHED}), WITHDRAWN, "WARNING_WITHDRAW", "withdrawn_at", "withdrawn_by")


def is_viewer_only(current: CurrentUser) -> bool:
    privileged = {ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER}
    return ROLE_VIEWER in current.roles and not (privileged & set(current.roles))


def _apply(w: Warning, transition: Transition, actor: CurrentUser, audit: AuditContext, reason: str | None = None) -> None:
    if w.status not in transition.sources:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    w.status = transition.target
    if transition.timestamp_field:
        setattr(w, transition.timestamp_field, utcnow())
    if transition.actor_field:
        setattr(w, transition.actor_field, actor.id)
    audit.record(transition.audit_action, resource_type="warning", resource_id=w.public_id, reason=reason)


# ---- 查询 ----


def get_warning(db: Session, public_id: str, *, lock: bool = False) -> Warning | None:
    stmt = select(Warning).where(Warning.public_id == public_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def get_visible_warning(db: Session, public_id: str, current: CurrentUser) -> Warning:
    """查看者只能看到已发布预警；其余状态对其一律表现为不存在。"""
    w = get_warning(db, public_id)
    if w is None or (is_viewer_only(current) and w.status != PUBLISHED):
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return w


def list_warnings(db: Session, current: CurrentUser, status: str | None) -> list[Warning]:
    if status is not None and status not in WARNING_STATUSES:
        raise HTTPException(status_code=400, detail="INVALID_PARAMETER")
    stmt = select(Warning)
    if is_viewer_only(current):
        if status is not None and status != PUBLISHED:
            return []
        stmt = stmt.where(Warning.status == PUBLISHED)
    elif status is not None:
        stmt = stmt.where(Warning.status == status)
    return list(db.scalars(stmt.order_by(Warning.id.desc())).all())


def usernames(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.execute(select(User.id, User.username).where(User.id.in_(user_ids))).all()
    return {uid: name for uid, name in rows}


def to_out(w: Warning, names: dict[int, str]) -> WarningOut:
    result = w.warning_result
    return WarningOut(
        public_id=w.public_id,
        hazard_type=w.hazard_type,
        status=w.status,
        title=w.title,
        area_text=w.area_text,
        impact_text=w.impact_text,
        reasoning_text=w.reasoning_text,
        city_code=result.city_code if result else "",
        valid_date=result.valid_date if result else date.min,
        risk_level=result.risk_level if result else None,
        fused_mm=float(result.fused_mm) if result else 0.0,
        version_no=w.version_no,
        created_by=names.get(w.created_by, str(w.created_by)),
        submitted_at=w.submitted_at,
        approved_at=w.approved_at,
        published_at=w.published_at,
        withdrawn_at=w.withdrawn_at,
    )


def to_out_list(db: Session, warnings: list[Warning]) -> list[WarningOut]:
    names = usernames(db, {w.created_by for w in warnings})
    return [to_out(w, names) for w in warnings]


def to_detail_out(db: Session, w: Warning, names: dict[int, str]) -> WarningDetailOut:
    """预警详情：在列表字段基础上附带融合追溯（四模式输入、基线、代理标签、数据集版本）。"""
    base = to_out(w, names)
    result = w.warning_result
    baseline_mm = None
    proxy_label_mm = None
    dataset_version = None
    models: list[ModelValue] = []
    if result is not None:
        baseline_mm = float(result.baseline_mm) if result.baseline_mm is not None else None
        proxy_label_mm = float(result.proxy_label_mm) if result.proxy_label_mm is not None else None
        inputs = db.scalars(
            select(FusionInput).where(FusionInput.fusion_run_id == result.fusion_run_id)
        ).all()
        models = [
            ModelValue(model=MODEL_DISPLAY.get(i.model_code, i.model_code), precipitation_mm=float(i.value_mm))
            for i in inputs
        ]
        if inputs:
            dataset_version = db.scalar(
                select(Dataset.version)
                .join(ForecastRecord, ForecastRecord.dataset_id == Dataset.id)
                .where(ForecastRecord.id.in_([i.forecast_record_id for i in inputs]))
                .limit(1)
            )
    return WarningDetailOut(
        **base.model_dump(),
        baseline_mm=baseline_mm,
        proxy_label_mm=proxy_label_mm,
        dataset_version=dataset_version,
        models=models,
    )


def list_feedback(db: Session, w: Warning) -> list[WarningFeedback]:
    stmt = select(WarningFeedback).where(WarningFeedback.warning_id == w.id).order_by(WarningFeedback.id)
    return list(db.scalars(stmt).all())


# ---- 写操作（只 flush，调用方 commit） ----


def create_warning(db: Session, body: WarningCreate, actor: CurrentUser, audit: AuditContext) -> Warning:
    compute = compute_replay(db, body.city_code, body.valid_date, body.threshold_code)
    if compute is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if compute["data_status"] != "COMPLETE":
        raise HTTPException(status_code=409, detail="PARTIAL_DATA")
    if compute["risk_level"] is None:
        raise HTTPException(status_code=409, detail="THRESHOLD_NOT_REACHED")

    threshold = compute["threshold_row"]
    inputs = compute["inputs"]
    weight = round(1 / len(inputs), 4) if inputs else 0
    fusion_run = FusionRun(
        algorithm_version="v1",
        method="EQUAL_MEAN",
        lead_hours=LEAD_HOURS,
        weights_json={i["model_code"]: weight for i in inputs},
        input_count=len(inputs),
        status="SUCCESS",
        executed_at=utcnow(),
        created_by=actor.id,
    )
    db.add(fusion_run)
    db.flush()

    for item in inputs:
        db.add(
            FusionInput(
                fusion_run_id=fusion_run.id,
                forecast_record_id=item["forecast_record_id"],
                model_code=item["model_code"],
                value_mm=Decimal(str(item["value_mm"])),
            )
        )

    result = WarningResult(
        fusion_run_id=fusion_run.id,
        threshold_id=threshold.id,
        city_code=body.city_code,
        valid_date=body.valid_date,
        fused_mm=compute["fused_mm"],
        baseline_mm=compute["baseline_mm"],
        proxy_label_mm=compute["proxy_label_mm"],
        risk_level=compute["risk_level"],
        data_status="COMPLETE",
    )
    db.add(result)
    db.flush()

    w = Warning(
        public_id=new_public_id(),
        warning_result_id=result.id,
        hazard_type="RAINSTORM",
        created_by=actor.id,
        status=DRAFT,
        title=body.title,
        area_text=body.area_text,
        impact_text=body.impact_text,
        reasoning_text=body.reasoning_text,
    )
    db.add(w)
    audit.record("WARNING_CREATE", resource_type="warning", resource_id=w.public_id)
    db.flush()
    return w


def _require_own_editable(w: Warning | None, actor: CurrentUser) -> Warning:
    # 不存在、非本人、状态不可编辑统一返回 403，不暴露他人草稿是否存在
    if w is None or w.created_by != actor.id or w.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return w


def update_warning(db: Session, public_id: str, body: WarningUpdate, actor: CurrentUser, audit: AuditContext) -> Warning:
    w = _require_own_editable(get_warning(db, public_id, lock=True), actor)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(w, field, value)
    audit.record("WARNING_UPDATE", resource_type="warning", resource_id=w.public_id)
    db.flush()
    return w


def submit_warning(db: Session, public_id: str, actor: CurrentUser, audit: AuditContext) -> Warning:
    w = _require_own_editable(get_warning(db, public_id, lock=True), actor)
    _apply(w, SUBMIT, actor, audit)
    db.flush()
    return w


def review_warning(db: Session, public_id: str, decision: str, comment: str, actor: CurrentUser, audit: AuditContext) -> WarningReview:
    w = get_warning(db, public_id, lock=True)
    if w is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if w.created_by == actor.id:
        raise HTTPException(status_code=403, detail="SELF_REVIEW_FORBIDDEN")
    if w.status != PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    if decision == "REJECT" and not comment:
        raise HTTPException(status_code=422, detail="REJECT_REQUIRES_COMMENT")

    _apply(w, APPROVE if decision == "APPROVE" else REJECT, actor, audit, reason=decision)
    review = WarningReview(warning_id=w.id, reviewer_id=actor.id, decision=decision, comment=comment)
    db.add(review)
    db.flush()
    return review


def _transition_existing(db: Session, public_id: str, transition: Transition, actor: CurrentUser, audit: AuditContext) -> Warning:
    w = get_warning(db, public_id, lock=True)
    if w is None:
        # 发布/撤回接口历史上对不存在的预警也返回 409，保持兼容
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    _apply(w, transition, actor, audit)
    db.flush()
    return w


def publish_warning(db: Session, public_id: str, actor: CurrentUser, audit: AuditContext) -> Warning:
    return _transition_existing(db, public_id, PUBLISH, actor, audit)


def withdraw_warning(db: Session, public_id: str, actor: CurrentUser, audit: AuditContext) -> Warning:
    return _transition_existing(db, public_id, WITHDRAW, actor, audit)


def add_feedback(db: Session, public_id: str, body: FeedbackRequest, actor: CurrentUser, audit: AuditContext) -> WarningFeedback:
    w = get_warning(db, public_id)
    if w is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if w.status not in FEEDBACK_STATUSES:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    fb = WarningFeedback(warning_id=w.id, created_by=actor.id, response_status=body.response_status, content=body.content)
    db.add(fb)
    audit.record("WARNING_FEEDBACK", resource_type="warning", resource_id=w.public_id)
    db.flush()
    return fb
