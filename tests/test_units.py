import json
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.app.cities import CITIES, DEFAULT_MODELS
from backend.app.deps import CurrentUser
from backend.app.models import WarningSubscription
from backend.app.services.subscriptions import matches
from backend.app.services.warnings import is_viewer_only
from backend.app.security import hash_password, new_public_id, verify_password
from backend.app.services.metrics import get_experiment, list_experiments

ROOT = Path(__file__).resolve().parent.parent


def test_password_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong", hashed)


def test_public_id_is_unguessable_length():
    ids = {new_public_id() for _ in range(100)}
    assert all(len(i) == 26 for i in ids)
    assert len(ids) == 100


def test_nine_cities_and_four_models():
    assert len(CITIES) == 9
    assert len(DEFAULT_MODELS) == 4


def test_frozen_metrics_main_result():
    detail = get_experiment("10mm")
    assert detail is not None
    assert detail.n == 2403
    assert detail.positives == 406
    assert detail.baseline.f1 == 0.7462
    assert detail.fusion.f1 == 0.79
    assert detail.delta_f1 == 4.38
    assert detail.bootstrap_interval == [1.57, 7.29]


def test_experiment_list_has_10_and_25():
    versions = {e.version for e in list_experiments()}
    assert {"10mm", "25mm"}.issubset(versions)


def test_offline_sample_structure():
    data = json.loads((ROOT / "data/sample/replay_sample.json").read_text(encoding="utf-8"))
    assert data["days"], "sample must not be empty"
    for day in data["days"]:
        assert day["city_code"] in CITIES
        assert day["valid_date"]
        assert set(day["models"]).issubset(set(DEFAULT_MODELS))
        assert day["proxy_label_mm"] is not None
    assert any(d["proxy_label_mm"] >= 25 for d in data["days"])
    assert any(d["proxy_label_mm"] < 10 for d in data["days"])


def test_viewer_only():
    assert is_viewer_only(CurrentUser(1, "v", ["VIEWER"]))
    assert is_viewer_only(CurrentUser(6, "norole", []))
    assert is_viewer_only(CurrentUser(7, "guest", ["GUEST"]))
    assert not is_viewer_only(CurrentUser(2, "a", ["ANALYST"]))
    assert not is_viewer_only(CurrentUser(3, "va", ["VIEWER", "ANALYST"]))
    assert not is_viewer_only(CurrentUser(4, "admin", ["ADMIN"]))
    assert not is_viewer_only(CurrentUser(5, "r", ["REVIEWER"]))


def test_login_request_rejects_oversized_credentials():
    import pytest
    from pydantic import ValidationError

    from backend.app.schemas import LoginRequest

    assert LoginRequest(username="", password="").username == ""
    assert LoginRequest(username="a" * 64, password="p" * 128).password == "p" * 128
    with pytest.raises(ValidationError):
        LoginRequest(username="a" * 65, password="secret")
    with pytest.raises(ValidationError):
        LoginRequest(username="admin_demo", password="p" * 129)


def test_subscription_matching():
    def sub(hazard_type, city_code):
        return WarningSubscription(hazard_type=hazard_type, city_code=city_code)

    # 两个维度各自「不限」或精确相等才投递
    assert matches(sub("*", ""), "RAINSTORM", "CHANGSHA")
    assert matches(sub("RAINSTORM", ""), "RAINSTORM", "CHANGSHA")
    assert matches(sub("*", "CHANGSHA"), "RAINSTORM", "CHANGSHA")
    assert matches(sub("RAINSTORM", "CHANGSHA"), "RAINSTORM", "CHANGSHA")
    assert not matches(sub("TYPHOON", ""), "RAINSTORM", "CHANGSHA")
    assert not matches(sub("RAINSTORM", "WUHAN"), "RAINSTORM", "CHANGSHA")
    assert not matches(sub("TYPHOON", "WUHAN"), "RAINSTORM", "CHANGSHA")


def test_seed_module_imports_and_builds_its_tables():
    """seed 是 compose 里的必经服务：导入期就崩会让新部署的 API 永远起不来。

    测试套件其余部分都不导入 seed，所以「模块级 NameError」这类问题
    只会在真正部署时才暴露——这里补一个最便宜的看门狗。
    """
    import importlib
    from decimal import Decimal

    seed = importlib.import_module("backend.app.seed")

    assert [row[0] for row in seed.THRESHOLDS] == ["MODERATE", "HEAVY", "STORM"]
    assert all(isinstance(row[1], Decimal) for row in seed.THRESHOLDS)
    assert set(seed.ROLES) == {"ADMIN", "ANALYST", "REVIEWER", "VIEWER"}


