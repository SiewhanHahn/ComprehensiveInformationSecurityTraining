"""预警接口：参数、鉴权与序列化；业务规则见 ``services/warnings.py``。"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER, CurrentUser, get_current_user, require_roles
from ..schemas import (
    FeedbackOut,
    FeedbackRequest,
    ReviewOut,
    ReviewRequest,
    WarningCreate,
    WarningOut,
    WarningUpdate,
)
from ..services import warnings as svc
from ..services.audit import audit_context

router = APIRouter()

analyst_required = require_roles(ROLE_ANALYST, ROLE_ADMIN)
reviewer_required = require_roles(ROLE_REVIEWER, ROLE_ADMIN)


def _respond(db: Session, w) -> WarningOut:
    db.commit()
    db.refresh(w)
    return svc.to_out(w, svc.usernames(db, {w.created_by}))


@router.post("/warnings", response_model=WarningOut)
def create_warning(
    body: WarningCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(analyst_required),
):
    w = svc.create_warning(db, body, current, audit_context(request, db, current))
    return _respond(db, w)


@router.get("/warnings", response_model=list[WarningOut])
def list_warnings(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    return svc.to_out_list(db, svc.list_warnings(db, current, status))


@router.get("/warnings/{public_id}", response_model=WarningOut)
def get_warning(
    public_id: str,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    w = svc.get_visible_warning(db, public_id, current)
    return svc.to_out(w, svc.usernames(db, {w.created_by}))


@router.patch("/warnings/{public_id}", response_model=WarningOut)
def update_warning(
    public_id: str,
    body: WarningUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(analyst_required),
):
    w = svc.update_warning(db, public_id, body, current, audit_context(request, db, current))
    return _respond(db, w)


@router.post("/warnings/{public_id}/submit", response_model=WarningOut)
def submit_warning(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(analyst_required),
):
    w = svc.submit_warning(db, public_id, current, audit_context(request, db, current))
    return _respond(db, w)


@router.post("/warnings/{public_id}/review", response_model=ReviewOut)
def review_warning(
    public_id: str,
    body: ReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(reviewer_required),
):
    review = svc.review_warning(db, public_id, body.decision, body.comment, current, audit_context(request, db, current))
    db.commit()
    return ReviewOut(
        decision=review.decision,
        comment=review.comment,
        reviewer=current.username,
        created_at=review.created_at,
    )


@router.post("/warnings/{public_id}/publish", response_model=WarningOut)
def publish_warning(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(reviewer_required),
):
    w = svc.publish_warning(db, public_id, current, audit_context(request, db, current))
    return _respond(db, w)


@router.post("/warnings/{public_id}/withdraw", response_model=WarningOut)
def withdraw_warning(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(reviewer_required),
):
    w = svc.withdraw_warning(db, public_id, current, audit_context(request, db, current))
    return _respond(db, w)


@router.post("/warnings/{public_id}/feedback", response_model=FeedbackOut)
def add_feedback(
    public_id: str,
    body: FeedbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(analyst_required),
):
    fb = svc.add_feedback(db, public_id, body, current, audit_context(request, db, current))
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
    w = svc.get_visible_warning(db, public_id, current)
    rows = svc.list_feedback(db, w)
    names = svc.usernames(db, {r.created_by for r in rows})
    return [
        FeedbackOut(
            response_status=r.response_status,
            content=r.content,
            created_by=names.get(r.created_by, str(r.created_by)),
            created_at=r.created_at,
        )
        for r in rows
    ]
