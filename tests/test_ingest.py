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
    from sqlalchemy import select

    from backend.app.models import Dataset

    ids = list(session.scalars(select(Dataset.id).where(Dataset.version == version)).all())
    _cleanup_dataset_ids(session, ids)


def _cleanup_dataset_ids(session, ids):
    from sqlalchemy import delete

    from backend.app.models import Dataset, DatasetIssue, ForecastRecord, ObservationRecord

    ids = list(ids)
    if not ids:
        return
    session.execute(delete(DatasetIssue).where(DatasetIssue.dataset_id.in_(ids)))
    session.execute(delete(ForecastRecord).where(ForecastRecord.dataset_id.in_(ids)))
    session.execute(delete(ObservationRecord).where(ObservationRecord.dataset_id.in_(ids)))
    session.execute(delete(Dataset).where(Dataset.id.in_(ids)))
    session.commit()


def _max_dataset_id(session) -> int:
    from sqlalchemy import func, select

    from backend.app.models import Dataset

    return session.scalar(select(func.coalesce(func.max(Dataset.id), 0))) or 0


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
        [
            {**COMPLETE_DAY, "valid_date": "2024-01-05", "models": None, "proxy_label_mm": 5.0},
            {**COMPLETE_DAY, "valid_date": "2024-01-06", "models": {
                "ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0,
            }, "proxy_label_mm": 10.0},
        ]
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
        [
            {"city_code": "A" * 40, "valid_date": "2024-01-06", "models": {}, "proxy_label_mm": 5.0},
            {**COMPLETE_DAY, "valid_date": "2024-01-07", "models": {
                "ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0,
            }, "proxy_label_mm": 10.0},
        ]
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


def test_sample_without_days_is_marked_failed_not_ready():
    """结构坏掉的样本不能变成一个 0 行却 READY 的数据集——它会遮蔽真实数据。

    ``latest_dataset`` 只排除 FAILED，所以一个空 READY 数据集会成为「最新」，
    让所有回放变成 PARTIAL。
    """
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset, DatasetIssue
    from backend.app.services import ingest

    version = f"test_ingest_broken_{uuid4().hex}"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"version": version, "days": {}}, f)
        path = Path(f.name)
    try:
        with SessionLocal() as session:
            result = ingest.import_sample(
                session, path, _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"), _source_id(session, "OPEN_METEO_ERA5")
            )
        assert result["imported"] is False
        assert result.get("unusable") is True

        with SessionLocal() as session:
            dataset = session.scalar(
                select(Dataset).where(Dataset.dataset_type == "FORECAST", Dataset.version == version)
            )
            assert dataset is not None
            assert dataset.quality_status == "FAILED"
            assert dataset.row_count == 0
            issues = session.scalars(
                select(DatasetIssue).where(DatasetIssue.dataset_id == dataset.id)
            ).all()
            assert [i.issue_type for i in issues] == ["INVALID_VALUE"]
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


def _import_days_with_version(version, days):
    from backend.app.db import SessionLocal
    from backend.app.services import ingest

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"version": version, "days": days}, f)
        path = Path(f.name)
    try:
        with SessionLocal() as session:
            return ingest.import_sample(
                session,
                path,
                _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"),
                _source_id(session, "OPEN_METEO_ERA5"),
            )
    finally:
        path.unlink(missing_ok=True)


def test_all_rejected_days_mark_forecast_failed():
    """非空 days 但全部条目无效时，0 行数据集必须 FAILED，不能遮蔽旧数据。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset

    version = f"test_ingest_rejected_{uuid4().hex}"
    result = _import_days_with_version(
        version,
        [{"city_code": "ATLANTIS", "valid_date": "2024-02-01", "models": {}, "proxy_label_mm": 10.0}],
    )
    try:
        assert result["imported"] is True
        assert result["forecast"] == 0
        assert result.get("unusable") is True
        with SessionLocal() as session:
            fc_ds = session.scalar(
                select(Dataset).where(
                    Dataset.dataset_type == "FORECAST",
                    Dataset.source_id == _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"),
                    Dataset.version == version,
                )
            )
            assert fc_ds.quality_status == "FAILED"
            assert fc_ds.row_count == 0
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)


def test_failed_version_can_be_reimported():
    """坏样本把版本标成 FAILED 后，修正文件用同一版本重导必须成功。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset

    version = f"test_ingest_repair_{uuid4().hex}"
    first = _import_days_with_version(
        version,
        [{"city_code": "ATLANTIS", "valid_date": "2024-02-02", "models": {}, "proxy_label_mm": 10.0}],
    )
    assert first.get("unusable") is True
    with SessionLocal() as session:
        first_ds = session.scalar(
            select(Dataset).where(
                Dataset.dataset_type == "FORECAST",
                Dataset.source_id == _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"),
                Dataset.version == version,
            )
        )
        assert first_ds is not None
        assert first_ds.quality_status == "FAILED"
        first_id = first_ds.id
    models = {"ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0}
    second = _import_days_with_version(
        version,
        [{"city_code": "WUHAN", "valid_date": "2024-02-03", "models": models, "proxy_label_mm": 10.0}],
    )
    try:
        assert second["imported"] is True
        assert second["forecast"] == 4
        with SessionLocal() as session:
            fc_ds = session.scalar(
                select(Dataset).where(
                    Dataset.dataset_type == "FORECAST",
                    Dataset.source_id == _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"),
                    Dataset.version == version,
                )
            )
            # 复用同一行（唯一约束不允许插第二条），而不是新建
            assert fc_ds.id == first_id
            assert fc_ds.quality_status == "READY"
            assert fc_ds.row_count == 4
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)