def test_csrf_comparison_survives_non_ascii():
    """compare_digest 对含非 ASCII 的 str 会抛 TypeError，必须按字节比较。"""
    from backend.app.main import csrf_matches

    assert csrf_matches("abc123", "abc123")
    assert not csrf_matches("abc123", "abc124")
    assert not csrf_matches(None, "abc123")
    assert not csrf_matches("abc123", None)
    assert not csrf_matches("café", "abc123")


def test_reasoning_text_checks_utf8_bytes_not_characters():
    """TEXT 列按字节计：20,000 个 4 字节字符仍会超过 65,535 字节。"""
    from datetime import date

    import pytest
    from pydantic import ValidationError

    from backend.app.schemas import WarningCreate, WarningUpdate

    base = dict(city_code="WUHAN", valid_date=date(2024, 1, 1), threshold_code="HEAVY", title="t", area_text="a", impact_text="i")
    with pytest.raises(ValidationError):
        WarningCreate(**base, reasoning_text="😀" * 20000)
    with pytest.raises(ValidationError):
        WarningUpdate(reasoning_text="😀" * 20000)
    # 中文按 3 字节计，20,000 字符 = 60,000 字节，仍在 TEXT 容量内
    assert WarningCreate(**base, reasoning_text="雨" * 20000).reasoning_text


def test_read_session_rejects_non_dict_and_session_expired_handles_tz(monkeypatch):
    from datetime import datetime, timezone

    from backend.app import session as sess

    class FakeRedis:
        def __init__(self, payload):
            self.payload = payload

        def get(self, _key):
            return self.payload

    monkeypatch.setattr(sess, "get_redis", lambda: FakeRedis("123"))
    assert sess.read_session("sid") is None
    monkeypatch.setattr(sess, "get_redis", lambda: FakeRedis('["a"]'))
    assert sess.read_session("sid") is None

    assert sess.session_expired({"created_at": "2020-01-01T00:00:00+00:00"}) is True
    recent_aware = datetime.now(timezone.utc).isoformat()
    assert sess.session_expired({"created_at": recent_aware}) is False


def test_client_ip_rejects_malformed_proxy_header(monkeypatch):
    from types import SimpleNamespace

    from backend.app import deps

    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(trust_proxy_headers=True))

    def make_req(header_val, host="10.0.0.1"):
        return SimpleNamespace(
            headers={"x-real-ip": header_val} if header_val is not None else {},
            client=SimpleNamespace(host=host),
        )

    assert deps.client_ip(make_req("203.0.113.5")) == "203.0.113.5"
    assert deps.client_ip(make_req("1.2.3.4, 5.6.7.8")) == "10.0.0.1"
    assert deps.client_ip(make_req("1" * 60)) == "10.0.0.1"


