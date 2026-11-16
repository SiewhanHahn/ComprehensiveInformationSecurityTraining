"""add idx_users_active index on users(is_active)

Revision ID: 0006_idx_users_active
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006_idx_users_active"
down_revision: Union[str, None] = "0005_subscriptions_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("idx_users_active", "users", ["is_active"])


def downgrade() -> None:
    op.drop_index("idx_users_active", table_name="users")
