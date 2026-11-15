import json
from pathlib import Path

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

    base = dict(city_code="WUHAN", valid_date=date(2024, 1, 1), threshold_code="HEAVY", title="t", area_text="a")
    with pytest.raises(ValidationError):
        WarningCreate(**base, reasoning_text="😀" * 20000)
    with pytest.raises(ValidationError):
        WarningUpdate(reasoning_text="😀" * 20000)
    # 中文按 3 字节计，20,000 字符 = 60,000 字节，仍在 TEXT 容量内
    assert WarningCreate(**base, reasoning_text="雨" * 20000).reasoning_text