def test_warning_cancel_migration_and_model_metadata():
    import importlib.util

    from sqlalchemy.dialects import mysql
    from backend.app.models import AuditLog, Warning

    migration_path = ROOT / "backend/migrations/versions/0007_warning_lifecycle_audit.py"
    spec = importlib.util.spec_from_file_location("migration_0007", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0007_warning_lifecycle_audit"
    assert migration.down_revision == "0006_idx_users_active"
    assert Warning.__table__.c.cancelled_at.nullable is True
    assert Warning.__table__.c.cancelled_by.nullable is True
    assert AuditLog.__table__.c.resource_version.nullable is True
    assert any(
        fk.name == "fk_warnings_cancelled_by_users"
        for fk in Warning.__table__.c.cancelled_by.foreign_keys
    )
    assert isinstance(Warning.__table__.c.cancelled_at.type, mysql.DATETIME)
    assert Warning.__table__.c.cancelled_at.type.fsp == 6


    import backend.app.schemas as schemas

    action = schemas.WarningActionRequest(reason="  发布说明  ")
    assert action.reason == "发布说明"
    assert schemas.WarningActionRequest(reason=" \t ").reason is None
    assert schemas.WarningActionRequest().reason is None


def test_audit_resource_version_is_persisted():
    from backend.app.deps import CurrentUser
    from backend.app.services.audit import AuditContext

    added = []

    class FakeDB:
        def add(self, obj):
            added.append(obj)

    ctx = AuditContext(
        db=FakeDB(),
        actor=CurrentUser(1, "u", ["VIEWER", "ADMIN"]),
        request_id="r" * 60,
        ip_address="9" * 80,
    )
    ctx.record(
        "ACT_" * 30,
        resource_type="RES_" * 30,
        resource_id="ID_" * 40,
        result="RESULT_" * 10,
        reason="why_" * 200,
    )
    ctx.record(
        "WARNING_CANCEL",
        resource_type="warning",
        resource_id="warning-1",
        resource_version=7,
    )
    assert added[1].resource_version == 7


def test_audit_truncates_oversized_fields_and_sorts_roles():
    from backend.app.deps import CurrentUser
    from backend.app.services.audit import AuditContext

    added = []

    class FakeDB:
        def add(self, obj):
            added.append(obj)

    ctx = AuditContext(
        db=FakeDB(),
        actor=CurrentUser(1, "u", ["VIEWER", "ADMIN"]),
        request_id="r" * 60,
        ip_address="9" * 80,
    )
    ctx.record(
        "ACT_" * 30,
        resource_type="RES_" * 30,
        resource_id="ID_" * 40,
        result="RESULT_" * 10,
        reason="why_" * 200,
    )
    row = added[0]
    assert row.actor_role == "ADMIN,VIEWER"
    assert len(row.actor_role) <= 32
    assert len(row.action) <= 64
    assert len(row.resource_type) <= 64
    assert len(row.resource_id) <= 64
    assert len(row.result) <= 16
    assert len(row.reason) <= 500
    assert len(row.request_id) <= 36
    assert len(row.ip_address) <= 45


@pytest.mark.parametrize("raw_date", [
    pytest.param("2024-01-31", id="before-protocol"),
    pytest.param("0001-01-01", id="minimum-date"),
    pytest.param("9999-12-31", id="maximum-date"),
    pytest.param("20240327", id="compact-iso"),
    pytest.param("2024-W13-3", id="iso-week"),
    pytest.param("2024-03-27T00:00:00", id="datetime"),
    pytest.param("2024-03-27 00:00:00", id="datetime-space"),
    pytest.param(" 2024-03-27", id="leading-space"),
    pytest.param("2024-03-27 ", id="trailing-space"),
    pytest.param("2024-03-27\n", id="trailing-newline"),
    pytest.param("", id="empty"),
    pytest.param(None, id="null"),
    pytest.param(20240327, id="integer"),
    pytest.param(20240327.0, id="float"),
    pytest.param(True, id="boolean"),
    pytest.param(["2024-03-27"], id="list"),
    pytest.param({"date": "2024-03-27"}, id="object"),
    pytest.param(date(2024, 3, 27), id="date-object"),
    pytest.param("2025-02-29", id="non-leap-year"),
    pytest.param("2024-02-30", id="invalid-leap-day"),
    pytest.param("2024-3-27", id="unpadded-month"),
    pytest.param("２０２４-０３-２７", id="non-ascii-digits"),
])
def test_validate_days_rejects_non_protocol_dates(raw_date):
    """非协议日期只记 INVALID_DATE，不构造记录、问题日期或期间候选。"""
    from backend.app.services.ingest import _validate_days

    staged = _validate_days([{
        "city_code": "WUHAN", "valid_date": raw_date,
        "models": {model: 10.0 for model in DEFAULT_MODELS}, "proxy_label_mm": 12.0,
    }])

    assert staged["fc_rows"] == []
    assert staged["obs_rows"] == []
    assert staged["fc_dates"] == set()
    assert staged["obs_dates"] == set()
    assert len(staged["issues"]) == 1
    on_obs, issue_type, city, model, issue_date, _detail = staged["issues"][0]
    assert (on_obs, issue_type, city, model, issue_date) == (False, "INVALID_DATE", "WUHAN", None, None)
    assert staged["fc_has_issue"] is True
    assert staged["obs_has_issue"] is False


@pytest.mark.parametrize(("raw_date", "expected"), [
    ("2024-02-01", date(2024, 2, 1)),
    ("2024-02-29", date(2024, 2, 29)),
    ("2026-09-30", date(2026, 9, 30)),
])
def test_validate_days_accepts_protocol_boundaries_and_leap_day(raw_date, expected):
    from decimal import Decimal

    from backend.app.services.ingest import _validate_days

    staged = _validate_days([{
        "city_code": "WUHAN", "valid_date": raw_date,
        "models": {model: 10.0 for model in DEFAULT_MODELS}, "proxy_label_mm": 12.0,
    }])

    assert len(staged["fc_rows"]) == 4
    assert {row[1] for row in staged["fc_rows"]} == set(DEFAULT_MODELS)
    assert all(row[0] == "WUHAN" and row[2] == datetime.combine(expected, datetime.min.time())
               and row[3] == Decimal("10.0") for row in staged["fc_rows"])
    assert staged["obs_rows"] == [("WUHAN", expected, Decimal("12.0"))]
    assert staged["fc_dates"] == staged["obs_dates"] == {expected}
    assert staged["issues"] == []
    assert staged["fc_has_issue"] is False
    assert staged["obs_has_issue"] is False


def test_invalid_dates_do_not_poison_duplicate_or_order_tracking():
    from backend.app.services.ingest import _validate_days

    day = {"city_code": "WUHAN", "models": {model: 10.0 for model in DEFAULT_MODELS}, "proxy_label_mm": 12.0}
    staged = _validate_days([
        {**day, "valid_date": "2026-10-01"},
        {**day, "valid_date": "20240327"},
        {**day, "valid_date": "2024-03-27"},
    ])

    assert len(staged["fc_rows"]) == 4
    assert len(staged["obs_rows"]) == 1
    assert staged["fc_dates"] == staged["obs_dates"] == {date(2024, 3, 27)}
    assert [issue[1] for issue in staged["issues"]] == ["INVALID_DATE", "INVALID_DATE"]
    assert all(issue[4] is None for issue in staged["issues"])


@pytest.fixture
def import_session():
    """本地结果语义测试用 SQLite；不代替 MySQL 外键/迁移集成验证。"""
    from sqlalchemy import Integer, MetaData, create_engine
    from sqlalchemy.dialects.mysql import BIGINT
    from sqlalchemy.orm import Session

    from backend.app.models import Dataset, DatasetIssue, ForecastRecord, FusionInput, ObservationRecord

    metadata = MetaData()
    # 复制而不修改生产映射；SQLite 自增主键须使用 INTEGER，且不支持 CURRENT_TIMESTAMP(6)。
    for table in Dataset.metadata.tables.values():
        table.to_metadata(metadata)
    tables = [metadata.tables[model.__tablename__] for model in (
        Dataset, DatasetIssue, ForecastRecord, ObservationRecord, FusionInput,
    )]
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, BIGINT):
                column.type = Integer()
            if column.server_default is not None and "CURRENT_TIMESTAMP" in str(column.server_default.arg):
                column.server_default = None
    engine = create_engine("sqlite://")
    metadata.create_all(engine, tables=tables)
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            yield session
    finally:
        engine.dispose()


