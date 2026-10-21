"""make warning_results.risk_level nullable

Revision ID: 0002_risk_level_nullable
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_risk_level_nullable"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "warning_results",
        "risk_level",
        existing_type=sa.String(16),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "warning_results",
        "risk_level",
        existing_type=sa.String(16),
        nullable=False,
    )
