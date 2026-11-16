"""融合追溯（FR-04）：创建预警写入 fusion_inputs，详情接口返回四模式输入/基线/代理标签。

需要 RUN_INTEGRATION=1 与 DEMO_*_PASSWORD。测试创建的预警由 conftest 的
``created_warnings`` 夹具在结束时连同融合记录一并清理。
"""

import pytest

from conftest import PARTIAL_DAY, csrf_headers

pytestmark = pytest.mark.integration

# 回放样本中长沙 2024-03-27 四模式完整日（融合 29.625mm）
EXPECTED_MODELS = {"ECMWF", "GFS", "ICON", "GEM"}


def test_detail_returns_fusion_traceability(login, make_warning):
    analyst, csrf = login("analyst_demo")
    public_id = make_warning(analyst, csrf, "fusion-trace")

    detail = analyst.get(f"/api/v1/warnings/{public_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()

    # 四模式输入：显示名与数值齐全，数值与回放样本一致
    models = {m["model"]: m["precipitation_mm"] for m in body["models"]}
    assert set(models) == EXPECTED_MODELS
    assert models["ECMWF"] == pytest.approx(32.7)
    assert models["GEM"] == pytest.approx(35.5)

    # 基线为 ECMWF，代理标签来自 ERA5，融合值为四模式等权平均
    assert body["baseline_mm"] == pytest.approx(32.7)
    assert body["proxy_label_mm"] == pytest.approx(29.6)
    assert body["fused_mm"] == pytest.approx(29.625, abs=1e-3)
    assert body["dataset_version"]

    # 追溯字段是对外 WarningOut 的增量，列表接口不应暴露
    listed = analyst.get("/api/v1/warnings").json()
    entry = next(w for w in listed if w["public_id"] == public_id)
    assert "models" not in entry


def test_partial_day_cannot_create_warning(login):
    analyst, csrf = login("analyst_demo")
    payload = {
        **PARTIAL_DAY,
        "threshold_code": "HEAVY",
        "title": "fusion-partial",
        "area_text": "自动化测试",
        "reasoning_text": "自动化测试",
    }
    resp = analyst.post("/api/v1/warnings", headers=csrf_headers(csrf), json=payload)
    # 缺 GEM 的一天数据不完整，禁止创建正式预警
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PARTIAL_DATA"


def test_complete_below_threshold_cannot_create_warning(login):
    """COMPLETE 但融合值未达所选阈值：禁止创建（risk_level 为空）。"""
    analyst, csrf = login("analyst_demo")
    # 长沙 2024-03-27 四模式完整，融合 29.625mm < STORM(50mm)
    payload = {
        "city_code": "CHANGSHA",
        "valid_date": "2024-03-27",
        "threshold_code": "STORM",
        "title": "fusion-below-threshold",
        "area_text": "自动化测试",
        "reasoning_text": "自动化测试",
    }
    resp = analyst.post("/api/v1/warnings", headers=csrf_headers(csrf), json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "THRESHOLD_NOT_REACHED"


def _partial_days(client) -> int:
    resp = client.get("/api/v1/monitor/status")
    assert resp.status_code == 200, resp.text
    return resp.json()["coverage"]["partial_days"]


def _replay(analyst, valid_date: str):
    return analyst.get(
        "/api/v1/replay",
        params={"city_code": "CHANGSHA", "date": valid_date, "threshold_code": "HEAVY"},
    )


def test_null_model_value_is_partial_not_a_crash(login):
    """值为 NULL 的记录不能算「这一天有该模式」：既不能 500，也不能判成 COMPLETE。"""
    from datetime import datetime

    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import ForecastRecord
    from backend.app.services.replay import latest_dataset

    analyst, _ = login("analyst_demo")
    baseline = _partial_days(analyst)

    with SessionLocal() as db:
        fc_ds = latest_dataset(db, "FORECAST")
        assert fc_ds is not None
        record = db.scalar(
            select(ForecastRecord).where(
                ForecastRecord.dataset_id == fc_ds.id,
                ForecastRecord.city_code == "CHANGSHA",
                ForecastRecord.valid_at == datetime(2024, 3, 27),
                ForecastRecord.model_code == "gem_global",
            )
        )
        assert record is not None, "样本里应有长沙 2024-03-27 的 GEM 记录"
        record_pk, original = record.id, record.precipitation_mm
        record.precipitation_mm = None
        db.commit()

    try:
        resp = _replay(analyst, "2024-03-27")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data_status"] == "PARTIAL"
        assert body["fused_mm"] is None
        assert body["risk_level"] is None
        assert _partial_days(analyst) == baseline + 1
    finally:
        with SessionLocal() as db:
            db.get(ForecastRecord, record_pk).precipitation_mm = original
            db.commit()


def test_null_baseline_does_not_crash(login):
    """ECMWF 基线值为 NULL 时也只能判 PARTIAL，不能 500。

    基线走的是独立的取值路径，上一轮只给融合值加了非空判定，基线漏掉了。
    """
    from datetime import datetime

    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.models import ForecastRecord
    from backend.app.services.replay import latest_dataset

    analyst, _ = login("analyst_demo")

    with SessionLocal() as db:
        fc_ds = latest_dataset(db, "FORECAST")
        assert fc_ds is not None
        record = db.scalar(
            select(ForecastRecord).where(
                ForecastRecord.dataset_id == fc_ds.id,
                ForecastRecord.city_code == "CHANGSHA",
                ForecastRecord.valid_at == datetime(2024, 3, 27),
                ForecastRecord.model_code == "ecmwf_ifs025",
            )
        )
        assert record is not None
        record_pk, original = record.id, record.precipitation_mm
        record.precipitation_mm = None
        db.commit()

    try:
        resp = _replay(analyst, "2024-03-27")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["data_status"] == "PARTIAL"
        assert body["baseline_mm"] is None
    finally:
        with SessionLocal() as db:
            db.get(ForecastRecord, record_pk).precipitation_mm = original
            db.commit()


def test_monitor_counts_lead_hours_like_replay(login):
    """提前量不是固定 24 小时的记录同样不算齐全，监测口径要与回放一致。"""
    from datetime import datetime

    from sqlalchemy import select

    from backend.app.cities import LEAD_HOURS
    from backend.app.db import SessionLocal
    from backend.app.models import ForecastRecord
    from backend.app.services.replay import latest_dataset

    analyst, _ = login("analyst_demo")
    baseline = _partial_days(analyst)

    with SessionLocal() as db:
        fc_ds = latest_dataset(db, "FORECAST")
        assert fc_ds is not None
        record = db.scalar(
            select(ForecastRecord).where(
                ForecastRecord.dataset_id == fc_ds.id,
                ForecastRecord.city_code == "CHANGSHA",
                ForecastRecord.valid_at == datetime(2024, 3, 27),
                ForecastRecord.model_code == "gem_global",
            )
        )
        assert record is not None
        record_pk, original_lead = record.id, record.lead_hours
        record.lead_hours = LEAD_HOURS + 24
        db.commit()

    try:
        assert _replay(analyst, "2024-03-27").json()["data_status"] == "PARTIAL"
        assert _partial_days(analyst) == baseline + 1
    finally:
        with SessionLocal() as db:
            db.get(ForecastRecord, record_pk).lead_hours = original_lead
            db.commit()


def test_replay_does_not_leak_failed_datasets_when_no_valid_dataset_exists(monkeypatch):
    """全部预报批次都处于 FAILED（latest_dataset 返回 None）时，不能无过滤读取失败数据。"""
    from datetime import date

    from backend.app.db import SessionLocal
    from backend.app.services import replay

    monkeypatch.setattr(replay, "latest_dataset", lambda db, dtype, version=None: None)
    with SessionLocal() as db:
        result = replay.compute_replay(db, "CHANGSHA", date(2024, 3, 27), "HEAVY")
    assert result is not None
    assert result["data_status"] == "PARTIAL"
    assert result["fused_mm"] is None
    assert result["risk_level"] is None
    assert all(m.precipitation_mm is None for m in result["models"])


def test_replay_includes_cached_at_timestamp(login):
    client, _csrf = login("viewer_demo")
    resp = client.get(
        "/api/v1/replay",
        params={"city_code": "CHANGSHA", "date": "2024-03-27", "threshold_code": "HEAVY"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"]["cached_at"] is not None


def test_replay_uses_decimal_half_up_precision():
    from datetime import date, datetime
    from decimal import Decimal

    from sqlalchemy import select

    from backend.app.cities import LEAD_HOURS
    from backend.app.db import SessionLocal
    from backend.app.models import Dataset, ForecastRecord
    from backend.app.services import replay

    with SessionLocal() as db:
        fc_ds = replay.latest_dataset(db, "FORECAST")
        assert fc_ds is not None
        recs = db.scalars(
            select(ForecastRecord).where(
                ForecastRecord.dataset_id == fc_ds.id,
                ForecastRecord.city_code == "CHANGSHA",
                ForecastRecord.valid_at == datetime(2024, 3, 27),
                ForecastRecord.lead_hours == LEAD_HOURS,
            )
        ).all()
        assert len(recs) == 4
        originals = {r.id: r.precipitation_mm for r in recs}
        test_vals = [Decimal("25.000"), Decimal("25.001"), Decimal("25.000"), Decimal("25.001")]
        try:
            for rec, val in zip(recs, test_vals):
                rec.precipitation_mm = val
            db.commit()

            # 均值 25.0005：二进制浮点 round(..., 3) 会偶舍入成 25.0，Decimal HALF_UP 必须为 25.001
            out = replay.compute_replay(db, "CHANGSHA", date(2024, 3, 27), "HEAVY")
            assert out["fused_mm"] == 25.001
        finally:
            for rec in recs:
                rec.precipitation_mm = originals[rec.id]
            db.commit()