def _write_import_sample(tmp_path, *, version="unit-sample", days=None):
    path = tmp_path / "sample.json"
    path.write_text(json.dumps({"version": version, "days": days if days is not None else [{
        "city_code": "WUHAN", "valid_date": "2024-03-27",
        "models": {model: 10.0 for model in DEFAULT_MODELS}, "proxy_label_mm": 12.0,
    }]}), encoding="utf-8")
    return path


@pytest.mark.parametrize("unreadable", [False, True], ids=["missing", "permission-denied"])
def test_import_sample_handles_missing_file_gracefully(import_session, tmp_path, monkeypatch, unreadable):
    from sqlalchemy import func, select

    from backend.app.models import Dataset, DatasetIssue
    from backend.app.services import ingest

    missing = tmp_path / "does_not_exist.json"
    if unreadable:
        def deny_read(_path):
            raise PermissionError("sample access denied")
        monkeypatch.setattr(Path, "read_bytes", deny_read)
    with pytest.raises(OSError) as exc_info:
        missing.read_bytes()
    result = ingest.import_sample(import_session, missing, 1, 2)
    assert result["imported"] is False
    assert result.get("unusable") is True
    assert result["forecast"] == result["observation"] == result["issues"] == 0
    assert result["error"] == str(exc_info.value)
    assert result.get("outcome") == "file_unreadable"
    assert result.get("has_usable_forecast") is False
    assert import_session.scalar(select(func.count()).select_from(Dataset)) == 0
    assert import_session.scalar(select(func.count()).select_from(DatasetIssue)) == 0


@pytest.mark.parametrize("partial", [False, True], ids=["ready", "partial"])
def test_import_outcome_success_and_idempotency(import_session, tmp_path, partial):
    from backend.app.services import ingest

    path = _write_import_sample(tmp_path)
    if partial:
        data = json.loads(path.read_text())
        del data["days"][0]["models"]["gem_global"]
        path.write_text(json.dumps(data), encoding="utf-8")
    first = ingest.import_sample(import_session, path, 1, 2)
    assert first.get("outcome") == "imported"
    assert first.get("has_usable_forecast") is True
    assert first["forecast"] == (3 if partial else 4)
    second = ingest.import_sample(import_session, path, 1, 2)
    assert second.get("outcome") == "unchanged"
    assert second.get("has_usable_forecast") is True
    assert second["imported"] is False
    assert second["forecast"] == second["observation"] == second["issues"] == 0


