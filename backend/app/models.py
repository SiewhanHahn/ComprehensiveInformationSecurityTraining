from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6),
        nullable=False,
        default=_utcnow,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        onupdate=_utcnow,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles",
        primaryjoin="User.id == UserRole.user_id",
        secondaryjoin="UserRole.role_id == Role.id",
        viewonly=True,
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("roles.id"), primary_key=True)
    granted_by: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=True)
    granted_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    license_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("data_sources.id"), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (UniqueConstraint("source_id", "dataset_type", "version"),)


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("datasets.id"), nullable=False)
    city_code: Mapped[str] = mapped_column(String(32), nullable=False)
    model_code: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    lead_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )

    __table_args__ = (
        UniqueConstraint("dataset_id", "city_code", "model_code", "valid_at", "lead_hours"),
        Index("idx_forecast_lookup", "city_code", "valid_at", "lead_hours"),
    )


class ObservationRecord(Base):
    __tablename__ = "observation_records"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("datasets.id"), nullable=False)
    city_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    station_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    observed_date: Mapped[date] = mapped_column(Date, nullable=False)
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    quality_flag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "city_code", "observed_date", "observation_type",
            name="uq_obs_city_date_type",
        ),
    )


class FusionRun(Base):
    __tablename__ = "fusion_runs"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    lead_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    weights_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False)
    created_by: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=True)


class FusionInput(Base):
    __tablename__ = "fusion_inputs"

    fusion_run_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("fusion_runs.id"), primary_key=True
    )
    forecast_record_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("forecast_records.id"), primary_key=True
    )
    model_code: Mapped[str] = mapped_column(String(32), nullable=False)
    value_mm: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)


class WarningThreshold(Base):
    __tablename__ = "warning_thresholds"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    hazard_type: Mapped[str] = mapped_column(String(32), nullable=False, default="RAINSTORM", server_default=text("'RAINSTORM'"))
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold_mm: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))

    __table_args__ = (UniqueConstraint("hazard_type", "code"),)


class WarningResult(Base):
    __tablename__ = "warning_results"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    fusion_run_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("fusion_runs.id"), nullable=False)
    threshold_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("warning_thresholds.id"), nullable=False)
    city_code: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_date: Mapped[date] = mapped_column(Date, nullable=False)
    fused_mm: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    baseline_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    proxy_label_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    data_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class Warning(Base, TimestampMixin):
    __tablename__ = "warnings"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(26), unique=True, nullable=False)
    warning_result_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("warning_results.id"), nullable=False)
    hazard_type: Mapped[str] = mapped_column(String(32), nullable=False, default="RAINSTORM", server_default=text("'RAINSTORM'"))
    created_by: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    area_text: Mapped[str] = mapped_column(String(500), nullable=False)
    impact_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_text: Mapped[str] = mapped_column(Text, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    submitted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6), nullable=True)
    published_by: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=True)
    withdrawn_by: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=True)

    warning_result: Mapped["WarningResult"] = relationship(
        primaryjoin="Warning.warning_result_id == WarningResult.id",
        viewonly=True,
        lazy="selectin",
    )


class WarningReview(Base):
    __tablename__ = "warning_reviews"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    warning_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("warnings.id"), nullable=False)
    reviewer_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class WarningFeedback(Base):
    __tablename__ = "warning_feedback"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    warning_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("warnings.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=False)
    response_status: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), nullable=False, default=_utcnow, server_default=text("CURRENT_TIMESTAMP(6)")
    )

    __table_args__ = (
        Index("idx_audit_created_at", "created_at"),
        Index("idx_audit_actor_created", "actor_id", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )
