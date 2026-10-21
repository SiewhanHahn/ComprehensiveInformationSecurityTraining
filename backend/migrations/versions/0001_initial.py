"""initial weather warning schema (explicit DDL)

Revision ID: 0001_initial
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIGINT = mysql.BIGINT(unsigned=True)
DT = mysql.DATETIME(fsp=6)


def _ts_cols():
    return (
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("updated_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", DT, nullable=True),
        *_ts_cols(),
    )

    op.create_table(
        "roles",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", BIGINT, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", BIGINT, sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("granted_by", BIGINT, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("granted_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    op.create_table(
        "data_sources",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(512), nullable=True),
        sa.Column("license_note", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    op.create_table(
        "datasets",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("source_id", BIGINT, sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("dataset_type", sa.String(32), nullable=False),
        sa.Column("version", sa.String(100), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("quality_status", sa.String(32), nullable=False),
        sa.Column("imported_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.UniqueConstraint("source_id", "dataset_type", "version"),
    )

    op.create_table(
        "forecast_records",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("dataset_id", BIGINT, sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("city_code", sa.String(32), nullable=False),
        sa.Column("model_code", sa.String(32), nullable=False),
        sa.Column("valid_at", DT, nullable=False),
        sa.Column("lead_hours", sa.Integer(), nullable=False),
        sa.Column("precipitation_mm", sa.Numeric(10, 3), nullable=True),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.UniqueConstraint("dataset_id", "city_code", "model_code", "valid_at", "lead_hours"),
    )
    op.create_index("idx_forecast_lookup", "forecast_records", ["city_code", "valid_at", "lead_hours"])

    op.create_table(
        "observation_records",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("dataset_id", BIGINT, sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("city_code", sa.String(32), nullable=True),
        sa.Column("station_code", sa.String(64), nullable=True),
        sa.Column("observation_type", sa.String(32), nullable=False),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("precipitation_mm", sa.Numeric(10, 3), nullable=True),
        sa.Column("quality_flag", sa.String(32), nullable=True),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
        sa.UniqueConstraint("dataset_id", "station_code", "observed_date", "observation_type"),
    )

    op.create_table(
        "fusion_runs",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("lead_hours", sa.Integer(), nullable=False),
        sa.Column("weights_json", mysql.JSON(), nullable=False),
        sa.Column("input_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("executed_at", DT, nullable=False),
        sa.Column("created_by", BIGINT, sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "fusion_inputs",
        sa.Column("fusion_run_id", BIGINT, sa.ForeignKey("fusion_runs.id"), primary_key=True),
        sa.Column("forecast_record_id", BIGINT, sa.ForeignKey("forecast_records.id"), primary_key=True),
        sa.Column("model_code", sa.String(32), nullable=False),
        sa.Column("value_mm", sa.Numeric(10, 3), nullable=False),
    )

    op.create_table(
        "warning_thresholds",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("hazard_type", sa.String(32), nullable=False, server_default=sa.text("'RAINSTORM'")),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("threshold_mm", sa.Numeric(10, 3), nullable=False),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("hazard_type", "code"),
    )

    op.create_table(
        "warning_results",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("fusion_run_id", BIGINT, sa.ForeignKey("fusion_runs.id"), nullable=False),
        sa.Column("threshold_id", BIGINT, sa.ForeignKey("warning_thresholds.id"), nullable=False),
        sa.Column("city_code", sa.String(32), nullable=False),
        sa.Column("valid_date", sa.Date(), nullable=False),
        sa.Column("fused_mm", sa.Numeric(10, 3), nullable=False),
        sa.Column("baseline_mm", sa.Numeric(10, 3), nullable=True),
        sa.Column("proxy_label_mm", sa.Numeric(10, 3), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("data_status", sa.String(32), nullable=False),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    op.create_table(
        "warnings",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("public_id", sa.String(26), nullable=False, unique=True),
        sa.Column("warning_result_id", BIGINT, sa.ForeignKey("warning_results.id"), nullable=False),
        sa.Column("hazard_type", sa.String(32), nullable=False, server_default=sa.text("'RAINSTORM'")),
        sa.Column("created_by", BIGINT, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("area_text", sa.String(500), nullable=False),
        sa.Column("impact_text", sa.Text(), nullable=True),
        sa.Column("reasoning_text", sa.Text(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("submitted_at", DT, nullable=True),
        sa.Column("approved_at", DT, nullable=True),
        sa.Column("published_at", DT, nullable=True),
        sa.Column("withdrawn_at", DT, nullable=True),
        sa.Column("published_by", BIGINT, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("withdrawn_by", BIGINT, sa.ForeignKey("users.id"), nullable=True),
        *_ts_cols(),
    )

    op.create_table(
        "warning_reviews",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("warning_id", BIGINT, sa.ForeignKey("warnings.id"), nullable=False),
        sa.Column("reviewer_id", BIGINT, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(1000), nullable=False),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    op.create_table(
        "warning_feedback",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("warning_id", BIGINT, sa.ForeignKey("warnings.id"), nullable=False),
        sa.Column("created_by", BIGINT, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("response_status", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("actor_id", BIGINT, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )
    op.create_index("idx_audit_created_at", "audit_logs", ["created_at"])
    op.create_index("idx_audit_actor_created", "audit_logs", ["actor_id", "created_at"])
    op.create_index("idx_audit_resource", "audit_logs", ["resource_type", "resource_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_resource", table_name="audit_logs")
    op.drop_index("idx_audit_actor_created", table_name="audit_logs")
    op.drop_index("idx_audit_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("warning_feedback")
    op.drop_table("warning_reviews")
    op.drop_table("warnings")
    op.drop_table("warning_results")
    op.drop_table("warning_thresholds")
    op.drop_table("fusion_inputs")
    op.drop_table("fusion_runs")
    op.drop_table("observation_records")
    op.drop_index("idx_forecast_lookup", table_name="forecast_records")
    op.drop_table("forecast_records")
    op.drop_table("datasets")
    op.drop_table("data_sources")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