@pytest.mark.parametrize("payload", [
    b'{"version":"bad","days":[]}',
    b'{"version":"bad","days":[{"city_code":"ATLANTIS"}]}',
    b'{"version":"bad","days":[{"city_code":"WUHAN","valid_date":"2024-03-27","models":{},"proxy_label_mm":12}]}',
    b'{not-json',
    b'\xff',
    b'[]',
], ids=["empty", "rejected", "observation-only", "invalid-json", "invalid-utf8", "non-object"])
@pytest.mark.parametrize("existing_usable", [False, True], ids=["fresh", "older-usable"])
def test_import_outcome_failed_uses_remaining_forecast(import_session, tmp_path, payload, existing_usable):
    from sqlalchemy import func, select

    from backend.app.models import Dataset, DatasetIssue
    from backend.app.services import ingest

    if existing_usable:
        ingest.import_sample(import_session, _write_import_sample(tmp_path, version="older"), 1, 2)
    path = tmp_path / "bad.json"
    path.write_bytes(payload)
    result = ingest.import_sample(import_session, path, 1, 2)
    assert result.get("outcome") == "marked_failed"
    assert result.get("has_usable_forecast") is existing_usable
    assert result.get("unusable") is True
    failed = import_session.scalar(select(Dataset).where(
        Dataset.dataset_type == "FORECAST", Dataset.version != "older",
    ))
    assert failed.quality_status == "FAILED"
    assert failed.row_count == 0
    issue_count = import_session.scalar(select(func.count()).select_from(DatasetIssue))
    assert issue_count == result["issues"]
    second = ingest.import_sample(import_session, path, 1, 2)
    assert second.get("outcome") == "unchanged_failed"
    assert second.get("has_usable_forecast") is existing_usable
    assert second["imported"] is False
    assert second["issues"] == 0
    assert import_session.scalar(select(func.count()).select_from(DatasetIssue)) == issue_count


@pytest.mark.parametrize(("dataset_type", "status", "row_count", "usable"), [
    ("FORECAST", "READY", 4, True),
    ("FORECAST", "PARTIAL", 1, True),
    ("FORECAST", "READY", 0, False),
    ("FORECAST", "FAILED", 4, False),
    ("ERA5_LABEL", "READY", 4, False),
])
def test_import_outcome_unreadable_checks_usable_forecast_metadata(
    import_session, tmp_path, dataset_type, status, row_count, usable,
):
    from backend.app.models import Dataset
    from backend.app.services import ingest

    import_session.add(Dataset(
        source_id=1, dataset_type=dataset_type, version="existing",
        period_start=date(2024, 3, 27), period_end=date(2024, 3, 27),
        quality_status=status, row_count=row_count,
    ))
    import_session.commit()
    result = ingest.import_sample(import_session, tmp_path / "missing.json", 1, 2)
    assert result.get("outcome") == "file_unreadable"
    assert result.get("has_usable_forecast") is usable


@pytest.mark.parametrize("days", [[], [{"city_code": "ATLANTIS"}]])
def test_import_outcome_preserves_existing_without_persisting_issues(import_session, tmp_path, days):
    from sqlalchemy import func, select

    from backend.app.models import Dataset, DatasetIssue, ForecastRecord, ObservationRecord
    from backend.app.services import ingest

    path = _write_import_sample(tmp_path)
    ingest.import_sample(import_session, path, 1, 2)
    before = [(d.id, d.checksum, d.quality_status, d.row_count) for d in import_session.scalars(select(Dataset))]
    _write_import_sample(tmp_path, days=days)
    result = ingest.import_sample(import_session, path, 1, 2)
    assert result.get("outcome") == "preserved_existing"
    assert result.get("has_usable_forecast") is True
    assert result["blocked"] == "unusable_sample"
    assert [(d.id, d.checksum, d.quality_status, d.row_count) for d in import_session.scalars(select(Dataset))] == before
    assert import_session.scalar(select(func.count()).select_from(DatasetIssue)) == 0
    assert import_session.scalar(select(func.count()).select_from(ForecastRecord)) == 4
    assert import_session.scalar(select(func.count()).select_from(ObservationRecord)) == 1


