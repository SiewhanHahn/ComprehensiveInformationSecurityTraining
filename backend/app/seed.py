"""幂等初始化：角色、数据源、教学阈值、演示账号，以及离线回放样本导入。

用法：python -m backend.app.seed [--sample data/sample/replay_sample.json]
演示账号密码从环境变量注入，不写死默认密码：
  DEMO_ADMIN_PASSWORD / DEMO_ANALYST_PASSWORD / DEMO_REVIEWER_PASSWORD / DEMO_VIEWER_PASSWORD
未设置对应密码时跳过该账号并打印提示。
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import (
    DataSource,
    Dataset,
    ForecastRecord,
    ObservationRecord,
    Role,
    User,
    UserRole,
    WarningThreshold,
)
from .security import hash_password

ROLES = {
    "ADMIN": "系统管理员",
    "ANALYST": "气象分析员",
    "REVIEWER": "预警审核员",
    "VIEWER": "普通查看用户",
}

SOURCES = {
    "OPEN_METEO_PREVIOUS_RUNS": (
        "Open-Meteo Previous Runs",
        "FORECAST",
        "https://previous-runs-api.open-meteo.com/v1/forecast",
        "CC-BY 4.0",
    ),
    "OPEN_METEO_ERA5": (
        "Open-Meteo ERA5",
        "REANALYSIS",
        "https://archive-api.open-meteo.com/v1/archive",
        "CC-BY 4.0（再分析，代理标签）",
    ),
    "NOAA_GHCN_DAILY": (
        "NOAA GHCN-Daily",
        "OBSERVATION",
        "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/",
        "公开数据，独立交叉验证",
    ),
}

THRESHOLDS = (
    ("MODERATE", Decimal("10"), "BLUE"),
    ("HEAVY", Decimal("25"), "YELLOW"),
    ("STORM", Decimal("50"), "ORANGE"),
)

DEMO_ACCOUNTS = (
    ("admin_demo", "系统管理员", "ADMIN", "DEMO_ADMIN_PASSWORD"),
    ("analyst_demo", "气象分析员", "ANALYST", "DEMO_ANALYST_PASSWORD"),
    ("reviewer_demo", "预警审核员", "REVIEWER", "DEMO_REVIEWER_PASSWORD"),
    ("viewer_demo", "普通查看用户", "VIEWER", "DEMO_VIEWER_PASSWORD"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_reference_data(session: Session) -> None:
    for code, name in ROLES.items():
        if session.scalar(select(Role).where(Role.code == code)) is None:
            session.add(Role(code=code, name=name, created_at=_now()))
    for code, (name, data_type, endpoint, license_note) in SOURCES.items():
        if session.scalar(select(DataSource).where(DataSource.code == code)) is None:
            session.add(
                DataSource(
                    code=code,
                    name=name,
                    data_type=data_type,
                    endpoint=endpoint,
                    license_note=license_note,
                    is_active=True,
                    created_at=_now(),
                )
            )
    for code, threshold_mm, level in THRESHOLDS:
        exists = session.scalar(
            select(WarningThreshold).where(
                WarningThreshold.hazard_type == "RAINSTORM", WarningThreshold.code == code
            )
        )
        if exists is None:
            session.add(
                WarningThreshold(
                    hazard_type="RAINSTORM",
                    code=code,
                    threshold_mm=threshold_mm,
                    level=level,
                    is_active=True,
                )
            )
    session.commit()


def seed_users(session: Session) -> None:
    for username, display_name, role_code, env_var in DEMO_ACCOUNTS:
        password = os.environ.get(env_var)
        if not password:
            print(f"[seed] 跳过账号 {username}（未设置 {env_var}）")
            continue
        role = session.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            print(f"[seed] 跳过账号 {username}（角色 {role_code} 不存在）")
            continue
        user = session.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, display_name=display_name, password_hash=hash_password(password), is_active=True)
            session.add(user)
            session.flush()
            session.add(UserRole(user_id=user.id, role_id=role.id, granted_at=_now()))
        else:
            # 幂等更新：同步密码哈希与启用状态，并补齐角色关联
            user.password_hash = hash_password(password)
            user.is_active = True
            session.execute(
                UserRole.__table__.insert().prefix_with("IGNORE").values(
                    user_id=user.id, role_id=role.id, granted_at=_now()
                )
            )
    session.commit()


def _source_id(session: Session, code: str) -> int:
    return session.scalar(select(DataSource.id).where(DataSource.code == code))


def import_sample(session: Session, path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version", "sample")
    days = data.get("days", [])

    if not days:
        print("[seed] 样本为空，跳过导入")
        return

    existing = session.scalar(
        select(Dataset).where(Dataset.dataset_type == "FORECAST", Dataset.version == version)
    )
    if existing is not None:
        print(f"[seed] 样本 {version} 已导入，跳过")
        return

    dates = sorted({date.fromisoformat(d["valid_date"]) for d in days})
    fc_source = _source_id(session, "OPEN_METEO_PREVIOUS_RUNS")
    obs_source = _source_id(session, "OPEN_METEO_ERA5")

    fc_dataset = Dataset(
        source_id=fc_source,
        dataset_type="FORECAST",
        version=version,
        period_start=dates[0],
        period_end=dates[-1],
        quality_status="READY",
        imported_at=_now(),
    )
    obs_dataset = Dataset(
        source_id=obs_source,
        dataset_type="ERA5_LABEL",
        version=version,
        period_start=dates[0],
        period_end=dates[-1],
        quality_status="READY",
        imported_at=_now(),
    )
    session.add_all([fc_dataset, obs_dataset])
    session.flush()

    n_fc = 0
    n_obs = 0
    for d in days:
        city = d["city_code"]
        day = date.fromisoformat(d["valid_date"])
        valid_at = datetime(day.year, day.month, day.day)
        models = d.get("models", {})
        for model_code, mm in models.items():
            if mm is None:
                continue
            session.add(
                ForecastRecord(
                    dataset_id=fc_dataset.id,
                    city_code=city,
                    model_code=model_code,
                    valid_at=valid_at,
                    lead_hours=24,
                    precipitation_mm=Decimal(str(mm)),
                    is_complete=True,
                )
            )
            n_fc += 1
        if d.get("proxy_label_mm") is not None:
            session.add(
                ObservationRecord(
                    dataset_id=obs_dataset.id,
                    city_code=city,
                    observation_type="ERA5_PROXY",
                    observed_date=day,
                    precipitation_mm=Decimal(str(d["proxy_label_mm"])),
                    quality_flag="OK",
                )
            )
            n_obs += 1
    session.commit()
    print(f"[seed] 导入 {n_fc} 条预报记录、{n_obs} 条代理标签记录")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default="data/sample/replay_sample.json")
    args = parser.parse_args()

    with SessionLocal() as session:
        seed_reference_data(session)
        import_sample(session, Path(args.sample))
        seed_users(session)
    print("[seed] 完成")


if __name__ == "__main__":
    main()
