"""Allow source-backed non-rainfall evidence in the common warning-result row.

Revision ID: 0008_hazard_assessment
Revises: 0007_warning_lifecycle_audit
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0008_hazard_assessment"
down_revision = "0007_warning_lifecycle_audit"
branch_labels = None
depends_on = None

_LEGACY_COLUMNS = (("fusion_run_id", mysql.BIGINT(unsigned=True)),
                   ("threshold_id", mysql.BIGINT(unsigned=True)), ("fused_mm", sa.Numeric(10, 3)))
_ASSESSMENT_CHECK = """(assessment_json IS NULL AND fused_mm IS NOT NULL) OR
    (assessment_json IS NOT NULL AND JSON_TYPE(assessment_json) = 'OBJECT' AND
     fused_mm IS NULL AND baseline_mm IS NULL AND proxy_label_mm IS NULL)"""


def upgrade() -> None:
    op.add_column("warning_results", sa.Column("assessment_json", mysql.JSON(), nullable=True))
    for name, column_type in _LEGACY_COLUMNS:
        op.alter_column("warning_results", name, existing_type=column_type, existing_nullable=False, nullable=True)
    op.create_check_constraint("ck_warning_result_evidence", "warning_results", _ASSESSMENT_CHECK)


def downgrade() -> None:
    # Live writes must be stopped; MySQL DDL implicitly commits.
    if op.get_bind().scalar(sa.text("""
        SELECT EXISTS(SELECT 1 FROM warning_results WHERE assessment_json IS NOT NULL
            OR fused_mm IS NULL OR fusion_run_id IS NULL OR threshold_id IS NULL)
    """)):
        raise RuntimeError("0008 contains non-rainfall evidence; restore a pre-upgrade backup instead")
    op.drop_constraint("ck_warning_result_evidence", "warning_results", type_="check")
    for name, column_type in _LEGACY_COLUMNS:
        op.alter_column("warning_results", name, existing_type=column_type, existing_nullable=True, nullable=False)
    op.drop_column("warning_results", "assessment_json")