def test_import_outcome_dataset_in_use_keeps_records(import_session, tmp_path):
    from decimal import Decimal

    from sqlalchemy import func, select

    from backend.app.models import Dataset, ForecastRecord, FusionInput
    from backend.app.services import ingest

    path = _write_import_sample(tmp_path)
    ingest.import_sample(import_session, path, 1, 2)
    record = import_session.scalar(select(ForecastRecord))
    import_session.add(FusionInput(
        fusion_run_id=1, forecast_record_id=record.id, model_code=record.model_code, value_mm=Decimal("10"),
    ))
    import_session.commit()
    checksums = list(import_session.scalars(select(Dataset.checksum)))
    _write_import_sample(tmp_path, days=[])
    result = ingest.import_sample(import_session, path, 1, 2)
    assert result.get("outcome") == "dataset_in_use"
    assert result.get("has_usable_forecast") is True
    assert result["blocked"] == "dataset_in_use"
    assert result["issues"] == 0
    assert list(import_session.scalars(select(Dataset.checksum))) == checksums
    assert import_session.scalar(select(func.count()).select_from(ForecastRecord)) == 4


@pytest.mark.parametrize(("scenario", "message", "exit_code"), [
    ("imported", "已导入", 0),
    ("unchanged", "无需导入", 0),
    ("marked_failed", "本次落为 FAILED", 1),
    ("unchanged_failed", "已有 FAILED 数据集未改变", 1),
    ("file_unreadable", "未读取", 1),
    ("preserved_existing", "保留已有可用版本", 0),
    ("older-usable", "本次落为 FAILED", 0),
    ("unreadable-with-existing", "未读取", 0),
])
def test_seed_outcome_messages_and_exit_status(
    import_session, tmp_path, monkeypatch, capsys, scenario, message, exit_code,
):
    import sys
    from contextlib import nullcontext

    from backend.app import seed
    from backend.app.services import ingest

    path = _write_import_sample(tmp_path)
    if scenario in {"unchanged", "preserved_existing", "unreadable-with-existing"}:
        ingest.import_sample(import_session, path, 1, 2)
    if scenario == "older-usable":
        ingest.import_sample(import_session, _write_import_sample(tmp_path, version="older"), 1, 2)
    if scenario in {"marked_failed", "unchanged_failed", "preserved_existing", "older-usable"}:
        path = _write_import_sample(tmp_path, days=[])
    if scenario == "unchanged_failed":
        ingest.import_sample(import_session, path, 1, 2)
    if scenario in {"file_unreadable", "unreadable-with-existing"}:
        path = tmp_path / "missing.json"
    monkeypatch.setattr(seed, "_source_id", lambda _session, code: {
        "OPEN_METEO_PREVIOUS_RUNS": 1, "OPEN_METEO_ERA5": 2,
    }[code])
    monkeypatch.setattr(seed, "SessionLocal", lambda: nullcontext(import_session))
    monkeypatch.setattr(seed, "seed_reference_data", lambda _session: None)
    monkeypatch.setattr(seed, "seed_users", lambda _session, **_kwargs: None)
    monkeypatch.setattr(sys, "argv", ["seed", "--sample", str(path)])

    status = seed.main()
    output = capsys.readouterr().out
    assert message in output
    assert status == exit_code
    if exit_code:
        assert "[seed] 完成" not in output
        assert "无可用预报数据" in output
    if scenario in {"file_unreadable", "unreadable-with-existing"}:
        with pytest.raises(OSError) as exc_info:
            path.read_bytes()
        assert str(exc_info.value) in output
        assert "FAILED" not in output
    if scenario == "preserved_existing":
        assert "本次未写入" in output
        assert "已标记为 FAILED" not in output
        assert "已导入" not in output


@pytest.mark.parametrize("existing", [False, True])
def test_seed_import_returns_parse_error(import_session, tmp_path, monkeypatch, capsys, existing):
    from backend.app import seed
    from backend.app.services import ingest

    monkeypatch.setattr(seed, "_source_id", lambda _session, _code: 1)
    path = _write_import_sample(tmp_path, version="sample")
    if existing:
        ingest.import_sample(import_session, path, 1, 1)
    path.write_bytes(b'{not-json')
    result = seed.import_sample(import_session, path)
    output = capsys.readouterr().out
    assert "不是合法 JSON" in output
    assert result["outcome"] == ("preserved_existing" if existing else "marked_failed")
    result = seed.import_sample(import_session, path)
    assert "不是合法 JSON" in capsys.readouterr().out
    assert result["outcome"] == ("preserved_existing" if existing else "unchanged_failed")


