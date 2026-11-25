"""Add storage for prior warning text without backfilling history.

Revision ID: 0009_warning_text_versions
Revises: 0008_hazard_assessment
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0009_warning_text_versions"
down_revision = "0008_hazard_assessment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warning_text_versions",
        sa.Column("warning_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("area_text", sa.String(500), nullable=False),
        sa.Column("impact_text", sa.Text(), nullable=True),
        sa.Column("reasoning_text", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("warning_id", "version_no"),
        sa.ForeignKeyConstraint(
            ["warning_id"], ["warnings.id"], name="fk_warning_text_versions_warning_id", ondelete="CASCADE"
        ),
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    # Stop writers for the entire check/drop window: MySQL DDL implicitly commits.
    if op.get_context().as_sql:
        raise RuntimeError("0009 downgrade requires a live emptiness check; stop writers and back up before retrying")
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM warning_text_versions)")):
        raise RuntimeError(
            "0009 downgrade refused: warning_text_versions contains history; "
            "stop writers and back up the current database. If rollback is required, restore a pre-upgrade backup."
        )
    op.drop_table("warning_text_versions")
