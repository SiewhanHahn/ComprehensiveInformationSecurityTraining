"""预警状态机与业务规则。

路由只负责参数、鉴权依赖和响应序列化；状态是否允许、谁能操作、写哪些时间戳
和审计记录都集中在这里，便于后续阶段在状态变更后挂接通知/响应任务。
所有写操作只 ``flush``，由调用方在请求末尾统一 ``commit``，保证业务记录与审计同事务。
"""

from dataclasses import dataclass
from datetime import date, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import DEFAULT_MODELS, LEAD_HOURS, MODEL_DISPLAY, WARNING_CITIES
from ..clock import utcnow
from ..deps import ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER, CurrentUser
from ..models import Dataset, ForecastRecord, FusionInput, FusionRun, User, Warning, WarningFeedback, WarningResult, WarningReview
from ..assessment_schemas import SnowAssessment, TyphoonAssessment
from ..schemas import (
    FeedbackRequest, ModelValue, SnowWarningCreate, TyphoonWarningCreate, WarningCreate, WarningDetailOut,
    WarningDraftText, WarningOut, WarningUpdate,
)
from ..security import new_public_id
from . import snow, typhoon
from .audit import AuditContext
from .notifications import NOTIFY_PUBLISHED, NOTIFY_WITHDRAWN, notify_warning
from .replay import compute_replay
from .tasks import close_for_withdrawn, create_for_published

DRAFT = "DRAFT"
PENDING_REVIEW = "PENDING_REVIEW"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
PUBLISHED = "PUBLISHED"
WITHDRAWN = "WITHDRAWN"
CANCELLED = "CANCELLED"

WARNING_STATUSES = frozenset({DRAFT, PENDING_REVIEW, APPROVED, REJECTED, PUBLISHED, WITHDRAWN, CANCELLED})
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
CANCEL = Transition(EDITABLE_STATUSES, CANCELLED, "WARNING_CANCEL", "cancelled_at", "cancelled_by")


def is_viewer_only(current: CurrentUser) -> bool:
    privileged = {ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER}
    return not (privileged & set(current.roles))


def _apply(w: Warning, transition: Transition, actor: CurrentUser, audit: AuditContext, reason: str | None = None) -> None:
    if w.status not in transition.sources:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    resource_version = w.version_no
    w.status = transition.target
    if transition.timestamp_field:
        stamp = utcnow()
        if transition is SUBMIT and w.submitted_at is not None and stamp <= w.submitted_at:
            stamp = w.submitted_at + timedelta(microseconds=1)
        setattr(w, transition.timestamp_field, stamp)
    if transition.actor_field:
        setattr(w, transition.actor_field, actor.id)
    audit.record(
        transition.audit_action,
        resource_type="warning",
        resource_id=w.public_id,
        reason=reason,
        resource_version=resource_version,
    )


# ---- 查询 ----


def get_warning(db: Session, public_id: str, *, lock: bool = False) -> Warning | None:
    stmt = select(Warning).where(Warning.public_id == public_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def get_visible_warning(db: Session, public_id: str, current: CurrentUser) -> Warning:
    """查看者只能看到已发布预警；其余状态对其一律表现为不存在。"""
    w = get_warning(db, public_id)
    if w is None or w.status == CANCELLED or (is_viewer_only(current) and w.status != PUBLISHED):
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


def review_token(w: Warning) -> str | None:
    # Opaque optimistic-concurrency precondition, not an authorization credential.
    if w.status != PENDING_REVIEW or w.submitted_at is None:
        return None
    return f"{w.version_no}:{w.submitted_at.isoformat(timespec='microseconds')}"


_ASSESSMENT_MODELS = {"TYPHOON": TyphoonAssessment, "SNOW_DISASTER": SnowAssessment}


def _assessment_snapshot(w: Warning) -> TyphoonAssessment | SnowAssessment | None:
    model = _ASSESSMENT_MODELS.get(w.hazard_type)
    if model is not None and w.warning_result is not None:
        return model.model_validate(w.warning_result.assessment_json)
    return None


def to_out(w: Warning, names: dict[int, str]) -> WarningOut:
    return _to_out(w, names, _assessment_snapshot(w))


def _to_out(w: Warning, names: dict[int, str], assessment: TyphoonAssessment | SnowAssessment | None) -> WarningOut:
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
        city_name=WARNING_CITIES.get(result.city_code) if result else None,
        valid_date=result.valid_date if result else date.min,
        risk_level=result.risk_level if result else None,
        fused_mm=(float(result.fused_mm) if result.fused_mm is not None else None) if result else 0.0,
        metric=assessment.metric if assessment is not None else None,
        version_no=w.version_no,
        review_token=review_token(w),
        created_by=names.get(w.created_by, str(w.created_by)),
        submitted_at=w.submitted_at,
        approved_at=w.approved_at,
        published_at=w.published_at,
        withdrawn_at=w.withdrawn_at,
    )