def test_import_outcome_does_not_preserve_empty_forecast(import_session, tmp_path):
    from sqlalchemy import select

    from backend.app.models import Dataset
    from backend.app.services import ingest

    path = _write_import_sample(tmp_path, days=[])
    import_session.add(Dataset(
        source_id=1, dataset_type="FORECAST", version="unit-sample",
        period_start=date.min, period_end=date.min, quality_status="READY", row_count=0,
    ))
    import_session.commit()
    result = ingest.import_sample(import_session, path, 1, 2)
    assert result.get("outcome") == "marked_failed"
    assert result.get("has_usable_forecast") is False
    assert import_session.scalar(select(Dataset.quality_status).where(Dataset.dataset_type == "FORECAST")) == "FAILED"


def test_seed_import_returns_result_and_source_error(import_session, tmp_path, monkeypatch, capsys):
    from backend.app import seed

    monkeypatch.setattr(seed, "_source_id", lambda _session, _code: 1)
    missing = tmp_path / "missing.json"
    result = seed.import_sample(import_session, missing)
    output = capsys.readouterr().out
    assert isinstance(result, dict)
    assert result["outcome"] == "file_unreadable"
    assert result["has_usable_forecast"] is False
    assert result["error"] in output


@pytest.mark.parametrize("usable", [False, True])
def test_seed_module_entrypoint_propagates_exit_status(monkeypatch, usable):
    import runpy
    import sys
    from unittest.mock import MagicMock

    from backend.app import db
    from backend.app.services import ingest

    monkeypatch.delitem(sys.modules, "backend.app.seed", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed"])
    monkeypatch.setattr(db, "SessionLocal", MagicMock())
    for role in ("ADMIN", "ANALYST", "REVIEWER", "VIEWER"):
        monkeypatch.delenv(f"DEMO_{role}_PASSWORD", raising=False)
    result = {
        "imported": False, "forecast": 0, "observation": 0, "issues": 0,
        "outcome": "unchanged" if usable else "unchanged_failed",
        "has_usable_forecast": usable,
    }
    if not usable:
        result["unusable"] = True
    monkeypatch.setattr(ingest, "import_sample", lambda *_args: result)
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("backend.app.seed", run_name="__main__")
    assert exc_info.value.code == (0 if usable else 1)


def test_seed_sync_passwords_clears_lockout_and_main_orders_users_before_sample(monkeypatch):
    import sys
    from datetime import datetime, timedelta
    from pathlib import Path
    from types import SimpleNamespace

    from backend.app import seed

    existing_user = SimpleNamespace(
        id=99,
        username="admin",
        password_hash="old",
        is_active=False,
        failed_login_count=5,
        locked_until=datetime.utcnow() + timedelta(minutes=10),
    )

    class FakeSession:
        def __init__(self):
            self.committed = False

        def scalar(self, stmt):
            sql = str(stmt)
            if "roles" in sql and "users" not in sql:
                return SimpleNamespace(id=1, code="ADMIN")
            if existing_user.username in repr(stmt.compile().params):
                return existing_user
            return None

        def add(self, _obj):
            pass

        def flush(self):
            pass

        def execute(self, _stmt):
            pass

        def commit(self):
            self.committed = True

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "NewAdminPass!123")
    monkeypatch.delenv("DEMO_ANALYST_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_REVIEWER_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_VIEWER_PASSWORD", raising=False)
    seed.seed_users(FakeSession(), sync_passwords=True)
    assert existing_user.is_active is True
    assert existing_user.failed_login_count == 0
    assert existing_user.locked_until is None

    order = []
    monkeypatch.setattr(seed, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(seed, "seed_reference_data", lambda _s: order.append("ref"))
    monkeypatch.setattr(seed, "seed_users", lambda _s, sync_passwords=False: order.append("users"))
    def import_unchanged(_session, _path):
        order.append("sample")
        return {"imported": False, "forecast": 0, "observation": 0, "issues": 0,
                "outcome": "unchanged", "has_usable_forecast": True}

    monkeypatch.setattr(seed, "import_sample", import_unchanged)
    monkeypatch.setattr(sys, "argv", ["seed.py", "--sample", str(Path("data/sample/replay_sample.json"))])
    assert seed.main() == 0
    assert order == ["ref", "users", "sample"]


def test_review_and_feedback_schemas_enforce_literal_and_optional_comment():
    import pytest
    from pydantic import ValidationError

    from backend.app.schemas import FeedbackRequest, ReviewRequest

    req = ReviewRequest(decision="APPROVE")
    assert req.comment == ""

    with pytest.raises(ValidationError):
        ReviewRequest(decision="INVALID", comment="x")

    with pytest.raises(ValidationError):
        FeedbackRequest(response_status="BAD", content="x")


def test_config_rejects_samesite_none_without_cookie_secure():
    import pytest

    from backend.app.config import Settings

    s = Settings(app_env="development", cookie_samesite="none", cookie_secure=False)
    with pytest.raises(ValueError):
        s.validate_for_serving()


def test_scheduler_logs_exception_before_rollback(monkeypatch):
    from datetime import datetime

    from backend.app import scheduler

    events = []

    class FakeDB:
        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

    monkeypatch.setattr(scheduler, "backfill_published", lambda *_a, **_kw: (_ for _ in ()).throw(ValueError("boom")))
    monkeypatch.setattr(scheduler, "escalate_overdue", lambda *_a, **_kw: 0)
    monkeypatch.setattr(scheduler.logger, "exception", lambda *_a, **_kw: events.append("log"))

    res = scheduler.run_scan(FakeDB(), now=datetime(2024, 3, 27, 0, 0), hours=24)
    assert res.failed == ("backfill",)
    assert events[:2] == ["log", "rollback"]


def test_to_detail_out_orders_models_and_warning_service_edge_guards():
    from datetime import date, datetime
    from decimal import Decimal
    from types import SimpleNamespace

    import pytest
    from fastapi import HTTPException

    from backend.app.deps import CurrentUser
    from backend.app.schemas import WarningUpdate
    from backend.app.services import warnings as svc

    wr = SimpleNamespace(
        city_code="CHANGSHA",
        valid_date=date(2024, 3, 27),
        risk_level="YELLOW",
        fused_mm=Decimal("25.0"),
        baseline_mm=Decimal("20.0"),
        proxy_label_mm=Decimal("22.0"),
        fusion_run_id=7,
    )
    w = SimpleNamespace(
        public_id="p1",
        hazard_type="RAINSTORM",
        status="DRAFT",
        title="t",
        area_text="a",
        impact_text=None,
        reasoning_text="r",
        version_no=1,
        created_by=1,
        submitted_at=None,
        approved_at=None,
        published_at=None,
        withdrawn_at=None,
        warning_result=wr,
    )
    reversed_inputs = [
        SimpleNamespace(model_code="gem_global", value_mm=Decimal("4.0"), forecast_record_id=4),
        SimpleNamespace(model_code="icon_global", value_mm=Decimal("3.0"), forecast_record_id=3),
        SimpleNamespace(model_code="gfs_global", value_mm=Decimal("2.0"), forecast_record_id=2),
        SimpleNamespace(model_code="ecmwf_ifs025", value_mm=Decimal("1.0"), forecast_record_id=1),
    ]

    class FakeDetailDB:
        def scalars(self, _stmt):
            return SimpleNamespace(all=lambda: reversed_inputs)

        def scalar(self, _stmt):
            return "v1"

    detail = svc.to_detail_out(FakeDetailDB(), w, {1: "analyst"})
    assert [m.model for m in detail.models] == ["ECMWF", "GFS", "ICON", "GEM"]

    recorded = []

    class FakeAudit:
        def record(self, *args, **kwargs):
            recorded.append((args, kwargs))

    class FakeEmptyDB:
        def scalar(self, _stmt):
            return w

        def flush(self):
            pass

    actor = CurrentUser(id=1, username="analyst", roles=["ANALYST"])
    svc.update_warning(FakeEmptyDB(), "p1", WarningUpdate(), actor, FakeAudit())
    assert recorded == []

    w.status = svc.PENDING_REVIEW
    reviewer = CurrentUser(id=2, username="reviewer", roles=["REVIEWER"])
    with pytest.raises(HTTPException) as exc_info:
        svc.review_warning(FakeEmptyDB(), "p1", "BAD_DECISION", "c", reviewer, FakeAudit())
    assert exc_info.value.status_code == 422


def test_lock_admin_raises_503_when_admin_role_missing():
    from types import SimpleNamespace

    import pytest
    from fastapi import HTTPException

    from backend.app.deps import CurrentUser
    from backend.app.routers import users as users_router

    class MissingAdminDB:
        def scalar(self, _stmt):
            return None

    with pytest.raises(HTTPException) as exc_info:
        users_router._lock_admin(MissingAdminDB(), CurrentUser(1, "admin", ["ADMIN"]), SimpleNamespace())
    assert exc_info.value.status_code == 503


def test_user_model_and_0006_migration_define_idx_users_active():
    import importlib

    from backend.app.models import User

    indexes = {idx.name: [col.name for col in idx.columns] for idx in User.__table__.indexes}
    assert indexes.get("idx_users_active") == ["is_active"]

    mig = importlib.import_module("backend.migrations.versions.0006_idx_users_active")
    assert mig.revision == "0006_idx_users_active"
    assert mig.down_revision == "0005_subscriptions_notifications"
