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