def to_out_list(db: Session, warnings: list[Warning]) -> list[WarningOut]:
    names = usernames(db, {w.created_by for w in warnings})
    return [to_out(w, names) for w in warnings]


def to_detail_out(db: Session, w: Warning, names: dict[int, str], *, reader_id: int | None = None) -> WarningDetailOut:
    """预警详情：在列表字段基础上附带融合追溯（四模式输入、基线、代理标签、数据集版本）。"""
    assessment = _assessment_snapshot(w)
    base = _to_out(w, names, assessment)
    result = w.warning_result
    baseline_mm = None
    proxy_label_mm = None
    dataset_version = None
    models: list[ModelValue] = []
    if result is not None and result.fusion_run_id is not None:
        baseline_mm = float(result.baseline_mm) if result.baseline_mm is not None else None
        proxy_label_mm = float(result.proxy_label_mm) if result.proxy_label_mm is not None else None
        inputs = db.scalars(
            select(FusionInput).where(FusionInput.fusion_run_id == result.fusion_run_id)
        ).all()
        order = {code: idx for idx, code in enumerate(DEFAULT_MODELS)}
        ordered_inputs = sorted(inputs, key=lambda item: order.get(item.model_code, len(DEFAULT_MODELS)))
        models = [
            ModelValue(model=MODEL_DISPLAY.get(i.model_code, i.model_code), precipitation_mm=float(i.value_mm))
            for i in ordered_inputs
        ]
        if inputs:
            dataset_version = db.scalar(
                select(Dataset.version)
                .join(ForecastRecord, ForecastRecord.dataset_id == Dataset.id)
                .where(ForecastRecord.id.in_([i.forecast_record_id for i in inputs]))
                .limit(1)
            )
    rejection = None
    if w.status == REJECTED and reader_id == w.created_by:
        rejection = db.scalar(select(WarningReview.comment).where(
            WarningReview.warning_id == w.id, WarningReview.decision == "REJECT"
        ).order_by(WarningReview.id.desc()).limit(1))
    return WarningDetailOut(
        **base.model_dump(), rejection_comment=rejection,
        baseline_mm=baseline_mm,
        proxy_label_mm=proxy_label_mm,
        dataset_version=dataset_version,
        models=models,
        typhoon_assessment=assessment if isinstance(assessment, TyphoonAssessment) else None,
        snow_assessment=assessment if isinstance(assessment, SnowAssessment) else None,
    )


def list_feedback(db: Session, w: Warning) -> list[WarningFeedback]:
    stmt = select(WarningFeedback).where(WarningFeedback.warning_id == w.id).order_by(WarningFeedback.id)
    return list(db.scalars(stmt).all())


# ---- 写操作（只 flush，调用方 commit） ----


def create_warning(db: Session, body: WarningCreate, actor: CurrentUser, audit: AuditContext) -> Warning:
    compute = compute_replay(db, body.city_code, body.valid_date, body.threshold_code)
    if compute is None:
        # 回放无法解析城市或活动阈值；已知参数但样本不完整由下面的 409 区分。
        raise HTTPException(status_code=422, detail="INVALID_PARAMETER")
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
                value_mm=item.get("value_dec", Decimal(str(item["value_mm"]))),
            )
        )

    result = WarningResult(
        fusion_run_id=fusion_run.id,
        threshold_id=threshold.id,
        city_code=body.city_code,
        valid_date=body.valid_date,
        fused_mm=compute["fused_dec"] if compute.get("fused_dec") is not None else compute["fused_mm"],
        baseline_mm=compute["baseline_dec"] if "baseline_dec" in compute else compute["baseline_mm"],
        proxy_label_mm=compute["proxy_dec"] if "proxy_dec" in compute else compute["proxy_label_mm"],
        risk_level=compute["risk_level"],
        data_status="COMPLETE",
    )
    return _create_draft(db, result, "RAINSTORM", body, actor, audit)


def create_typhoon_warning(db: Session, body: TyphoonWarningCreate, actor: CurrentUser, audit: AuditContext) -> Warning:
    # No browser-supplied distance, weather file, or post-event position is a source for formal creation.
    _, forecast = typhoon.assess_case(body.case_id, body.city_code)
    if forecast.outcome == "INSUFFICIENT" or forecast.closest_point is None:
        raise HTTPException(409, "PARTIAL_DATA")
    if forecast.outcome != "NEAR":
        raise HTTPException(409, "THRESHOLD_NOT_REACHED")
    result = WarningResult(
        city_code=forecast.city.code,
        valid_date=forecast.closest_point.valid_at.astimezone(timezone.utc).date(),
        risk_level=typhoon.NEAR_RISK_LEVEL,
        data_status="COMPLETE",
        assessment_json=forecast.model_dump(mode="json"),
    )
    return _create_draft(db, result, "TYPHOON", body, actor, audit)