def test_era5_labels_can_be_repaired_at_same_version():
    """预报可用但标签缺失的版本补齐 proxy_label_mm 后，同版本重导要补上观测记录。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset

    version = f"test_ingest_labels_{uuid4().hex}"
    models = {"ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0}
    day = {"city_code": "WUHAN", "valid_date": "2024-05-01", "models": models}

    first = _import_days_with_version(version, [day])
    assert first["imported"] is True
    assert first["observation"] == 0
    with SessionLocal() as session:
        obs = session.scalar(
            select(Dataset).where(Dataset.dataset_type == "ERA5_LABEL", Dataset.version == version)
        )
        assert obs.quality_status == "FAILED"
        obs_id = obs.id

    second = _import_days_with_version(version, [{**day, "proxy_label_mm": 12.0}])
    try:
        assert second["imported"] is True
        assert second["observation"] == 1
        with SessionLocal() as session:
            obs = session.scalar(
                select(Dataset).where(Dataset.dataset_type == "ERA5_LABEL", Dataset.version == version)
            )
            assert obs.id == obs_id
            assert obs.quality_status == "READY"
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)


def test_non_object_sample_does_not_crash():
    """顶层不是 JSON 对象时记录 FAILED，而不是让 seed 抛异常退出。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset
    from backend.app.services import ingest

    with SessionLocal() as session:
        before = _max_dataset_id(session)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(["not", "an", "object"], f)
        path = Path(f.name)
    try:
        with SessionLocal() as session:
            result = ingest.import_sample(
                session,
                path,
                _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"),
                _source_id(session, "OPEN_METEO_ERA5"),
            )
        assert result["imported"] is False
        assert result.get("unusable") is True
        with SessionLocal() as session:
            sample_datasets = session.scalars(
                select(Dataset).where(Dataset.version == "sample")
            ).all()
            assert any(
                d.dataset_type == "FORECAST" and d.quality_status == "FAILED"
                for d in sample_datasets
            )
            new_ids = [d.id for d in sample_datasets if d.id > before]
            _cleanup_dataset_ids(session, new_ids)
    finally:
        path.unlink(missing_ok=True)


def test_malformed_json_marks_failed_without_raising():
    """截断/非 UTF-8 样本不能把 seed 打崩；应落成 FAILED 并记问题。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset
    from backend.app.services import ingest

    with SessionLocal() as session:
        before = _max_dataset_id(session)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        f.write("{not valid json")
        path = Path(f.name)
    try:
        with SessionLocal() as session:
            result = ingest.import_sample(
                session,
                path,
                _source_id(session, "OPEN_METEO_PREVIOUS_RUNS"),
                _source_id(session, "OPEN_METEO_ERA5"),
            )
        assert result["imported"] is False
        assert result.get("unusable") is True
        with SessionLocal() as session:
            sample_datasets = session.scalars(
                select(Dataset).where(Dataset.version == "sample")
            ).all()
            assert any(
                d.dataset_type == "FORECAST" and d.quality_status == "FAILED"
                for d in sample_datasets
            )
            _cleanup_dataset_ids(session, [d.id for d in sample_datasets if d.id > before])
    finally:
        path.unlink(missing_ok=True)


def test_non_string_city_code_records_issue():
    """list/dict 城市代码不可哈希，必须记问题而不是让导入崩溃。"""
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import Dataset, DatasetIssue

    version = f"test_ingest_citytype_{uuid4().hex}"
    models = {"ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0}
    result = _import_days_with_version(
        version,
        [
            {"city_code": ["WUHAN"], "valid_date": "2024-03-01", "models": models, "proxy_label_mm": 10.0},
            {"city_code": "WUHAN", "valid_date": "2024-03-02", "models": models, "proxy_label_mm": 10.0},
        ],
    )
    try:
        assert result["imported"] is True
        assert result["forecast"] == 4
        with SessionLocal() as session:
            fc_ds_id = session.scalar(
                select(Dataset.id).where(Dataset.dataset_type == "FORECAST", Dataset.version == version)
            )
            issue_types = set(
                session.scalars(
                    select(DatasetIssue.issue_type).where(DatasetIssue.dataset_id == fc_ds_id)
                ).all()
            )
            assert "UNKNOWN_CITY" in issue_types
    finally:
        with SessionLocal() as session:
            _cleanup_dataset(session, version)


def test_valid_duplicate_after_invalid_duplicate_is_kept():
    """全坏的条目不能占用 (city, date) 去重键，否则修正过的同日条目会被误丢。"""
    version = f"test_ingest_dup_{uuid4().hex}"
    models = {"ecmwf_ifs025": 10.0, "gfs_global": 10.0, "icon_global": 10.0, "gem_global": 10.0}
    result = _import_days_with_version(
        version,
        [
            {"city_code": "WUHAN", "valid_date": "2024-04-01", "models": None, "proxy_label_mm": None},
            {"city_code": "WUHAN", "valid_date": "2024-04-01", "models": models, "proxy_label_mm": 10.0},
        ],
    )
    try:
        assert result["imported"] is True
        assert result["forecast"] == 4
        assert result["observation"] == 1
    finally:
        from backend.app.db import SessionLocal

        with SessionLocal() as session:
            _cleanup_dataset(session, version)
