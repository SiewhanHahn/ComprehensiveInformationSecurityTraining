from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .deps import ROLE_ADMIN, ROLE_ANALYST, ROLE_REVIEWER, ROLE_VIEWER


# ---- auth ----
class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUser(BaseModel):
    id: int
    username: str
    display_name: str
    roles: list[str]


class AuthResponse(BaseModel):
    user: AuthUser
    csrf_token: str


class MeResponse(BaseModel):
    user: AuthUser


RoleCode = Literal["ADMIN", "ANALYST", "REVIEWER", "VIEWER"]


class UserRolesUpdate(BaseModel):
    roles: list[RoleCode] = Field(min_length=1, max_length=4)

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value: list[RoleCode]) -> list[RoleCode]:
        return sorted(set(value))


class UserPasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def nonblank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("密码不能为空白")
        return value


class UserCreate(UserRolesUpdate, UserPasswordReset):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_display_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class UserStatusUpdate(BaseModel):
    is_active: bool = Field(strict=True)


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    is_active: bool
    roles: list[RoleCode]


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


# ---- replay ----
class CityOut(BaseModel):
    code: str
    name: str


class ModelValue(BaseModel):
    model: str
    precipitation_mm: float | None


class ThresholdOut(BaseModel):
    code: str
    threshold_mm: float
    level: str


class ReplaySource(BaseModel):
    dataset_version: str
    cached_at: datetime | None = None


class ReplayOut(BaseModel):
    replay_id: str
    city: CityOut
    valid_date: date
    threshold: ThresholdOut
    models: list[ModelValue]
    fused_mm: float | None
    baseline_mm: float | None
    proxy_label_mm: float | None
    risk_level: str | None
    data_status: str
    source: ReplaySource


# ---- metrics ----
class ExperimentListItem(BaseModel):
    version: str
    threshold_mm: float
    test_years: list[str]
    n: int
    positives: int
    delta_f1: float | None = None


class MetricBundle(BaseModel):
    precision: float
    recall: float
    fpr: float
    f1: float
    auc: float
    tp: int
    fp: int
    fn: int
    tn: int


class ExperimentDetail(BaseModel):
    version: str
    threshold_mm: float
    test_years: list[str]
    sites: list[str]
    n: int
    positives: int
    baseline: MetricBundle
    fusion: MetricBundle
    delta_f1: float
    bootstrap_interval: list[float]
    p_improve: float
    label_note: str


# ---- warnings ----
class WarningCreate(BaseModel):
    city_code: str
    valid_date: date
    threshold_code: str
    title: str = Field(max_length=200)
    area_text: str = Field(max_length=500)
    impact_text: str | None = Field(default=None, max_length=2000)
    reasoning_text: str

    @field_validator("title", "area_text", "reasoning_text")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("必填字段不能为空")
        return v

    @field_validator("impact_text")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class WarningUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    area_text: str | None = Field(default=None, max_length=500)
    impact_text: str | None = Field(default=None, max_length=2000)
    reasoning_text: str | None = None

    @field_validator("title", "area_text", "reasoning_text")
    @classmethod
    def _strip_required_if_provided(cls, v: str | None) -> str | None:
        # 字段被显式提供时必须非空；未提供时校验器不会执行，保持“不修改”
        if v is None:
            raise ValueError("必填字段不能为空")
        v = v.strip()
        if not v:
            raise ValueError("必填字段不能为空")
        return v

    @field_validator("impact_text")
    @classmethod
    def _strip_optional_update(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ReviewRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    # 批准可不填意见；驳回必须填写（在端点内校验）
    comment: str = Field(max_length=1000)

    @field_validator("comment")
    @classmethod
    def _strip_comment(cls, v: str) -> str:
        return v.strip()


class FeedbackRequest(BaseModel):
    response_status: str = Field(pattern="^(RECEIVED|PROCESSING|COMPLETED)$")
    content: str = Field(max_length=2000)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("反馈内容不能为空")
        return v


class WarningOut(BaseModel):
    public_id: str
    hazard_type: str
    status: str
    title: str
    area_text: str
    impact_text: str | None
    reasoning_text: str
    city_code: str
    valid_date: date
    risk_level: str | None
    fused_mm: float
    version_no: int
    created_by: str
    submitted_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    withdrawn_at: datetime | None


class ReviewOut(BaseModel):
    decision: str
    comment: str
    reviewer: str
    created_at: datetime


class FeedbackOut(BaseModel):
    response_status: str
    content: str
    created_by: str
    created_at: datetime


class AuditOut(BaseModel):
    id: int
    actor_id: int | None
    actor_role: str | None
    action: str
    resource_type: str
    resource_id: str | None
    result: str
    reason: str | None
    ip_address: str | None
    created_at: datetime
