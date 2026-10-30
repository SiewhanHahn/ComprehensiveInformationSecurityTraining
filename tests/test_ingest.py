"""导入校验与数据质量记录（FR-03）。需要 RUN_INTEGRATION=1。"""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from conftest import COMPLETE_DAY

pytestmark = pytest.mark.integration


def _source_id(session, code):
    from sqlalchemy import select

    from backend.app.models import DataSource

    return session.scalar(select(DataSource.id).where(DataSource.code == code))


def _cleanup_dataset(session, version):
    from sqlalchemy import delete, select

    from backend.app.models import Dataset, DatasetIssue, ForecastRecord, ObservationRecord

    ids = list(session.scalars(select(Dataset.id).where(Dataset.version == version)).all())
    if not ids:
        return
    session.execute(delete(DatasetIssue).where(DatasetIssue.dataset_id.in_(ids)))
    session.execute(delete(ForecastRecord).where(ForecastRecord.dataset_id.in_(ids)))
    session.execute(delete(ObservationRecord).where(ObservationRecord.dataset_id.in_(ids)))
    session.execute(delete(Dataset).where(Dataset.id.in_(ids)))
    session.commit()


def _sample_days():
    # 三个有效日：一个缺 GEM，一个含未知城市，一个含异常值
    return [
        {**COMPLETE_DAY, "valid_date": "2024-01-01", "models": {
            "ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": None,
        }, "proxy_label_mm": 10.0},
        {"city_code": "ATLANTIS", "valid_date": "2024-01-02", "models": {
            "ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0,
        }, "proxy_label_mm": 10.0},
        {"city_code": "WUHAN", "valid_date": "2024-01-03", "models": {
            "ecmwf_ifs025": -5.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0,
        }, "proxy_label_mm": 10.0},
    ]


def test_import_records_issues_and_sets_metadata():
    from backend.app.db import SessionLocal
    from backend.app.services import ingest

    version = f"test_ingest_{uuid4().hex}"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"version": version, "days": _sample_days()}, f)
        path = Path(f.name)

    try:
        with SessionLocal() as session:
            fc = _source_id(session, "OPEN_METEO_PREVIOUS_RUNS")
            obs = _source_id(session, "OPEN_METEO_ERA5")
            result = ingest.import_sample(session, path, fc, obs)

        assert result["imported"] is True
        # 缺 GEM、未知城市、负值各记一条问题；有效预报 3+3=6 条（第 1 天缺 GEM、
        # 第 3 天 ECMWF 为负值，各少一条）
        assert result["issues"] == 3

        from sqlalchemy import func, select

        from backend.app.models import Dataset, DatasetIssue, ForecastRecord

        with SessionLocal() as session:
            fc_ds = session.scalar(select(Dataset).where(Dataset.dataset_type == "FORECAST", Dataset.version == version))
            assert fc_ds.quality_status == "PARTIAL"
            assert fc_ds.row_count == 6
            assert len(fc_ds.checksum) == 64

            issues = {i.issue_type for i in session.scalars(select(DatasetIssue).where(DatasetIssue.dataset_id == fc_ds.id)).all()}
            assert issues == {"MISSING_MODEL", "UNKNOWN_CITY", "INVALID_VALUE"}

            # 未知城市/负值/缺测都没有落库
            cities = session.scalars(select(ForecastRecord.city_code).where(ForecastRecord.dataset_id == fc_ds.id)).all()
            assert "ATLANTIS" not in cities
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)


def test_import_is_idempotent():
    from backend.app.db import SessionLocal
    from backend.app.services import ingest

    version = f"test_ingest_idem_{uuid4().hex}"
    days = [{**COMPLETE_DAY, "valid_date": "2024-01-01", "models": {
        "ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0,
    }, "proxy_label_mm": 10.0}]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"version": version, "days": days}, f)
        path = Path(f.name)

    try:
        with SessionLocal() as session:
            fc = _source_id(session, "OPEN_METEO_PREVIOUS_RUNS")
            obs = _source_id(session, "OPEN_METEO_ERA5")
            first = ingest.import_sample(session, path, fc, obs)
        assert first["imported"] is True

        with SessionLocal() as session:
            fc = _source_id(session, "OPEN_METEO_PREVIOUS_RUNS")
            obs = _source_id(session, "OPEN_METEO_ERA5")
            second = ingest.import_sample(session, path, fc, obs)
        assert second["imported"] is False
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)
