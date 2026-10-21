"""observation_records unique key by city (ERA5 proxy) instead of station

Revision ID: 0003_observation_unique_city
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_observation_unique_city"
down_revision: Union[str, None] = "0002_risk_level_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 先建 city_code 维度的唯一键，保证 FK dataset_id 始终有可用索引后再删旧键
    op.create_unique_constraint(
        "uq_obs_city_date_type",
        "observation_records",
        ["dataset_id", "city_code", "observed_date", "observation_type"],
    )
    op.drop_index("dataset_id", table_name="observation_records")


def downgrade() -> None:
    op.create_unique_constraint(
        "dataset_id",
        "observation_records",
        ["dataset_id", "station_code", "observed_date", "observation_type"],
    )
    op.drop_constraint("uq_obs_city_date_type", "observation_records", type_="unique")
