"""add warning cancellation metadata and audit resource versions

Revision ID: 0007_warning_lifecycle_audit
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0007_warning_lifecycle_audit"
down_revision: Union[str, None] = "0006_idx_users_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIGINT = mysql.BIGINT(unsigned=True)
DT = mysql.DATETIME(fsp=6)


def upgrade() -> None:
    op.add_column("warnings", sa.Column("cancelled_at", DT, nullable=True))
    op.add_column("warnings", sa.Column("cancelled_by", BIGINT, nullable=True))
    op.create_foreign_key(
        "fk_warnings_cancelled_by_users",
        "warnings",
        "users",
        ["cancelled_by"],
        ["id"],
    )
    op.add_column("audit_logs", sa.Column("resource_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    # MySQL DDL commits implicitly. Check before the first ALTER, with writers stopped.
    if op.get_bind().scalar(sa.text("""
        SELECT EXISTS(SELECT 1 FROM warnings WHERE status='CANCELLED'
                      OR cancelled_at IS NOT NULL OR cancelled_by IS NOT NULL)
            OR EXISTS(SELECT 1 FROM audit_logs WHERE resource_version IS NOT NULL)
    """)):
        raise RuntimeError("0007 contains lifecycle/audit history; stop writers and restore a pre-upgrade backup instead")
    op.drop_constraint("fk_warnings_cancelled_by_users", "warnings", type_="foreignkey")
    op.drop_column("warnings", "cancelled_by")
    op.drop_column("warnings", "cancelled_at")
    op.drop_column("audit_logs", "resource_version")