def create_snow_warning(db: Session, body: SnowWarningCreate, actor: CurrentUser, audit: AuditContext) -> Warning:
    # Recompute from the registered forecast only. Replay's independent station report is never stored here.
    _, forecast = snow.assess_case(body.case_id)
    if forecast.outcome == "INSUFFICIENT":
        raise HTTPException(409, "PARTIAL_DATA")
    if forecast.outcome != "REACHED":
        raise HTTPException(409, "THRESHOLD_NOT_REACHED")
    result = WarningResult(
        city_code=forecast.case.city.code,
        valid_date=forecast.case.window_start.astimezone(timezone.utc).date(),
        risk_level=snow.REACHED_RISK_LEVEL,
        data_status="COMPLETE",
        assessment_json=forecast.model_dump(mode="json"),
    )
    return _create_draft(db, result, "SNOW_DISASTER", body, actor, audit)


def _create_draft(db: Session, result: WarningResult, hazard_type: str, body: WarningDraftText,
                  actor: CurrentUser, audit: AuditContext) -> Warning:
    db.add(result)
    db.flush()
    w = Warning(
        public_id=new_public_id(),
        warning_result_id=result.id,
        hazard_type=hazard_type,
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


def cancel_warning(db: Session, public_id: str, actor: CurrentUser, audit: AuditContext, reason: str | None = None) -> Warning:
    w = get_warning(db, public_id, lock=True)
    if w is None or w.created_by != actor.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if w.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    _apply(w, CANCEL, actor, audit, reason=reason or "未提供原因")
    db.flush()
    return w


def update_warning(db: Session, public_id: str, body: WarningUpdate, actor: CurrentUser, audit: AuditContext) -> Warning:
    w = _require_own_editable(get_warning(db, public_id, lock=True), actor)
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if getattr(w, k) != v}
    if changes:
        for field, value in changes.items():
            setattr(w, field, value)
        w.version_no += 1
        audit.record("WARNING_UPDATE", resource_type="warning", resource_id=w.public_id, resource_version=w.version_no)
        db.flush()
    return w


def submit_warning(db: Session, public_id: str, actor: CurrentUser, audit: AuditContext) -> Warning:
    w = _require_own_editable(get_warning(db, public_id, lock=True), actor)
    if not (w.impact_text or "").strip():
        raise HTTPException(status_code=422, detail="IMPACT_REQUIRED")
    _apply(w, SUBMIT, actor, audit)
    db.flush()
    return w


def review_warning(db: Session, public_id: str, decision: str, comment: str, actor: CurrentUser,
                   audit: AuditContext, expected_token: str | None = None) -> WarningReview:
    w = get_warning(db, public_id, lock=True)
    if w is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if w.created_by == actor.id:
        raise HTTPException(status_code=403, detail="SELF_REVIEW_FORBIDDEN")
    if w.status != PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    if decision == "APPROVE":
        transition = APPROVE
    elif decision == "REJECT":
        if not comment:
            raise HTTPException(status_code=422, detail="REJECT_REQUIRES_COMMENT")
        transition = REJECT
    else:
        raise HTTPException(status_code=422, detail="INVALID_DECISION")

    if not expected_token or expected_token != review_token(w):
        raise HTTPException(status_code=409, detail="REVIEW_CHANGED")
    _apply(w, transition, actor, audit, reason=comment)
    review = WarningReview(warning_id=w.id, reviewer_id=actor.id, decision=decision, comment=comment)
    db.add(review)
    db.flush()
    return review


def _transition_existing(
    db: Session,
    public_id: str,
    transition: Transition,
    actor: CurrentUser,
    audit: AuditContext,
    reason: str | None = None,
) -> Warning:
    w = get_warning(db, public_id, lock=True)
    if w is None:
        # 发布/撤回接口历史上对不存在的预警也返回 409，保持兼容
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    _apply(w, transition, actor, audit, reason=reason)
    db.flush()
    return w


def publish_warning(db: Session, public_id: str, actor: CurrentUser, audit: AuditContext, reason: str | None = None) -> Warning:
    w = _transition_existing(db, public_id, PUBLISH, actor, audit, reason=reason or "未提供原因")
    # 通知与响应任务都和状态变更、审计同事务（服务只 flush，路由 commit）
    notify_warning(db, w, NOTIFY_PUBLISHED)
    create_for_published(db, w, actor, audit)
    return w


def withdraw_warning(db: Session, public_id: str, actor: CurrentUser, audit: AuditContext, reason: str | None = None) -> Warning:
    w = _transition_existing(db, public_id, WITHDRAW, actor, audit, reason=reason or "未提供原因")
    # 先关闭关联响应任务再发送撤回通知，避免并行扫描窗口误判
    close_for_withdrawn(db, w, audit)
    notify_warning(db, w, NOTIFY_WITHDRAWN)
    return w


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
