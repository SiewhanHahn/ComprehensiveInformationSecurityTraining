from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cities import DEFAULT_MODELS
from ..db import get_db
from ..deps import (
    ROLE_ADMIN,
    ROLE_ANALYST,
    ROLE_REVIEWER,
    ROLE_VIEWER,
    CurrentUser,
    client_ip,
    get_current_user,
    request_id,
    require_roles,
)
from ..models import (
    FusionRun,
    User,
    Warning,
    WarningFeedback,
    WarningResult,
    WarningReview,
)
from ..schemas import (
    FeedbackOut,
    FeedbackRequest,
    ReviewOut,
    ReviewRequest,
    WarningCreate,
    WarningOut,
    WarningUpdate,
)
from ..security import new_public_id
from ..services.audit import add_audit
from ..services.replay import compute_replay, _get_threshold

router = APIRouter()

STATUS = ("DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "PUBLISHED", "WITHDRAWN")


def _viewer_only(current: CurrentUser) -> bool:
    privileged = {ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER}
    return ROLE_VIEWER in current.roles and not (privileged & set(current.roles))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _username(db: Session, user_id: int) -> str:
    u = db.scalar(select(User).where(User.id == user_id))
    return u.username if u else str(user_id)


def _to_out(db: Session, w: Warning, username_map: dict[int, str] | None = None) -> WarningOut:
    return WarningOut(
        public_id=w.public_id,
        hazard_type=w.hazard_type,
        status=w.status,
        title=w.title,
        area_text=w.area_text,
        impact_text=w.impact_text,
        reasoning_text=w.reasoning_text,
        city_code=w.warning_result.city_code if w.warning_result else "",
        valid_date=w.warning_result.valid_date if w.warning_result else date.min,
        risk_level=w.warning_result.risk_level if w.warning_result else None,
        fused_mm=float(w.warning_result.fused_mm) if w.warning_result else 0.0,
        version_no=w.version_no,
        created_by=username_map.get(w.created_by, str(w.created_by)) if username_map is not None else _username(db, w.created_by),
        submitted_at=w.submitted_at,
        approved_at=w.approved_at,
        published_at=w.published_at,
        withdrawn_at=w.withdrawn_at,
    )


def _get_warning(db: Session, public_id: str, lock: bool = False) -> Warning | None:
    stmt = select(Warning).where(Warning.public_id == public_id)
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


@router.post("/warnings", response_model=WarningOut)
def create_warning(
    body: WarningCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require_roles(ROLE_ANALYST, ROLE_ADMIN)),
):
    compute = compute_replay(db, body.city_code, body.valid_date, body.threshold_code)
    if compute is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if compute["data_status"] != "COMPLETE":
        raise HTTPException(status_code=409, detail="PARTIAL_DATA")

    threshold = _get_threshold(db, body.threshold_code)
    fusion_run = FusionRun(
        algorithm_version="v1",
        method="EQUAL_MEAN",
        lead_hours=24,
        weights_json={m: 0.25 for m in DEFAULT_MODELS},
        input_count=len(DEFAULT_MODELS),
        status="SUCCESS",
        executed_at=_now(),
        created_by=current.id,
    )
    db.add(fusion_run)
    db.flush()

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

    warning = Warning(
        public_id=new_public_id(),
        warning_result_id=result.id,
        hazard_type="RAINSTORM",
        created_by=current.id,
        status="DRAFT",
        title=body.title,
        area_text=body.area_text,
        impact_text=body.impact_text,
        reasoning_text=body.reasoning_text,
    )
    db.add(warning)
    add_audit(
        db,
        action="WARNING_CREATE",
        resource_type="warning",
        resource_id=warning.public_id,
        result="SUCCESS",
        actor_id=current.id,
        actor_role=",".join(current.roles),
        ip_address=client_ip(request), request_id=request_id(request),
    )
    db.commit()
    db.refresh(warning)
    return _to_out(db, warning)


WARNING_STATUSES = {
    "DRAFT",
    "PENDING_REVIEW",
    "APPROVED",
    "PUBLISHED",
    "WITHDRAWN",
    "REJECTED",
}


@router.get("/warnings", response_model=list[WarningOut])
def list_warnings(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    if status is not None and status not in WARNING_STATUSES:
        raise HTTPException(status_code=400, detail="INVALID_PARAMETER")
    stmt = select(Warning)
    if _viewer_only(current):
        if status is not None and status != "PUBLISHED":
            return []
        stmt = stmt.where(Warning.status == "PUBLISHED")
    elif status is not None:
        stmt = stmt.where(Warning.status == status)
    stmt = stmt.order_by(Warning.id.desc())
    warnings = db.scalars(stmt).all()
    uids = {w.created_by for w in warnings}
    username_map = {u.id: u.username for u in db.scalars(select(User).where(User.id.in_(uids))).all()}
    return [_to_out(db, w, username_map) for w in warnings]


@router.get("/warnings/{public_id}", response_model=WarningOut)
def get_warning(
    public_id: str,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    w = _get_warning(db, public_id)
    if w is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if _viewer_only(current) and w.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return _to_out(db, w)


@router.patch("/warnings/{public_id}", response_model=WarningOut)
def update_warning(
    public_id: str,
    body: WarningUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require_roles(ROLE_ANALYST, ROLE_ADMIN)),
):
    w = _get_warning(db, public_id, lock=True)
    if w is None or w.created_by != current.id or w.status not in ("DRAFT", "REJECTED"):
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(w, field, value)
    add_audit(
        db, action="WARNING_UPDATE", resource_type="warning", resource_id=w.public_id,
        result="SUCCESS", actor_id=current.id, actor_role=",".join(current.roles),
        ip_address=client_ip(request), request_id=request_id(request),
    )
    db.commit()
    db.refresh(w)
    return _to_out(db, w)


@router.post("/warnings/{public_id}/submit", response_model=WarningOut)
def submit_warning(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require_roles(ROLE_ANALYST, ROLE_ADMIN)),
):
    w = _get_warning(db, public_id, lock=True)
    if w is None or w.created_by != current.id or w.status not in ("DRAFT", "REJECTED"):
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    w.status = "PENDING_REVIEW"
    w.submitted_at = _now()
    add_audit(
        db, action="WARNING_SUBMIT", resource_type="warning", resource_id=w.public_id,
        result="SUCCESS", actor_id=current.id, actor_role=",".join(current.roles),
        ip_address=client_ip(request), request_id=request_id(request),
    )
    db.commit()
    db.refresh(w)
    return _to_out(db, w)


