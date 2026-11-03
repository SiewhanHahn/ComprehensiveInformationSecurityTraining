"""subscriptions, in-app notifications and response task tables

Revision ID: 0005_subscriptions_notifications
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0005_subscriptions_notifications"
down_revision: Union[str, None] = "0004_dataset_issues"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BIGINT = mysql.BIGINT(unsigned=True)
DT = mysql.DATETIME(fsp=6)

NOW = sa.text("CURRENT_TIMESTAMP(6)")


def upgrade() -> None:
    # 订阅用哨兵值表达「全部」（hazard_type='*'、city_code=''）而不是 NULL：
    # MySQL 唯一索引把 NULL 视为互不相等，用 NULL 会让同一人重复插入同样的订阅。
    op.create_table(
        "warning_subscriptions",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", BIGINT, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("hazard_type", sa.String(32), nullable=False, server_default=sa.text("'*'")),
        sa.Column("city_code", sa.String(32), nullable=False, server_default=sa.text("''")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", DT, nullable=False, server_default=NOW),
        sa.Column("updated_at", DT, nullable=False, server_default=NOW),
        sa.UniqueConstraint("user_id", "hazard_type", "city_code", name="uq_subscription_scope"),
    )

    # dedupe_key 唯一索引是定时扫描幂等的保证：同一 (预警, 用户, 种类) 只会有一条通知。
    op.create_table(
        "notifications",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("user_id", BIGINT, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(1000), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False, server_default=sa.text("'warning'")),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("dedupe_key", sa.String(160), nullable=True),
        sa.Column("read_at", DT, nullable=True),
        sa.Column("created_at", DT, nullable=False, server_default=NOW),
        sa.UniqueConstraint("dedupe_key", name="uq_notifications_dedupe"),
    )
    op.create_index("idx_notifications_user_created", "notifications", ["user_id", "created_at"])
    op.create_index("idx_notifications_user_read", "notifications", ["user_id", "read_at"])

    # 响应任务表本阶段只建表（B 档第二刀实现分配、处置时限与超时升级）。
    op.create_table(
        "response_tasks",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True),
        sa.Column("warning_id", BIGINT, sa.ForeignKey("warnings.id"), nullable=False),
        sa.Column("assignee_id", BIGINT, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by", BIGINT, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("due_at", DT, nullable=False),
        sa.Column("acked_at", DT, nullable=True),
        sa.Column("completed_at", DT, nullable=True),
        sa.Column("escalated_at", DT, nullable=True),
        sa.Column("escalation_level", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("created_at", DT, nullable=False, server_default=NOW),
        sa.Column("updated_at", DT, nullable=False, server_default=NOW),
    )
    op.create_index("idx_response_tasks_due", "response_tasks", ["status", "due_at"])
    op.create_index("idx_response_tasks_assignee", "response_tasks", ["assignee_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_response_tasks_assignee", table_name="response_tasks")
    op.drop_index("idx_response_tasks_due", table_name="response_tasks")
    op.drop_table("response_tasks")

    op.drop_index("idx_notifications_user_read", table_name="notifications")
    op.drop_index("idx_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")

    op.drop_table("warning_subscriptions")
