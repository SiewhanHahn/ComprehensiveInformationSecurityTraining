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


def _import_days(days):
    """把给定 days 写成临时样本并导入，返回 (result, version)。调用方负责 _cleanup_dataset。"""
    from backend.app.db import SessionLocal
    from backend.app.services import ingest

    version = f"test_ingest_{uuid4().hex}"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"version": version, "days": days}, f)
        path = Path(f.name)
    try:
        with SessionLocal() as session:
            result = ingest.import_sample(
                session, path, _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"), _source_id(session, "OPEN_METEO_ERA5")
            )
        return result, version
    finally:
        path.unlink(missing_ok=True)


def _dataset_issues(version):
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset, DatasetIssue

    with SessionLocal() as session:
        dataset = session.scalar(
            select(Dataset).where(Dataset.dataset_type == "FORECAST", Dataset.version == version)
        )
        assert dataset is not None
        rows = session.scalars(select(DatasetIssue).where(DatasetIssue.dataset_id == dataset.id)).all()
        return dataset.quality_status, [(r.issue_type, r.city_code, r.model_code) for r in rows]


def test_models_null_is_recorded_not_fatal():
    """``"models": null`` 不能让整个导入抛 AttributeError。"""
    from backend.app.db import SessionLocal

    result, version = _import_days(
        [{**COMPLETE_DAY, "valid_date": "2024-01-05", "models": None, "proxy_label_mm": 5.0}]
    )
    try:
        assert result["imported"] is True
        status, issues = _dataset_issues(version)
        assert status == "PARTIAL"
        assert "INVALID_VALUE" in {row[0] for row in issues}
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)


def test_overlong_city_code_is_truncated_not_fatal():
    """超长城市名只截断写入 dataset_issues，不能让整个导入回滚。"""
    from backend.app.db import SessionLocal

    result, version = _import_days(
        [{"city_code": "A" * 40, "valid_date": "2024-01-06", "models": {}, "proxy_label_mm": 5.0}]
    )
    try:
        assert result["imported"] is True
        status, issues = _dataset_issues(version)
        assert status == "PARTIAL"
        unknown = [row for row in issues if row[0] == "UNKNOWN_CITY"]
        assert unknown and len(unknown[0][1]) == 32
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)


def test_absent_model_key_counts_as_missing():
    """整天少一个模式的键（而不是 null）同样要记账并标 PARTIAL。"""
    from backend.app.db import SessionLocal

    result, version = _import_days([{
        **COMPLETE_DAY,
        "valid_date": "2024-01-07",
        "models": {"ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0},
        "proxy_label_mm": 10.0,
    }])
    try:
        status, issues = _dataset_issues(version)
        assert status == "PARTIAL"
        assert ("MISSING_MODEL", COMPLETE_DAY["city_code"], "gem_global") in issues
        assert result["forecast"] == 3
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


def test_same_date_multiple_cities_are_not_duplicates():
    """同一日期不同城市是不同记录，不应被判为重复丢弃。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset, ForecastRecord
    from backend.app.services import ingest

    version = f"test_ingest_cities_{uuid4().hex}"
    models = {"ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0}
    days = [
        {"city_code": "WUHAN", "valid_date": "2024-01-05", "models": models, "proxy_label_mm": 10.0},
        {"city_code": "CHANGSHA", "valid_date": "2024-01-05", "models": models, "proxy_label_mm": 10.0},
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"version": version, "days": days}, f)
        path = Path(f.name)

    try:
        with SessionLocal() as session:
            fc = _source_id(session, "OPEN_METEO_PREVIOUS_RUNS")
            obs = _source_id(session, "OPEN_METEO_ERA5")
            result = ingest.import_sample(session, path, fc, obs)

        assert result["imported"] is True
        assert result["issues"] == 0
        assert result["forecast"] == 8

        with SessionLocal() as session:
            fc_ds = session.scalar(
                select(Dataset).where(Dataset.dataset_type == "FORECAST", Dataset.version == version)
            )
            assert fc_ds.quality_status == "READY"
            cities = set(
                session.scalars(
                    select(ForecastRecord.city_code).where(ForecastRecord.dataset_id == fc_ds.id)
                ).all()
            )
            assert cities == {"WUHAN", "CHANGSHA"}
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)