@router.post("/warnings/{public_id}/review", response_model=ReviewOut)
def review_warning(
    public_id: str,
    body: ReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require_roles(ROLE_REVIEWER, ROLE_ADMIN)),
):
    w = _get_warning(db, public_id, lock=True)
    if w is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if w.created_by == current.id:
        raise HTTPException(status_code=403, detail="SELF_REVIEW_FORBIDDEN")
    if w.status != "PENDING_REVIEW":
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    if body.decision == "REJECT" and not body.comment.strip():
        raise HTTPException(status_code=422, detail="REJECT_REQUIRES_COMMENT")

    if body.decision == "APPROVE":
        w.status = "APPROVED"
        w.approved_at = _now()
    else:
        w.status = "REJECTED"

    db.add(WarningReview(warning_id=w.id, reviewer_id=current.id, decision=body.decision, comment=body.comment))
    add_audit(
        db, action="WARNING_REVIEW", resource_type="warning", resource_id=w.public_id,
        result="SUCCESS", actor_id=current.id, actor_role=",".join(current.roles),
        reason=body.decision, ip_address=client_ip(request), request_id=request_id(request),
    )
    db.commit()
    return ReviewOut(
        decision=body.decision,
        comment=body.comment,
        reviewer=current.username,
        created_at=_now(),
    )


@router.post("/warnings/{public_id}/publish", response_model=WarningOut)
def publish_warning(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require_roles(ROLE_REVIEWER, ROLE_ADMIN)),
):
    w = _get_warning(db, public_id, lock=True)
    if w is None or w.status != "APPROVED":
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    w.status = "PUBLISHED"
    w.published_at = _now()
    w.published_by = current.id
    add_audit(
        db, action="WARNING_PUBLISH", resource_type="warning", resource_id=w.public_id,
        result="SUCCESS", actor_id=current.id, actor_role=",".join(current.roles),
        ip_address=client_ip(request), request_id=request_id(request),
    )
    db.commit()
    db.refresh(w)
    return _to_out(db, w)


@router.post("/warnings/{public_id}/withdraw", response_model=WarningOut)
def withdraw_warning(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require_roles(ROLE_REVIEWER, ROLE_ADMIN)),
):
    w = _get_warning(db, public_id, lock=True)
    if w is None or w.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    w.status = "WITHDRAWN"
    w.withdrawn_at = _now()
    w.withdrawn_by = current.id
    add_audit(
        db, action="WARNING_WITHDRAW", resource_type="warning", resource_id=w.public_id,
        result="SUCCESS", actor_id=current.id, actor_role=",".join(current.roles),
        ip_address=client_ip(request), request_id=request_id(request),
    )
    db.commit()
    db.refresh(w)
    return _to_out(db, w)


@router.post("/warnings/{public_id}/feedback", response_model=FeedbackOut)
def add_feedback(
    public_id: str,
    body: FeedbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(require_roles(ROLE_ANALYST, ROLE_ADMIN)),
):
    w = _get_warning(db, public_id)
    if w is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if w.status not in ("PUBLISHED", "WITHDRAWN"):
        raise HTTPException(status_code=409, detail="INVALID_STATE")
    fb = WarningFeedback(
        warning_id=w.id, created_by=current.id, response_status=body.response_status, content=body.content
    )
    db.add(fb)
    add_audit(
        db, action="WARNING_FEEDBACK", resource_type="warning", resource_id=w.public_id,
        result="SUCCESS", actor_id=current.id, actor_role=",".join(current.roles),
        ip_address=client_ip(request), request_id=request_id(request),
    )
    db.commit()
    db.refresh(fb)
    return FeedbackOut(
        response_status=fb.response_status, content=fb.content, created_by=current.username, created_at=fb.created_at
    )


@router.get("/warnings/{public_id}/feedback", response_model=list[FeedbackOut])
def list_feedback(
    public_id: str,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    w = _get_warning(db, public_id)
    if w is None:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if _viewer_only(current) and w.status != "PUBLISHED":
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    rows = db.scalars(select(WarningFeedback).where(WarningFeedback.warning_id == w.id)).all()
    return [
        FeedbackOut(
            response_status=r.response_status,
            content=r.content,
            created_by=_username(db, r.created_by),
            created_at=r.created_at,
        )
        for r in rows
    ]
