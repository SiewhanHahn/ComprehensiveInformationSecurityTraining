"""dataset_issues table for import quality records

Revision ID: 0004_dataset_issues
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004_dataset_issues"
down_revision: Union[str, None] = "0003_observation_unique_city"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIGINT = mysql.BIGINT(unsigned=True)
DT = mysql.DATETIME(fsp=6)


def upgrade() -> None:
    op.create_table(
        "dataset_issues",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("dataset_id", BIGINT, sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("issue_type", sa.String(32), nullable=False),
        sa.Column("city_code", sa.String(32), nullable=True),
        sa.Column("model_code", sa.String(32), nullable=True),
        sa.Column("valid_date", sa.Date(), nullable=True),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("created_at", DT, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(6)")),
    )
    op.create_index("idx_dataset_issues_dataset", "dataset_issues", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("idx_dataset_issues_dataset", table_name="dataset_issues")
    op.drop_table("dataset_issues")
